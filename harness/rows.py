"""The four rows. Each returns one prediction dict (see docs/work-split.md)."""
import json, math
from . import client, prompts, packet, domain, dial

def _acc(stats, model, r):
    ti, to, c = client.usage_cost(model, r)
    stats["calls"] += 1  # counted even when served from the shared cache, so per-row cost is complete
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

def alone(case, model, use_images, frontier):
    stats = dict(calls=0, tokens_in=0, tokens_out=0, cost_usd=0.0, latency_ms=0)
    wiki, policy = packet.load_wiki(case)
    pages = {"supplier": wiki["supplier"], "items": wiki["items"]}
    content = [{"type": "text", "text": prompts.ALONE + "\n\n" + packet.context_text(case, pages, policy)}] + packet.document_parts(case, use_images)
    r = client.chat(model, [{"role": "user", "content": content}], max_tokens=4000 if not frontier else 600, logprobs=frontier)
    _acc(stats, model, r)
    j = client.parse_json(client.content(r)) or {}
    model_action = str(j.get("action", "")).upper() or None
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
    docs = packet.document_parts(case, use_images)
    # 1. Reading expert. Identical request in both harness rows, so the disk cache shares it.
    r = client.chat(model, [{"role": "user", "content": [{"type": "text", "text": prompts.READ}] + docs}], max_tokens=6000)
    _acc(stats, model, r)
    read = client.parse_json(client.content(r)) or {}
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
                dial=dial.explain(risk, at_risk, wiki_full, policy), **stats)
