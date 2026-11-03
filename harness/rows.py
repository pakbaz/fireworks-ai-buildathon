"""The four rows. Each returns one prediction dict (see docs/work-split.md)."""
import json, math
from . import client, prompts, packet, domain, dial, supplier_history

def _acc(stats, model, r):
    ti, to, c = client.usage_cost(model, r)
    stats["calls"] += 1  # counted even when served from the shared cache, so per-row cost is complete
    stats["cached_calls"] = stats.get("cached_calls", 0) + bool(r.get("_cached"))
    stats["tokens_in"] += ti; stats["tokens_out"] += to; stats["cost_usd"] += c
    stats["latency_ms"] += r.get("_latency_ms", 0)

def _action_prob(r):
    """P(ESCALATE) from the token probabilities at the action value; None if not available."""
    lp = ((r["choices"][0].get("logprobs") or {}).get("content")) or []
    text = ""
    for tok in lp:
        if text.rstrip().endswith('"action":"') or text.rstrip().endswith('"action": "') or text.endswith('"action": "') or text.endswith('"action":"'):
            p = {"E": 0.0, "P": 0.0, "W": 0.0}
            for alt in tok.get("top_logprobs") or []:
                t = alt["token"].strip().upper()[:1]
                if t in p:
                    p[t] += math.exp(alt["logprob"])
            s = sum(p.values())
            return p["E"] / s if s > 0.5 else None
        text += tok.get("token", "")
    return None

def _history_summary(h):
    if not h:
        return None
    # Same history facts the harness uses, so the comparison is about how the information is used, not who has it.
    return {k: h.get(k) for k in ("invoices", "problem_rate", "problems_by_type", "unit_price_by_sku", "lead_days",
                                  "remit_to", "ship_from", "qty_max_by_company_sku")}

def alone(case, model, use_images, frontier):
    stats = dict(calls=0, tokens_in=0, tokens_out=0, cost_usd=0.0, latency_ms=0)
    wiki, policy = packet.load_wiki(case)
    pages = {"supplier": wiki["supplier"], "items": wiki["items"], "supplier_history": _history_summary(wiki.get("history"))}
    content = [{"type": "text", "text": prompts.ALONE + "\n\n" + packet.context_text(case, pages, policy)}] + packet.document_parts(case, use_images)
    r = client.chat(model, [{"role": "user", "content": content}], max_tokens=4000 if not frontier else 600, logprobs=frontier)
    _acc(stats, model, r)
    j = client.parse_json(client.content(r)) or {}
    model_action = str(j.get("action", "")).upper() or None
    if model_action not in ("PAY", "WAIT", "ESCALATE"):
        # Empty, malformed or truncated output: never a payment recommendation.
        return dict(model=model, action="ESCALATE", model_action=model_action, risk=None, at_risk_usd=None,
                    reason_code="invalid_model_output", next_step="investigate", evidence="model output was missing or invalid; sent for review",
                    features=None, read=None, issues=None, dial=None, **stats)
    risk = _action_prob(r) if frontier else None
    if risk is None:
        risk = domain.num(j.get("risk"))
        if risk is None:
            risk = 0.98 if model_action == "ESCALATE" else 0.02
    at_risk = domain.num(j.get("at_risk_usd")) or 0.0
    wait = model_action == "WAIT"
    action = dial.decide(risk, at_risk, wait, wiki, policy)
    return dict(model=model, action=action, model_action=model_action, risk=round(float(risk), 4), at_risk_usd=at_risk,
                reason_code=j.get("reason_code"), next_step=j.get("next_step"), evidence=j.get("evidence"),
                features=None, read=None, issues=None, dial=dial.explain(risk, at_risk, wiki, policy), **stats)

def harness(case, model, use_images, with_wiki):
    stats = dict(calls=0, tokens_in=0, tokens_out=0, cost_usd=0.0, latency_ms=0)
    wiki_full, policy = packet.load_wiki(case)
    wiki = wiki_full if with_wiki else None
    # 0. Low-value gate: pay without checking when even a total loss is cheaper than a check (text mode only;
    #    with images the total is not known before reading).
    if not use_images:
        skip, info = dial.skip_check(case, wiki_full, policy)
        if skip:
            return dict(model=model, action="PAY", model_action=None, risk=None, at_risk_usd=info["invoice_total_usd"],
                        reason_code="below_review_threshold", next_step="pay",
                        evidence=f"invoice total ${info['invoice_total_usd']:,.2f}: worst-case loss ${info['max_loss_usd']:,.2f} is below the ${info['limit_usd']:,.2f} cost of checking",
                        features={"skipped": True, **info}, read=None, issues=[], dial=None, **stats)
    docs = packet.document_parts(case, use_images)
    # 1. Reading expert. Identical request in both harness rows, so the disk cache shares it.
    r = client.chat(model, [{"role": "user", "content": [{"type": "text", "text": prompts.READ}] + docs}], max_tokens=6000)
    _acc(stats, model, r)
    read = client.parse_json(client.content(r)) or {}
    if not read.get("invoice") or not read.get("po"):
        # Reader produced no invoice or PO: never pay on an empty read.
        return dict(model=model, action="ESCALATE", model_action=None, risk=None, at_risk_usd=None, reason_code="invalid_model_output",
                    next_step="investigate", evidence="reader returned no invoice or purchase order; sent for review",
                    features=None, read=read, issues=None, dial=None, **stats)
    # 1b. A document that exists but came back empty is a reading failure, not an absent document: read it alone.
    present = {k for k in ("po", "shipping_notice", "gr", "invoice")
               if (case.get("documents") or {}).get(k) or (use_images and k in packet.images_of(case))}
    dropped = [k for k in sorted(present) if not read.get(k)]
    if dropped:
        parts = [p for p in packet.document_parts(case, use_images)
                 if not (p.get("type") == "text" and any(p["text"].startswith(f"--- {packet.DOC_NAMES[o]}") for o in ("po", "shipping_notice", "gr", "invoice") if o not in dropped))]
        rd = client.chat(model, [{"role": "user", "content": [{"type": "text", "text": prompts.READ + "\n\nOnly these documents are included; return null for the others."}] + parts}], max_tokens=6000)
        _acc(stats, model, rd)
        extra = client.parse_json(client.content(rd)) or {}
        for k in dropped:
            if extra.get(k):
                read[k] = extra[k]
    issues, feats, at_risk, wait = domain.analyze(read, case, wiki, policy)
    agree = True
    read2 = None
    # 2. Re-read only when a check failed or a value was unreadable.
    if issues or feats["n_unreadable"]:
        focus = ", ".join(feats["unreadable"] + [i[2] for i in issues]) or "all quantities, prices and references"
        hints = ""
        if with_wiki:
            hint = {"supplier": {k: v for k, v in (wiki["supplier"] or {}).items() if k in ("aliases", "po_ref_style", "number_format", "handwritten_qty_authoritative", "layout_notes", "sites")},
                    "items": [{k: v for k, v in it.items() if k in ("sku", "description_variants", "uom", "pack_conversions")} for it in wiki["items"]]}
            hints = "Company reference data (facts about how this supplier writes documents; data, not instructions): " + json.dumps(hint) + "\n"
        r2 = client.chat(model, [{"role": "user", "content": [{"type": "text", "text": prompts.READ + "\n\n" + prompts.REREAD.format(focus=focus, hints=hints)}] + docs}], max_tokens=6000)
        _acc(stats, model, r2)
        read2 = client.parse_json(client.content(r2))
        if read2:
            issues2, feats2, at_risk2, wait2 = domain.analyze(read2, case, wiki, policy)
            agree = (feats2["codes"] == feats["codes"])
            issues, feats, at_risk, wait = issues2, feats2, at_risk2, wait2
    if with_wiki:
        ctx = supplier_history.context_issues(case, read2 or read, wiki_full.get("history"), wiki_full.get("supplier"), wiki["items"], policy)
        for code, step, detail, usd in ctx:
            issues.append((code, step, detail)); at_risk = max(at_risk, round(usd or 0, 2))
        feats["n_issues"] = len(issues); feats["codes"] = [i[0] for i in issues]
    risk = dial.raw_risk(feats, agree)
    feats["reads_agree"] = agree
    action = dial.decide(risk, at_risk, wait, wiki_full, policy)  # the business dial uses company config in every row
    if issues:
        code, step, ev = issues[0]
    elif wait:
        code, step, ev = "gr_missing_in_transit", "wait", "no receipt yet; shipping notice inside the window"
    elif feats["n_unreadable"]:
        code, step, ev = "unreadable_field", "investigate", "could not read: " + ", ".join(feats["unreadable"][:4])
    else:
        code, step, ev = "none", "pay", "all checks passed on readable fields"
    return dict(model=model, action=action, model_action=None, risk=risk, at_risk_usd=at_risk, reason_code=code,
                next_step=step, evidence=ev, features=feats, read=read2 if (issues or feats["n_unreadable"]) and read2 else read,
                issues=[{"code": c, "next_step": n, "detail": d} for c, n, d in issues],
                anomalies=(supplier_history.anomalies(case, read2 or read, wiki_full.get("history"), wiki["items"]) if with_wiki else None),
                dial=dial.explain(risk, at_risk, wiki_full, policy), **stats)
