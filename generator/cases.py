"""Build one case: structured gold records, the mutation, billing context, noise, rendered text, label."""
import datetime
import math
import random

from world import (COMPANIES, ITEMS, SUPPLIERS, TEMPLATES, TEST_ONLY_TEMPLATES, TEST_ONLY_SUPPLIER,
                   BASE_SUPPLIERS, DOC_TYPES, NEXT_STEP, LEG, WIKI_SUPPLIER_PAGES)
from noise import po_str, choose_noise_types, build_noise_cfg
from templates import render_document

AS_OF_START = datetime.date(2025, 3, 1)
AS_OF_END = datetime.date(2026, 10, 30)
CARRIERS = ["UPS Freight", "FedEx Ground", "XPO Logistics", "Old Dominion", "DHL Express", "Estes Express"]
OCR_CLASS = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5"})
LOST_NOTES = ["rcvd {q}, box crushed {c}", "only {q} rcvd - 1 ctn damaged {c}", "rcvd {q}, pallet wrap torn {c}"]
LOST_REMARKS = ["box crushed", "1 ctn damaged, refused", "carton open on arrival"]


def ocr_key(s):
    return s.translate(OCR_CLASS)


def c2f(c):
    return round(c / 100.0, 2)


def wchoice(rng, weights):
    keys = sorted(weights)
    return rng.choices(keys, [weights[k] for k in keys])[0]


class SplitState:
    """Uniqueness bookkeeping within one split."""
    def __init__(self):
        self.po_numbers = set()
        self.inv_keys = set()

    def new_po(self, rng, avoid=()):
        while True:
            n = rng.randint(1000, 99999)
            if n in self.po_numbers:
                continue
            # keep every PO number in a case at least 2 digits apart from the others
            if any(sum(a != b for a, b in zip("%06d" % n, "%06d" % m)) < 2 for m in avoid):
                continue
            self.po_numbers.add(n)
            return n

    def new_invoice(self, rng, sid, yy):
        fmt = SUPPLIERS[sid]["inv_fmt"]
        while True:
            s = fmt.format(n4="%04d" % rng.randint(1, 9999), n5="%05d" % rng.randint(1, 99999),
                           n6="%06d" % rng.randint(1, 999999), n7="%07d" % rng.randint(1000000, 9999999),
                           yy="%02d" % yy)
            k = ocr_key(s)
            if k not in self.inv_keys:
                self.inv_keys.add(k)
                return s


def gen_qty(rng, sku, mutable=False):
    it = ITEMS[sku]
    cat, pack = it["category"], it["pack"]
    if cat == "medical_device":
        return rng.randint(2 if mutable else 1, 6)
    lo, hi = (10, 500) if cat == "medical_consumable" else (100, 5000)
    if pack and rng.random() < 0.75:
        size = pack["size"]
        return size * rng.randint(math.ceil(lo / size), hi // size)
    q = rng.randint(lo, hi)
    return q if cat == "medical_consumable" else max(lo, q - q % 10)


def gen_price(rng, sku):
    return int(round(ITEMS[sku]["unit_value_cents"] * rng.uniform(0.96, 1.04)))


def shift_price(rng, cents, lo=0.03, hi=0.12, up_only=False):
    """A price at least `lo` away from cents (never near the 1% tolerance line)."""
    f = rng.uniform(lo + 0.002, hi)
    if up_only or rng.random() < 0.5:
        new = math.ceil(cents * (1 + f))
        while (new - cents) * 100 < lo * 100 * cents:
            new += 1
    else:
        new = math.floor(cents * (1 - f))
        while (cents - new) * 100 < lo * 100 * cents:
            new -= 1
    return new


def short_amount(rng, sku, q):
    pack = ITEMS[sku]["pack"]
    if q <= 6:
        return rng.randint(1, q - 1)
    if pack and q % pack["size"] == 0 and q // pack["size"] >= 2 and rng.random() < 0.5:
        return pack["size"] * rng.randint(1, max(1, (q // pack["size"]) // 3))
    return rng.randint(1, max(1, int(q * 0.3)))


def build_case(split, seed, idx, case_id, company, stratum, reason, held_t, held_s, st):
    rng = random.Random(seed * 1000003 + idx)
    rng_ocr = random.Random(seed * 1000003 + idx + 500000000)

    # ---------------- supplier, dates
    if held_s:
        sid = TEST_ONLY_SUPPLIER
    else:
        sid = rng.choice([s for s in BASE_SUPPLIERS if company in SUPPLIERS[s]["companies"]])
    sup = SUPPLIERS[sid]
    co = COMPANIES[company]
    as_of = AS_OF_START + datetime.timedelta(days=rng.randint(0, (AS_OF_END - AS_OF_START).days))
    qty_mut = reason in ("short_shipped", "lost_in_transit", "qty_mismatch")
    # ~12% of cases are a second delivery on a PO whose first delivery was already invoiced and paid
    partial = reason not in ("duplicate_invoice", "wrong_po") and rng.random() < 0.12

    if stratum == "in_transit":
        days_since_ship = rng.randint(1, 8)
        ship = as_of - datetime.timedelta(days=days_since_ship)
        received = None
    else:
        received = as_of - datetime.timedelta(days=rng.randint(1, 20))
        ship = received - datetime.timedelta(days=max(1, sup["lead_days"] + rng.randint(-1, 2)))
    po_date = ship - datetime.timedelta(days=rng.randint(25, 45) if partial else rng.randint(3, 21))
    inv_date = ship + datetime.timedelta(days=rng.randint(0, 3))
    if inv_date > as_of:
        inv_date = as_of
    due = inv_date + datetime.timedelta(days=30)

    # ---------------- lines
    catalog = [s for s in sup["catalog"] if ITEMS[s]["company"] == company]
    n = min(len(catalog), rng.choices([1, 2, 3], [0.45, 0.35, 0.20])[0])
    skus = rng.sample(catalog, n)
    mut_i = rng.randrange(n)
    lines = []
    for i, sku in enumerate(skus):
        q = gen_qty(rng, sku, mutable=(qty_mut and i == mut_i))
        lines.append({"sku": sku, "open": q, "price": gen_price(rng, sku), "prior": 0})
    prior_inv = None
    if partial:
        for ln in lines:
            while True:
                pr = gen_qty(rng, ln["sku"])
                if pr != ln["open"]:
                    break
            ln["prior"] = pr
        prior_inv = st.new_invoice(rng, sid, (po_date.year % 100))
        prior_date = po_date + datetime.timedelta(days=rng.randint(4, 15))

    po_n = st.new_po(rng)
    sup_desc_i = BASE_SUPPLIERS.index(sid) % 2 + 1 if sid in BASE_SUPPLIERS else 2

    def desc(sku, supplier_doc):
        d = ITEMS[sku]["descriptions"]
        return d[min(sup_desc_i, len(d) - 1)] if supplier_doc else d[0]

    # ---------------- per-line quantities by document (all EA)
    shipped = [ln["open"] for ln in lines]
    recv = [ln["open"] for ln in lines]
    inv_qty = [ln["open"] for ln in lines]
    inv_price = [ln["price"] for ln in lines]
    mutation = None
    has_asn = {"short_shipped": True, "lost_in_transit": True, "qty_mismatch": False}.get(reason)
    if stratum == "in_transit":
        has_asn = True
    if has_asn is None:
        has_asn = rng.random() < 0.75

    m = lines[mut_i]
    if reason in ("short_shipped", "lost_in_transit", "qty_mismatch"):
        d = short_amount(rng, m["sku"], m["open"])
        recv[mut_i] = m["open"] - d
        if reason == "short_shipped":
            shipped[mut_i] = recv[mut_i]
        mutation = {"sku": m["sku"], "invoiced": inv_qty[mut_i], "received": recv[mut_i],
                    "shipped": shipped[mut_i] if has_asn else None}
    elif reason == "price_mismatch":
        inv_price[mut_i] = shift_price(rng, m["price"], up_only=True)
        mutation = {"sku": m["sku"], "po_price": c2f(m["price"]), "invoice_price": c2f(inv_price[mut_i])}

    open_pos = []
    inv_po = po_n
    if reason == "wrong_po":
        po_b = st.new_po(rng, avoid=[po_n])
        b_lines = []
        for i, ln in enumerate(lines):
            inv_price[i] = shift_price(rng, ln["price"])
            b_lines.append({"sku": ln["sku"], "qty": gen_qty(rng, ln["sku"]), "unit_price": c2f(inv_price[i])})
        open_pos.append({"po_number": po_str(po_b), "po_date": (po_date + datetime.timedelta(
            days=rng.randint(1, 10))).isoformat(), "supplier_id": sid, "status": "open", "lines": b_lines})
        inv_po = po_b
        mutation = {"invoice_po": po_str(po_b), "received_po": po_str(po_n)}
    if rng.random() < 0.3:
        for _ in range(rng.randint(1, 2)):
            pn = st.new_po(rng, avoid=[po_n] + [int(o["po_number"][3:]) for o in open_pos])
            ks = rng.sample(catalog, min(len(catalog), rng.randint(1, 2)))
            open_pos.append({"po_number": po_str(pn), "po_date": (as_of - datetime.timedelta(
                days=rng.randint(5, 40))).isoformat(), "supplier_id": sid, "status": "open",
                "lines": [{"sku": k, "qty": gen_qty(rng, k), "unit_price": c2f(gen_price(rng, k))} for k in ks]})
        rng.shuffle(open_pos)

    # ---------------- gold documents
    po_lines = []
    for i, ln in enumerate(lines):
        ordered = ln["open"] + ln["prior"]
        po_lines.append({"line": i + 1, "sku": ln["sku"], "description": desc(ln["sku"], False),
                         "qty": ordered, "qty_previously_billed": ln["prior"], "qty_open": ln["open"],
                         "uom": "EA", "unit_price": c2f(ln["price"]), "amount": c2f(ordered * ln["price"])})
    gold_po = {"po_number": po_str(po_n), "po_date": po_date.isoformat(), "revision": 2 if partial else 1,
               "prior_invoice": prior_inv, "company": company, "buyer": rng.choice(co["buyers"]),
               "supplier_id": sid, "supplier_name": sup["name"], "currency": "USD", "lines": po_lines,
               "total": c2f(sum((ln["open"] + ln["prior"]) * ln["price"] for ln in lines))}
    gold_asn = None
    if has_asn:
        gold_asn = {"asn_number": sup["asn_fmt"].format(n5="%05d" % rng.randint(1, 99999),
                                                        n6="%06d" % rng.randint(1, 999999)),
                    "po_number": po_str(po_n), "ship_date": ship.isoformat(), "ship_from": sup["sites"][0],
                    "carrier": rng.choice(CARRIERS), "tracking": "1Z%010d" % rng.randint(0, 9999999999),
                    "cartons": rng.randint(1, 3 + len(lines) * 4),
                    "lines": [{"sku": ln["sku"], "description": desc(ln["sku"], True), "qty_shipped": shipped[i],
                               "uom": "EA"} for i, ln in enumerate(lines)]}
    gold_gr = None
    if received is not None:
        gold_gr = {"gr_number": "%s-%06d" % (co["gr_prefix"], rng.randint(1, 999999)), "po_number": po_str(po_n),
                   "received_date": received.isoformat(), "received_by": rng.choice(co["clerks"]),
                   "dock": rng.randint(1, 6),
                   "lines": [{"sku": ln["sku"], "description": desc(ln["sku"], False), "qty_ordered": ln["open"],
                              "qty_received": recv[i], "uom": "EA"} for i, ln in enumerate(lines)]}
    inv_no = st.new_invoice(rng, sid, inv_date.year % 100)
    inv_lines = [{"line": i + 1, "sku": ln["sku"], "description": desc(ln["sku"], True), "qty": inv_qty[i],
                  "uom": "EA", "unit_price": c2f(inv_price[i]), "amount": c2f(inv_qty[i] * inv_price[i])}
                 for i, ln in enumerate(lines)]
    inv_total_c = sum(inv_qty[i] * inv_price[i] for i in range(len(lines)))
    gold_inv = {"invoice_number": inv_no, "invoice_date": inv_date.isoformat(), "due_date": due.isoformat(),
                "po_number": po_str(inv_po), "supplier_id": sid, "remit_to": sup["sites"][0], "currency": "USD",
                "lines": inv_lines, "subtotal": c2f(inv_total_c), "tax": 0.0, "total": c2f(inv_total_c)}

    # ---------------- billing history
    history = []
    if partial:
        history.append({"invoice_number": prior_inv, "po_number": po_str(po_n), "invoice_date": prior_date.isoformat(),
                        "lines": [{"sku": ln["sku"], "qty": ln["prior"], "amount": c2f(ln["prior"] * ln["price"])}
                                  for ln in lines], "status": "paid"})
    if reason == "duplicate_invoice":
        history.append({"invoice_number": inv_no, "po_number": po_str(po_n), "invoice_date": inv_date.isoformat(),
                        "lines": [{"sku": l["sku"], "qty": l["qty"], "amount": l["amount"]} for l in inv_lines],
                        "status": "paid"})
        mutation = {"invoice_number": inv_no}
    other_skus = [s for s in catalog if s not in skus]
    if other_skus and rng.random() < 0.3:
        for _ in range(rng.randint(1, 2)):
            ks = rng.sample(other_skus, min(len(other_skus), rng.randint(1, 2)))
            pn = st.new_po(rng, avoid=[po_n])
            hl = []
            for k in ks:
                q = gen_qty(rng, k)
                hl.append({"sku": k, "qty": q, "amount": c2f(q * gen_price(rng, k))})
            d = as_of - datetime.timedelta(days=rng.randint(30, 200))
            history.append({"invoice_number": st.new_invoice(rng, sid, d.year % 100), "po_number": po_str(pn),
                            "invoice_date": d.isoformat(), "lines": hl, "status": "paid"})
    history.sort(key=lambda h: (h["invoice_date"], h["invoice_number"]))

    gold = {"po": gold_po, "shipping_notice": gold_asn, "gr": gold_gr, "invoice": gold_inv,
            "billing_history": history, "open_pos": open_pos}
    present = [d for d in DOC_TYPES if gold[d] is not None]

    # ---------------- noise
    def doc_qtys(d):
        g = gold[d]
        if d == "po":
            return [(l["sku"], l["qty"]) for l in g["lines"]]
        if d == "shipping_notice":
            return [(l["sku"], l["qty_shipped"]) for l in g["lines"]]
        if d == "gr":
            return [(l["sku"], l["qty_ordered"]) for l in g["lines"]] + \
                   [(l["sku"], l["qty_received"]) for l in g["lines"]]
        return [(l["sku"], l["qty"]) for l in g["lines"]]

    def packable(d):
        return any(ITEMS[s]["pack"] and q > 0 and q % ITEMS[s]["pack"]["size"] == 0 for s, q in doc_qtys(d))

    pack_docs = [d for d in present if packable(d)]
    big_docs = [d for d in present if d in ("po", "invoice") and (gold[d]["total"] >= 1000)
                or any(q >= 1000 for _, q in doc_qtys(d))]
    types = choose_noise_types(rng, stratum, present, bool(pack_docs))
    cfg = build_noise_cfg(rng, types, sid, present, pack_docs, big_docs)

    # handwriting on the receipt
    hw = {}
    clerk = gold_gr["received_by"] if gold_gr else None
    if gold_gr is not None:
        if reason == "lost_in_transit" and rng.random() < 0.7:
            q = recv[mut_i]
            if rng.random() < 0.5 or "handwritten_note" in types:
                hw[m["sku"]] = {"variant": "struck", "printed": shipped[mut_i], "written": "%d %s" % (q, clerk),
                                "remark": rng.choice(LOST_REMARKS) + " " + clerk}
            else:
                hw[m["sku"]] = {"variant": "note", "printed": q, "written": None,
                                "remark": rng.choice(LOST_NOTES).format(q=q, c=clerk)}
        if "handwritten_note" in types:
            gl = gold_gr["lines"]
            cand = [l for l in gl if l["sku"] not in hw]
            if not cand:
                cand = []
            k = rng.randint(1, max(1, len(cand))) if cand else 0
            for l in rng.sample(cand, k):
                q = l["qty_received"]
                mutated = qty_mut and l["sku"] == m["sku"]
                opts = ["tick", "blank"]
                if sup["writes_qty_by_hand"] or mutated:
                    opts += ["struck", "struck"]
                v = rng.choice(opts)
                if v == "tick":
                    hw[l["sku"]] = {"variant": "tick", "printed": q, "written": "%d ✓ %s" % (q, clerk)}
                elif v == "blank":
                    hw[l["sku"]] = {"variant": "blank", "printed": None, "written": "%d %s" % (q, clerk)}
                else:
                    if mutated:
                        printed = l["qty_ordered"]
                    else:
                        delta = rng.randint(1, max(1, q // 10))
                        printed = q + delta if (rng.random() < 0.5 or q - delta < 1) else q - delta
                    hw[l["sku"]] = {"variant": "struck", "printed": printed, "written": "%d %s" % (q, clerk)}

    # ---------------- templates
    tpl = {}
    held_docs = []
    if held_t:
        held_docs = rng.sample(present, rng.choice([1, 1, 2]))
    for d in DOC_TYPES:
        if gold[d] is None:
            tpl[d] = None
        elif d in held_docs:
            tpl[d] = TEST_ONLY_TEMPLATES[d]
        elif d == "po":
            tpl[d] = wchoice(rng, co["po_tpl_w"])
        elif d == "gr":
            tpl[d] = wchoice(rng, co["gr_tpl_w"])
        elif d == "invoice":
            tpl[d] = wchoice(rng, sup["inv_tpl_w"])
        else:
            tpl[d] = wchoice(rng, sup["asn_tpl_w"])

    ctx = {"company": company, "supplier_id": sid}
    texts, tokens = {}, []
    for d in DOC_TYPES:
        if gold[d] is None:
            texts[d] = None
            continue
        t, toks = render_document(d, tpl[d], gold, ctx, cfg[d], hw if d == "gr" else {}, rng_ocr)
        texts[d] = t
        tokens += toks

    # ---------------- label
    if stratum == "in_transit":
        code = "gr_missing_in_transit"
    elif stratum == "real":
        code = reason
    else:
        code = "none"
    if reason in ("short_shipped", "lost_in_transit", "qty_mismatch"):
        at_risk_c = (inv_qty[mut_i] - recv[mut_i]) * inv_price[mut_i]
    elif reason == "price_mismatch":
        at_risk_c = (inv_price[mut_i] - m["price"]) * inv_qty[mut_i]
    elif reason in ("wrong_po", "duplicate_invoice"):
        at_risk_c = inv_total_c
    else:
        at_risk_c = 0

    label = {
        "stratum": stratum,
        "real_discrepancy": stratum == "real",
        "reason_code": code,
        "next_step": NEXT_STEP[code],
        "at_risk_usd": c2f(at_risk_c),
        "leg": LEG[code],
        "noise_types": types,
        "mutation": mutation,
        "gold": gold,
        "render_meta": {"doc_cfg": cfg, "handwriting": hw, "tokens": tokens,
                        "partial_delivery": partial},
    }
    case = {
        "case_id": case_id,
        "split": split,
        "company": company,
        "supplier_id": sid,
        "as_of_date": as_of.isoformat(),
        "documents": texts,
        "billing_history": history,
        "open_pos": open_pos,
        "wiki_refs": {
            "supplier": ("wiki/suppliers/%s.json" % sid) if sid in WIKI_SUPPLIER_PAGES else None,
            "items": ["wiki/items/%s.json" % s for s in sorted(skus)],
            "policy": "wiki/policy.json",
        },
        "template_ids": tpl,
        "heldout": {"template": any(v and v.endswith("_t4") for v in tpl.values()), "supplier": sid == TEST_ONLY_SUPPLIER},
        "label": label,
    }
    return case
