"""Domain expert: normalization, cross-document checks, chain-break diagnosis, dollars at risk. Pure code."""
import re
from .packet import days_between

OCR = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5"})

def num(x):
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    # OCR fixes (O->0, l->1, S->5) apply only inside tokens that contain a digit, so "USD" or "EUR" never become numbers.
    toks = [t.translate(OCR) for t in str(x).split() if re.search(r"\d", t)]
    s = re.sub(r"[^\d,.\-]", "", " ".join(toks))
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        tail = s.split(",")[-1]
        s = s.replace(",", ".") if len(tail) == 2 else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None

def ref(x):
    if x is None:
        return None
    d = re.sub(r"\D", "", str(x).translate(OCR))
    return d.lstrip("0") or None

SKU_OCR = str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"})

def norm_sku(x):
    """Same OCR folding on both sides, so 'CW-CSE-IP15R' and 'CW-CSE-IPI5R' compare equal."""
    return re.sub(r"[^A-Z0-9]", "", str(x or "").upper()).translate(SKU_OCR) or None

def pack_size(uom, qty_text, sku, wiki_items):
    """EA per unit of `uom`. Explicit text like '(12 EA)' first, then wiki conversions, else None."""
    u = (uom or "EA").upper().strip()
    if u in ("EA", "EACH", "PC", "PCS", "UNIT", "UNITS", ""):
        return 1.0
    if wiki_items is not None:
        for it in wiki_items:
            if norm_sku(it.get("sku")) == norm_sku(sku):
                conv = it.get("pack_conversions") or it.get("packs") or it.get("conversions") or {}
                if isinstance(conv, dict):
                    for k, v in conv.items():
                        if k.upper() == u and num(v):
                            return num(v)
                elif isinstance(conv, list):
                    for c in conv:
                        if str(c.get("unit", c.get("uom", ""))).upper() == u:
                            n = num(c.get("ea", c.get("qty", c.get("each"))))
                            if n: return n
    return None

def explicit_ea(qty_text):
    # Fix OCR letters inside number-like tokens first, so "l,896 EA" reads as 1896 and not 896.
    t = " ".join(tok.translate(OCR) if re.search(r"\d", tok) else tok for tok in str(qty_text or "").split())
    m = re.search(r"(\d[\d.,]*)\s*(?:EA|EACH|PCS?)\b", t.upper())
    return num(m.group(1)) if m else None

def line_ea(line, qty_key, sku, wiki_items):
    q = num(line.get(qty_key))
    ex = explicit_ea(line.get("qty_text"))
    if ex is not None and (line.get("uom") or "EA").upper() not in ("EA", "EACH"):
        return ex
    if q is None:
        return None
    ps = pack_size(line.get("uom"), line.get("qty_text"), sku, wiki_items)
    return q * ps if ps else None

def by_sku(lines):
    out = {}
    for i, l in enumerate(lines or []):
        out[norm_sku(l.get("sku")) or f"#{i}"] = l
    return out

def _first_number(text):
    m = re.search(r"[\dOolIS][\dOolIS.,]*", str(text or ""))
    return num(m.group(0)) if m and re.search(r"\d", m.group(0)) else None

def recover(read):
    """Where the model returned null but copied the raw text, parse it in code (e.g. 'l,896 EA' -> 1896)."""
    fixed = []
    for doc, qk in (("po", "qty"), ("invoice", "qty"), ("gr", "qty_received"), ("shipping_notice", "qty_shipped")):
        d = (read or {}).get(doc) or {}
        for i, ln in enumerate(d.get("lines") or []):
            if ln.get(qk) is None and ln.get("qty_text"):
                v = explicit_ea(ln["qty_text"]) or _first_number(ln["qty_text"])
                if v is not None:
                    ln[qk] = v; fixed.append(f"{doc}.lines[{i}].{qk}")
            for vk, tk in (("unit_price", "price_text"), ("amount", "amount_text")):
                if vk in ln or tk in ln:
                    if ln.get(vk) is None and ln.get(tk):
                        v = _first_number(ln[tk])
                        if v is not None:
                            ln[vk] = v; fixed.append(f"{doc}.lines[{i}].{vk}")
    if fixed and read.get("unreadable"):
        read["unreadable"] = [u for u in read["unreadable"] if not any(u.startswith(f.rsplit(".", 1)[0]) and u.endswith(f.rsplit(".", 1)[1]) for f in fixed)]
    return fixed

def analyze(read, case, wiki, policy):
    """Return (issues, features, at_risk_usd, wait). wiki is None for the no-wiki row."""
    recovered = recover(read or {})
    tol = float((policy or {}).get("price_tolerance", 0.01))
    window = int((policy or {}).get("in_transit_window_days", 10))
    items = wiki["items"] if wiki else None
    po, asn, gr, inv = (read or {}).get("po") or {}, (read or {}).get("shipping_notice"), (read or {}).get("gr"), (read or {}).get("invoice") or {}
    # Only decision-critical values count as unreadable: quantities, prices, amounts, references, invoice number, dates.
    # The invoice total is derived from the line amounts, so an unreadable total only matters if the lines are unreadable too.
    CRIT = ("qty", "price", "amount", "po_ref", "po_number", "invoice_number", "ship_date")
    unreadable = [u for u in ((read or {}).get("unreadable") or []) if any(k in str(u).lower() for k in CRIT)]
    _inv = (read or {}).get("invoice") or {}
    if _inv.get("total") is None and not all(num(l.get("amount")) is not None for l in _inv.get("lines") or [{}]):
        unreadable.append("invoice.total")
    issues, risk_usd = [], 0.0
    inv_total = num(inv.get("total")) or sum(num(l.get("amount")) or 0 for l in inv.get("lines") or [])

    # References and duplicates
    po_ref, inv_ref = ref(po.get("po_number")), ref(inv.get("po_ref"))
    gr_ref = ref(gr.get("po_ref")) if gr else None
    if inv_ref is None or po_ref is None:
        unreadable.append("invoice.po_ref" if inv_ref is None else "po.po_number")
    elif inv_ref != po_ref:
        issues.append(("wrong_po", "investigate", f"invoice cites PO {inv_ref}, goods ordered on PO {po_ref}"))
        risk_usd = max(risk_usd, inv_total or 0)
    hist = case.get("billing_history") or []
    inv_no = re.sub(r"[^A-Z0-9]", "", str(inv.get("invoice_number") or "").upper().translate(OCR))
    if inv_no and any(re.sub(r"[^A-Z0-9]", "", str(h.get("invoice_number", "")).upper().translate(OCR)) == inv_no for h in hist):
        issues.append(("duplicate_invoice", "investigate", f"invoice {inv.get('invoice_number')} already paid"))
        risk_usd = max(risk_usd, inv_total or 0)

    # Missing receipt: in transit or not
    wait = False
    if not gr:
        sd = asn.get("ship_date") if asn else None
        d = days_between(sd, case.get("as_of_date")) if sd else None
        if asn and d is not None and 0 <= d <= window:
            wait = True
        else:
            issues.append(("qty_mismatch", "investigate", "no goods receipt and no recent shipping notice"))
            risk_usd = max(risk_usd, inv_total or 0)

    po_l, inv_l = by_sku(po.get("lines")), by_sku(inv.get("lines"))
    asn_l = by_sku(asn.get("lines")) if asn else {}
    gr_l = by_sku(gr.get("lines")) if gr else {}
    billed_before = {}
    for h in hist:
        for hl in h.get("lines") or []:
            billed_before[norm_sku(hl.get("sku"))] = billed_before.get(norm_sku(hl.get("sku")), 0) + (num(hl.get("qty")) or 0)

    for sku, il in inv_l.items():
        pl = po_l.get(sku)
        if not pl:
            unreadable.append(f"po.line.{sku}")
            continue
        inv_ea = line_ea(il, "qty", sku, items)
        po_ea = line_ea(pl, "qty", sku, items)
        if inv_ea is None:
            unreadable.append(f"invoice.qty.{sku}"); continue
        po_unit = num(pl.get("unit_price"))
        if po_unit is not None and po_ea and num(pl.get("qty")):
            po_unit_ea = po_unit * num(pl.get("qty")) / po_ea
        else:
            po_unit_ea = po_unit
        amt = num(il.get("amount"))
        inv_unit_ea = (amt / inv_ea) if (amt and inv_ea) else None
        if inv_unit_ea is None and num(il.get("unit_price")) is not None:
            ps = (num(il.get("qty")) and inv_ea / num(il.get("qty"))) or 1
            inv_unit_ea = num(il.get("unit_price")) / ps
        if po_unit_ea is None or inv_unit_ea is None:
            unreadable.append(f"price.{sku}")
        elif inv_unit_ea > po_unit_ea * (1 + tol) + 1e-9:
            issues.append(("price_mismatch", "dispute_with_supplier", f"{sku} billed {inv_unit_ea:.2f}/EA vs PO {po_unit_ea:.2f}/EA"))
            risk_usd = max(risk_usd, (inv_unit_ea - po_unit_ea) * inv_ea)
        remaining = (po_ea - billed_before.get(sku, 0)) if po_ea is not None else None
        if gr:
            gl = gr_l.get(sku)
            gr_ea = line_ea(gl, "qty_received", sku, items) if gl else None
            if gr_ea is None:
                unreadable.append(f"gr.qty.{sku}"); continue
            if inv_ea > gr_ea + 1e-9:
                al = asn_l.get(sku)
                shipped = line_ea(al, "qty_shipped", sku, items) if al else None
                if shipped is not None and abs(shipped - inv_ea) < 1e-9:
                    code, step, leg = "lost_in_transit", "claim_from_carrier", "carrier"
                elif shipped is not None and abs(shipped - gr_ea) < 1e-9:
                    code, step, leg = "short_shipped", "dispute_with_supplier", "supplier"
                else:
                    code, step, leg = "qty_mismatch", "investigate", "unknown"
                issues.append((code, step, f"{sku}: billed {inv_ea:g}, received {gr_ea:g}" + (f", shipped {shipped:g}" if shipped is not None else "")))
                risk_usd = max(risk_usd, (inv_ea - gr_ea) * (po_unit_ea or inv_unit_ea or 0))
        if remaining is not None and inv_ea > remaining + 1e-9 and not any(i[0] == "duplicate_invoice" for i in issues):
            issues.append(("qty_mismatch", "investigate", f"{sku}: billed {inv_ea:g} but only {remaining:g} left on the PO"))
            risk_usd = max(risk_usd, (inv_ea - remaining) * (po_unit_ea or 0))

    arith_off = 0
    for il in inv.get("lines") or []:
        q, p, a = num(il.get("qty")), num(il.get("unit_price")), num(il.get("amount"))
        if q and p and a and abs(q * p - a) > max(0.02, 0.005 * a):
            arith_off += 1
    features = {"recovered_from_text": recovered, "n_issues": len(issues), "unreadable": sorted(set(unreadable)), "n_unreadable": len(set(unreadable)),
                "arith_off": arith_off, "wait": wait, "codes": [i[0] for i in issues]}
    if (issues or unreadable) and not risk_usd:
        # Unknown dollar amount on a flagged invoice: fall back to the invoice total from the text; the dial fails closed if still unknown.
        risk_usd = inv_total or invoice_total_from_text((case.get("documents") or {}).get("invoice")) or 0.0
    if not issues and unreadable:
        risk_usd = max(risk_usd, inv_total or 0)
    return issues, features, round(risk_usd, 2), wait


def invoice_total_from_text(text):
    """Best-effort invoice total from the invoice text, before any model call. None if not found."""
    best = None
    for line in str(text or "").splitlines():
        if re.search(r"total|amount due|balance due|due", line, re.I):
            for tok in re.findall(r"[\d][\d.,OolIS]*\d", line):
                v = num(tok)
                if v is not None and (best is None or v > best):
                    best = v
    return best
