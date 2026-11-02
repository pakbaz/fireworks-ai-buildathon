"""Checker: recompute every label from the gold records and re-derive rendered values from the text.

python3 -I generator/check.py            # checks data/*.jsonl, wiki/, images, manifest
Exits non-zero on any failure.
"""
import collections
import datetime
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from world import (SPLITS, REASONS, NEXT_STEP, LEG, NOISE_TYPES, TEST_ONLY_SUPPLIER, SUPPLIERS,  # noqa: E402
                   WIKI_SUPPLIER_PAGES, EXPIRED_PAGE, POISONED_PAGE, POISON_TEXT)
from generate import stratum_counts  # noqa: E402

FAIL = []
UNDO = str.maketrans({"O": "0", "l": "1", "I": "1", "S": "5"})
CONF = set("OlIS")
MONTHS = {m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
                                          "Sep", "Oct", "Nov", "Dec"])}


def fail(cid, msg):
    FAIL.append("%s: %s" % (cid, msg))


def load_json(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f)


POLICY = load_json("wiki/policy.json")
TOL = POLICY["price_tolerance"]
WINDOW = POLICY["in_transit_window_days"]
ITEM_PAGES = {}
for fn in os.listdir(os.path.join(ROOT, "wiki", "items")):
    p = load_json("wiki/items/" + fn)
    ITEM_PAGES[p["sku"]] = p


def cents(x):
    return int(round(x * 100))


# ------------------------------------------------------------ parsing rendered values

def n_conf(s):
    return sum(1 for ch in s if ch in CONF)


def parse_number(s, money):
    s = s.translate(UNDO)
    if not re.fullmatch(r"[\d.,]+", s):
        raise ValueError("bad number %r" % s)
    if money:
        m = re.fullmatch(r"([\d.,]*\d)[.,](\d\d)", s)
        if not m:
            raise ValueError("bad money %r" % s)
        whole = re.sub(r"[.,]", "", m.group(1))
        return int(whole) * 100 + int(m.group(2))
    return int(re.sub(r"[.,]", "", s))


def parse_money_tok(t, sku):
    """-> (cents per EA, confusables)"""
    s = t.strip()
    uom = "EA"
    m = re.search(r"/(CS|BX)$", s)
    if m:
        uom = m.group(1)
        s = s[:m.start()]
    s = re.sub(r"^(USD|US\$|\$)\s*", "", s)
    s = re.sub(r"\s*(USD|\$)$", "", s)
    conf = n_conf(s)
    v = parse_number(s, True)
    if uom != "EA":
        size = ITEM_PAGES[sku]["pack_conversions"][uom]
        if v % size:
            raise ValueError("pack price not divisible")
        v //= size
    return v, conf


def parse_qty_tok(t, sku):
    m = re.fullmatch(r"([\dOlIS.,]+) (EA|CS|BX)(?: \(([\dOlIS.,]+) EA\))?", t.strip())
    if not m:
        raise ValueError("bad qty %r" % t)
    conf = n_conf(m.group(1)) + (n_conf(m.group(3)) if m.group(3) else 0)
    n = parse_number(m.group(1), False)
    if m.group(2) != "EA":
        n *= ITEM_PAGES[sku]["pack_conversions"][m.group(2)]
        if m.group(3) and parse_number(m.group(3), False) != n:
            raise ValueError("pack paren disagrees %r" % t)
    return n, conf


def parse_gr_qty(t, sku):
    hw = re.search(r"\[handwritten: '([^']*)'\]", t)
    if hw:
        m = re.search(r"\d+", hw.group(1))
        return int(m.group(0)), 0, re.search(r"\[struck-out: ([^\]]*)\]", t)
    q, c = parse_qty_tok(t, sku)
    return q, c, None


def parse_po_ref(t):
    m = re.fullmatch(r"(?:PO-|#|P\.O\. )?([\dOlIS]+)", t.strip())
    if not m:
        raise ValueError("bad po ref %r" % t)
    return int(m.group(1).translate(UNDO)), n_conf(m.group(1))


def parse_date(t):
    t = t.strip()
    for f in ("%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.datetime.strptime(t, f).date().isoformat()
        except ValueError:
            pass
    m = re.fullmatch(r"(\d{1,2}) ([A-Z][a-z]{2}) (\d{4})", t)
    if m:
        return datetime.date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))).isoformat()
    m = re.fullmatch(r"(\d{2})-([A-Z]{3}) ?-(\d{2})|(\d{2})-([A-Z]{3})-(\d{2})", t)
    if m:
        g = [x for x in m.groups() if x]
        return datetime.date(2000 + int(g[2]), MONTHS[g[1].title()], int(g[0])).isoformat()
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{2})", t)  # EU d/m/y, day > 12
    if m and int(m.group(1)) > 12:
        return datetime.date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", t)  # US m/d/Y, day > 12
    if m and int(m.group(2)) > 12:
        return datetime.date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()
    raise ValueError("bad/ambiguous date %r" % t)


def id_equiv(text, gold):
    if len(text) != len(gold):
        return False, 99
    diff = sum(a != b for a, b in zip(text, gold))
    return text.translate(UNDO) == gold.translate(UNDO) or all(
        a == b or a.translate(UNDO) == b.translate(UNDO) for a, b in zip(text, gold)), diff


# ------------------------------------------------------------ token re-derivation

def line_of(lines, sku):
    for l in lines:
        if l["sku"] == sku:
            return l
    raise KeyError(sku)


def expected_value(g, tok):
    d, f, sku = tok["doc"], tok["field"], tok["sku"]
    doc = g[d]
    if f in ("po_number", "po_ref"):
        return int(doc["po_number"].split("-")[1])
    if f in ("po_date", "ship_date", "received_date", "invoice_date", "due_date"):
        return doc[f]
    if f in ("asn_number", "invoice_number"):
        return doc[f]
    if f == "sku":
        return sku
    if f in ("total", "subtotal"):
        return cents(doc[f])
    ln = line_of(doc["lines"], sku)
    if f in ("unit_price", "amount"):
        return cents(ln[f])
    return ln[f]  # qty, qty_shipped, qty_ordered, qty_received


EXPECTED_FIELDS = {
    "po": ["po_number", "po_date", "total"], "shipping_notice": ["asn_number", "ship_date", "po_ref"],
    "gr": ["received_date", "po_ref"], "invoice": ["invoice_number", "invoice_date", "due_date", "po_ref",
                                                   "subtotal", "total"]}
EXPECTED_LINE_FIELDS = {"po": ["sku", "qty", "unit_price", "amount"], "shipping_notice": ["sku", "qty_shipped"],
                        "gr": ["sku", "qty_ordered", "qty_received"],
                        "invoice": ["sku", "qty", "unit_price", "amount"]}


def check_tokens(c):
    cid, lab = c["case_id"], c["label"]
    g = lab["gold"]
    toks = lab["render_meta"]["tokens"]
    clean = lab["stratum"] == "clean"
    seen = collections.Counter()
    for t in toks:
        d = t["doc"]
        text = c["documents"].get(d)
        if text is None or t["text"] not in text:
            fail(cid, "token not in %s text: %r" % (d, t["text"]))
            continue
        seen[(d, t["field"], t["sku"])] += 1
        try:
            exp = expected_value(g, t)
            k = t["kind"]
            conf = 0
            if k == "money":
                v, conf = parse_money_tok(t["text"], t["sku"])
            elif k == "qty":
                v, conf = parse_qty_tok(t["text"], t["sku"])
            elif k == "gr_qty":
                v, conf, struck = parse_gr_qty(t["text"], t["sku"])
                if struck:
                    pv, _ = parse_qty_tok(struck.group(1), t["sku"])
                    if pv == v:
                        fail(cid, "struck-out qty equals handwritten qty")
            elif k == "po_ref":
                v, conf = parse_po_ref(t["text"])
            elif k == "date":
                v = parse_date(t["text"])
            elif k in ("id", "sku"):
                ok, conf = id_equiv(t["text"], exp)
                v = exp if ok else t["text"]
            else:
                raise ValueError("unknown kind " + k)
            if v != exp:
                fail(cid, "%s.%s(%s) rendered %r -> %r != gold %r" % (d, t["field"], t["sku"], t["text"], v, exp))
            if conf > 1:
                fail(cid, "more than one OCR swap in %s.%s: %r" % (d, t["field"], t["text"]))
            if clean:
                canon = {"money": r"\d{1,3}(,\d{3})*\.\d\d", "qty": r"\d{1,3}(,\d{3})* EA",
                         "gr_qty": r"\d{1,3}(,\d{3})* EA", "po_ref": r"PO-\d{6}",
                         "date": r"\d{4}-\d\d-\d\d"}.get(k)
                if canon and not re.fullmatch(canon, t["text"]):
                    fail(cid, "clean case has non-canonical %s %r" % (k, t["text"]))
                if k in ("id", "sku") and t["text"] != exp:
                    fail(cid, "clean case has OCR noise in %r" % t["text"])
        except (ValueError, KeyError) as e:
            fail(cid, "cannot re-derive %s.%s: %s" % (d, t["field"], e))
    # coverage: every decision-critical field rendered exactly once
    for d, fields in EXPECTED_FIELDS.items():
        if g[d] is None:
            continue
        for f in fields:
            if seen[(d, f, None)] != 1:
                fail(cid, "critical field %s.%s rendered %d times" % (d, f, seen[(d, f, None)]))
        for ln in g[d]["lines"]:
            for f in EXPECTED_LINE_FIELDS[d]:
                if seen[(d, f, ln["sku"])] != 1:
                    fail(cid, "critical line field %s.%s(%s) missing" % (d, f, ln["sku"]))


# ------------------------------------------------------------ label recomputation

def days(a, b):
    return (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days


def recompute(c):
    """Return (reason_codes set, at_risk_cents, in_transit bool, problems list) from gold only."""
    g = c["label"]["gold"]
    po, asn, gr, inv = g["po"], g["shipping_notice"], g["gr"], g["invoice"]
    hist, open_pos = g["billing_history"], g["open_pos"]
    reasons, probs = set(), []
    at_risk = 0
    inv_total = cents(inv["total"])

    basis = {l["sku"]: cents(l["unit_price"]) for l in po["lines"]}
    if inv["po_number"] != po["po_number"]:
        ref = [o for o in open_pos if o["po_number"] == inv["po_number"]]
        if len(ref) != 1:
            probs.append("invoice references unknown PO")
        else:
            reasons.add("wrong_po")
            at_risk = inv_total
            basis = {l["sku"]: cents(l["unit_price"]) for l in ref[0]["lines"]}
            if not any(abs(cents(l["unit_price"]) - cents(line_of(po["lines"], l["sku"])["unit_price"]))
                       >= 0.03 * cents(line_of(po["lines"], l["sku"])["unit_price"]) for l in inv["lines"]):
                probs.append("wrong_po without a >=3% price difference vs received PO")
    if gr is not None and gr["po_number"] != po["po_number"]:
        probs.append("receipt not booked against the PO")
    if asn is not None and asn["po_number"] != po["po_number"]:
        probs.append("ASN not against the PO")

    dup = [h for h in hist if h["invoice_number"].translate(UNDO) == inv["invoice_number"].translate(UNDO)]
    if dup:
        reasons.add("duplicate_invoice")
        at_risk = inv_total
        if len(dup) != 1 or dup[0]["status"] != "paid" or \
                sorted((l["sku"], l["qty"], cents(l["amount"])) for l in dup[0]["lines"]) != \
                sorted((l["sku"], l["qty"], cents(l["amount"])) for l in inv["lines"]):
            probs.append("duplicate entry does not repeat the invoice lines")

    price_lines = 0
    qty_lines = 0
    for il in inv["lines"]:
        sku = il["sku"]
        if cents(il["amount"]) != il["qty"] * cents(il["unit_price"]):
            probs.append("invoice line arithmetic")
        p, ip = basis[sku], cents(il["unit_price"])
        if abs(ip - p) > TOL * p:
            reasons.add("price_mismatch")
            price_lines += 1
            if abs(ip - p) < 0.03 * p:
                probs.append("price mutation near tolerance line")
            at_risk += (ip - p) * il["qty"]
        elif ip != p:
            probs.append("price drift on agreeing line")
        pl = line_of(po["lines"], sku)
        if pl["qty"] - pl["qty_previously_billed"] != pl["qty_open"]:
            probs.append("PO open qty inconsistent")
        if il["qty"] != pl["qty_open"]:
            probs.append("invoice qty != PO open qty")
        a = line_of(asn["lines"], sku)["qty_shipped"] if asn else None
        if gr is not None:
            gl = line_of(gr["lines"], sku)
            r = gl["qty_received"]
            if gl["qty_ordered"] != pl["qty_open"]:
                probs.append("GR ordered qty != PO open qty")
            if r > il["qty"]:
                probs.append("over-receipt")
            elif r < il["qty"]:
                qty_lines += 1
                at_risk += (il["qty"] - r) * ip
                if a is None:
                    reasons.add("qty_mismatch")
                elif a == r:
                    reasons.add("short_shipped")
                elif a == il["qty"]:
                    reasons.add("lost_in_transit")
                else:
                    probs.append("ASN qty matches neither receipt nor invoice")
            elif a is not None and a != il["qty"]:
                probs.append("ASN qty differs on an agreeing line")
        elif a is not None and a != il["qty"]:
            probs.append("in-transit ASN qty != invoice qty")
    if price_lines > 1 or qty_lines > 1:
        probs.append("mutation touches more than one line")
    if "wrong_po" in reasons or "duplicate_invoice" in reasons:
        at_risk = inv_total
    in_transit = False
    if gr is None:
        if asn is None:
            probs.append("no receipt and no shipping notice")
        else:
            dd = days(asn["ship_date"], c["as_of_date"])
            in_transit = 0 <= dd <= WINDOW
            if not in_transit:
                probs.append("no receipt and ship date outside window")
    return reasons, at_risk, in_transit, probs


def check_history(c):
    cid = c["case_id"]
    g = c["label"]["gold"]
    po, inv, hist = g["po"], g["invoice"], g["billing_history"]
    is_dup = c["label"]["reason_code"] == "duplicate_invoice"
    inv_lines = sorted((l["sku"], l["qty"]) for l in inv["lines"])
    inv_skus = {l["sku"] for l in inv["lines"]}
    prev = collections.Counter()
    for h in hist:
        if h["status"] != "paid":
            fail(cid, "history entry not paid")
        if h["invoice_date"] > c["as_of_date"]:
            fail(cid, "history entry after as_of")
        same_no = h["invoice_number"].translate(UNDO) == inv["invoice_number"].translate(UNDO)
        if same_no:
            if not is_dup:
                fail(cid, "non-duplicate case has its invoice number in history")
            continue
        if sorted((l["sku"], l["qty"]) for l in h["lines"]) == inv_lines:
            fail(cid, "history entry repeats the invoice lines under another number (implies double billing)")
        if h["po_number"] == po["po_number"]:
            for l in h["lines"]:
                prev[l["sku"]] += l["qty"]
                if cents(l["amount"]) != l["qty"] * cents(line_of(po["lines"], l["sku"])["unit_price"]):
                    fail(cid, "prior partial invoice priced off-PO")
        else:
            if set(l["sku"] for l in h["lines"]) & inv_skus:
                fail(cid, "unrelated history entry shares a SKU with the invoice")
    for pl in po["lines"]:
        if prev[pl["sku"]] != pl["qty_previously_billed"]:
            fail(cid, "PO previously-billed qty (%d) != paid history on this PO (%d)"
                 % (pl["qty_previously_billed"], prev[pl["sku"]]))
        if pl["qty_previously_billed"] + pl["qty_open"] != pl["qty"]:
            fail(cid, "PO ordered != previously billed + open")
        if pl["qty_previously_billed"] and pl["qty_previously_billed"] == pl["qty_open"]:
            fail(cid, "partial delivery equals current delivery (looks like a re-bill)")
        if pl["qty_previously_billed"]:
            if po["prior_invoice"] is None or po["prior_invoice"] not in c["documents"]["po"]:
                fail(cid, "PO does not state prior invoice for partial delivery")
            if "open balance" not in c["documents"]["po"]:
                fail(cid, "PO does not state open balance")


def check_case(c, split):
    cid, lab = c["case_id"], c["label"]
    g = lab["gold"]
    for k in ("case_id", "split", "company", "supplier_id", "as_of_date", "documents", "billing_history",
              "wiki_refs", "template_ids", "heldout", "label"):
        if k not in c:
            fail(cid, "missing key " + k)
    if c["split"] != split:
        fail(cid, "split field")
    st = lab["stratum"]
    for d in ("po", "shipping_notice", "gr", "invoice"):
        if (c["documents"][d] is None) != (g[d] is None):
            fail(cid, "document/gold presence mismatch for " + d)
        if (c["template_ids"][d] is None) != (g[d] is None):
            fail(cid, "template presence mismatch for " + d)
    if c["documents"]["po"] is None or c["documents"]["invoice"] is None:
        fail(cid, "PO and invoice must be present")
    if c["billing_history"] != g["billing_history"]:
        fail(cid, "billing_history differs from gold")
    if c.get("open_pos", []) != g["open_pos"]:
        fail(cid, "open_pos differs from gold")

    reasons, at_risk, in_transit, probs = recompute(c)
    for p in probs:
        fail(cid, p)
    code = lab["reason_code"]
    if st in ("clean", "messy"):
        if reasons or g["gr"] is None or code != "none":
            fail(cid, "%s case does not agree: %s" % (st, sorted(reasons)))
    elif st == "real":
        if reasons != {code} or code not in REASONS:
            fail(cid, "real case reasons %s != label %s" % (sorted(reasons), code))
        if code == "short_shipped" and g["shipping_notice"] is None:
            fail(cid, "short_shipped without ASN")
        if code == "qty_mismatch" and g["shipping_notice"] is not None:
            fail(cid, "qty_mismatch with ASN")
    elif st == "in_transit":
        if not in_transit or reasons or code != "gr_missing_in_transit" or g["gr"] is not None:
            fail(cid, "in_transit case invalid")
        if c["documents"]["gr"] is not None:
            fail(cid, "in_transit case has a receipt document")
    else:
        fail(cid, "unknown stratum")
    if lab["real_discrepancy"] != (st == "real"):
        fail(cid, "real_discrepancy flag")
    if lab["next_step"] != NEXT_STEP.get(code) or lab["leg"] != LEG.get(code):
        fail(cid, "next_step/leg inconsistent with reason")
    exp_risk = at_risk if st == "real" else 0
    if cents(lab["at_risk_usd"]) != exp_risk:
        fail(cid, "at_risk %s != recomputed %s" % (lab["at_risk_usd"], exp_risk / 100))
    if st == "real" and exp_risk <= 0:
        fail(cid, "real case with zero at-risk")

    # dates
    po, asn, gr, inv = g["po"], g["shipping_notice"], g["gr"], g["invoice"]
    seq = [po["po_date"]] + ([asn["ship_date"]] if asn else []) + ([gr["received_date"]] if gr else [])
    if seq != sorted(seq) or seq[-1] > c["as_of_date"] or inv["invoice_date"] > c["as_of_date"]:
        fail(cid, "date order")
    # arithmetic of gold
    if cents(po["total"]) != sum(cents(l["amount"]) for l in po["lines"]):
        fail(cid, "PO total arithmetic")
    if cents(inv["subtotal"]) != sum(cents(l["amount"]) for l in inv["lines"]) or \
            cents(inv["total"]) != cents(inv["subtotal"]) + cents(inv["tax"]):
        fail(cid, "invoice total arithmetic")
    for l in po["lines"]:
        if cents(l["amount"]) != l["qty"] * cents(l["unit_price"]):
            fail(cid, "PO line arithmetic")

    check_history(c)

    # noise
    nt = lab["noise_types"]
    if any(t not in NOISE_TYPES for t in nt) or len(set(nt)) != len(nt):
        fail(cid, "bad noise types")
    lo, hi = {"clean": (0, 0), "messy": (2, 4), "real": (0, 2), "in_transit": (0, 2)}[st]
    if not lo <= len(nt) <= hi:
        fail(cid, "noise count %d outside [%d,%d]" % (len(nt), lo, hi))
    hw = lab["render_meta"]["handwriting"]
    if "handwritten_note" not in nt and code != "lost_in_transit" and hw:
        fail(cid, "handwriting present without handwritten_note noise")
    if st == "clean":
        for d, t in c["documents"].items():
            if t and ("[handwritten" in t or "[struck-out" in t):
                fail(cid, "clean case has handwriting")
    if "handwritten_note" in nt and not any(t and "[handwritten" in t for t in c["documents"].values()):
        fail(cid, "handwritten_note noise not visible")
    for sku, spec in hw.items():
        gl = line_of(g["gr"]["lines"], sku)
        if spec["variant"] == "struck" and spec["printed"] == gl["qty_received"]:
            fail(cid, "struck-out printed qty equals true qty")
    check_tokens(c)

    # wiki refs
    refs = c["wiki_refs"]
    sid = c["supplier_id"]
    if (refs["supplier"] is not None) != (sid in WIKI_SUPPLIER_PAGES):
        fail(cid, "supplier wiki ref presence")
    for p in [refs["supplier"], refs["policy"]] + refs["items"]:
        if p and not os.path.exists(os.path.join(ROOT, p)):
            fail(cid, "missing wiki page " + p)
    if sorted(refs["items"]) != sorted("wiki/items/%s.json" % l["sku"] for l in inv["lines"]):
        fail(cid, "item refs")
    # heldout
    t4 = any(v and v.endswith("_t4") for v in c["template_ids"].values())
    if c["heldout"]["template"] != t4 or c["heldout"]["supplier"] != (sid == TEST_ONLY_SUPPLIER):
        fail(cid, "heldout flags")
    if split != "test" and (t4 or sid == TEST_ONLY_SUPPLIER):
        fail(cid, "test-only template/supplier in " + split)
    if c["company"] not in SUPPLIERS[sid]["companies"]:
        fail(cid, "supplier does not serve company")
    # images
    ims = c.get("images")
    if ims:
        if split != "test":
            fail(cid, "images outside test")
        for d, p in ims.items():
            if c["documents"].get(d) is None:
                fail(cid, "image for absent doc " + d)
            if not os.path.exists(os.path.join(ROOT, p)):
                fail(cid, "missing image " + p)
        if set(ims) != {d for d, t in c["documents"].items() if t}:
            fail(cid, "image set != present docs")


def check_split(split):
    path = os.path.join(ROOT, "data", split + ".jsonl")
    cases = [json.loads(l) for l in open(path, encoding="utf-8")]
    n = SPLITS[split]["size"]
    if len(cases) != n:
        fail(split, "size %d != %d" % (len(cases), n))
    if len({c["case_id"] for c in cases}) != len(cases):
        fail(split, "duplicate case ids")
    for c in cases:
        check_case(c, split)
    c_exp, r_exp = stratum_counts(n)
    st = collections.Counter(c["label"]["stratum"] for c in cases)
    rs = collections.Counter(c["label"]["reason_code"] for c in cases if c["label"]["stratum"] == "real")
    co = collections.Counter(c["company"] for c in cases)
    if dict(st) != c_exp:
        fail(split, "stratum counts %s != %s" % (dict(st), c_exp))
    if dict(rs) != r_exp:
        fail(split, "reason counts %s != %s" % (dict(rs), r_exp))
    if co["northside"] != n // 2 or co["caseworks"] != n // 2:
        fail(split, "company split %s" % dict(co))
    for s in c_exp:
        sc = collections.Counter(c["company"] for c in cases if c["label"]["stratum"] == s)
        if abs(sc["northside"] - sc["caseworks"]) > 1:
            fail(split, "company imbalance in stratum %s: %s" % (s, dict(sc)))
    if split == "test":
        held = sum(1 for c in cases if c["heldout"]["template"] or c["heldout"]["supplier"])
        if not 0.15 * n <= held <= 0.25 * n:
            fail(split, "heldout share %d" % held)
        ims = [c for c in cases if c.get("images")]
        if len(ims) != 100:
            fail(split, "image cases %d != 100" % len(ims))
        isc = collections.Counter(c["label"]["stratum"] for c in ims)
        if any(isc[s] != 25 for s in c_exp):
            fail(split, "image strata %s" % dict(isc))
        if not any("[struck-out" in (c["documents"]["gr"] or "") for c in ims):
            fail(split, "no image case with a struck-out receipt qty")
    return cases


def check_wiki():
    sup_pages = os.listdir(os.path.join(ROOT, "wiki", "suppliers"))
    ids = sorted(p[:-5] for p in sup_pages)
    if ids != sorted(WIKI_SUPPLIER_PAGES):
        fail("wiki", "supplier pages %s" % ids)
    frac = len(ids) / len(SUPPLIERS)
    if not 0.6 <= frac <= 0.8:
        fail("wiki", "supplier page share %.2f" % frac)
    expired = [i for i in ids if load_json("wiki/suppliers/%s.json" % i)["expires"] < "2025-01-01"]
    poisoned = [i for i in ids if POISON_TEXT in json.dumps(load_json("wiki/suppliers/%s.json" % i))]
    if expired != [EXPIRED_PAGE] or poisoned != [POISONED_PAGE]:
        fail("wiki", "expired %s poisoned %s" % (expired, poisoned))
    for i in ids:
        p = load_json("wiki/suppliers/%s.json" % i)
        if p["past_problem_rate"].get("synthetic") is not True:
            fail("wiki", "past_problem_rate not marked synthetic")
        for k in ("aliases", "sites", "po_ref_style", "number_format", "handwritten_qty_authoritative",
                  "lead_days", "layout_notes", "author", "approved_by", "version", "expires"):
            if k not in p:
                fail("wiki", "%s missing %s" % (i, k))
    want = {"price_tolerance": 0.01, "in_transit_window_days": 10, "review_cost_usd": 10,
            "category_weights": {"medical_device": 25, "medical_consumable": 3, "consumer": 1},
            "supplier_weight_range": [0.5, 2], "overrides": {}}
    for k, v in want.items():
        if POLICY.get(k) != v:
            fail("wiki", "policy %s" % k)


def check_manifest():
    p = os.path.join(ROOT, "data", "manifest.json")
    if not os.path.exists(p):
        fail("manifest", "missing")
        return
    m = load_json("data/manifest.json")
    for f, info in m["files"].items():
        fp = os.path.join(ROOT, f)
        if not os.path.exists(fp):
            fail("manifest", "missing " + f)
            continue
        h = hashlib.sha256(open(fp, "rb").read()).hexdigest()
        if h != info["sha256"]:
            fail("manifest", "hash mismatch " + f)
    for s in ("data/train.jsonl", "data/dev.jsonl", "data/test.jsonl"):
        if s not in m["files"]:
            fail("manifest", "no hash for " + s)


def main():
    check_wiki()
    for s in ("train", "dev", "test"):
        check_split(s)
    check_manifest()
    if FAIL:
        print("CHECK FAILED: %d problems" % len(FAIL))
        for f in FAIL[:60]:
            print("  " + f)
        sys.exit(1)
    print("CHECK PASSED: wiki, %s, manifest" % ", ".join(
        "%s=%d" % (s, SPLITS[s]["size"]) for s in SPLITS))


if __name__ == "__main__":
    main()
