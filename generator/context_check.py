"""Checker for the context-anomaly set. Recomputes supplier history from TRAIN gold independently,
reads the wiki, and verifies every context label. Exits non-zero on any failure.

python3 -I generator/context_check.py
"""
import collections
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FAIL = []
UNDO = str.maketrans({"O": "0", "l": "1", "I": "1", "S": "5"})
ANOMALIES = {"new_item_for_supplier": "investigate", "price_above_history": "dispute_with_supplier",
             "pack_size_changed": "dispute_with_supplier", "remit_to_changed": "investigate",
             "near_duplicate_invoice": "investigate", "quantity_spike": "investigate",
             "ship_from_unusual": "investigate"}
BENIGN = ["benign_price_within_band", "benign_qty_moderate", "benign_remit_reformatted",
          "benign_new_item_approved", "benign_near_match_other_po"]
TARGET = {"dev_context": (4, 14), "test_context": (20, 70)}
SAFE = {"field_reorder", "date_format", "number_format", "po_ref_format", "vendor_alias"}
REGION = {"Nevada": "NV", "Germany": "DE", "Florida": "FL", "Texas": "TX", "Netherlands": "NL",
          "California": "CA", "China": "CN", "Georgia": "GA", "New Jersey": "NJ", "Tennessee": "TN",
          "Hong Kong": "HK", "Sweden": "SE", "South Carolina": "SC"}


def fail(cid, msg):
    FAIL.append("%s: %s" % (cid, msg))


def canon_site(s):
    s = re.sub(r"\s*\(.*\)$", "", s.strip())
    city, rest = s.split(", ", 1)
    first = rest.split(" ")[0]
    for name, code in REGION.items():
        if rest.startswith(name):
            first = code
    return (city.lower(), first.upper())


def history():
    skus, inv_p, qmax, remit, ship = (collections.defaultdict(set), collections.defaultdict(list),
                                      collections.defaultdict(int), collections.defaultdict(set),
                                      collections.defaultdict(set))
    co_skus = collections.defaultdict(set)
    for line in open(os.path.join(ROOT, "data", "train.jsonl"), encoding="utf-8"):
        c = json.loads(line)
        g, sid, co = c["label"]["gold"], c["supplier_id"], c["company"]
        if not g["invoice"].get("remit_to"):
            fail(c["case_id"], "train invoice without remit_to")
        if g["shipping_notice"] and not g["shipping_notice"].get("ship_from"):
            fail(c["case_id"], "train notice without ship_from")
        qs = [(l["sku"], l["qty"]) for l in g["po"]["lines"] + g["invoice"]["lines"]]
        if g["shipping_notice"]:
            qs += [(l["sku"], l["qty_shipped"]) for l in g["shipping_notice"]["lines"]]
            ship[sid].add(g["shipping_notice"]["ship_from"])
        if g["gr"]:
            qs += [(l["sku"], max(l["qty_received"], l["qty_ordered"])) for l in g["gr"]["lines"]]
        qs += [(l["sku"], l["qty"]) for h in g["billing_history"] for l in h["lines"]]
        qs += [(l["sku"], l["qty"]) for o in g["open_pos"] for l in o["lines"]]
        for k, q in qs:
            skus[sid].add(k)
            co_skus[co].add(k)
            qmax[(co, sid, k)] = max(qmax[(co, sid, k)], q)
        for l in g["invoice"]["lines"]:
            inv_p[(sid, l["sku"])].append(l["unit_price"])
        remit[sid].add(g["invoice"]["remit_to"])
    return skus, inv_p, qmax, remit, ship, co_skus


def main():
    skus, inv_p, qmax, remit, ship, co_skus = history()
    wh = {}
    hd = os.path.join(ROOT, "wiki", "history")
    if os.path.isdir(hd):
        for fn in os.listdir(hd):
            if fn.startswith("SUP-"):
                wh[fn[:-5]] = json.load(open(os.path.join(hd, fn)))
    pages = {fn[:-5]: json.load(open(os.path.join(ROOT, "wiki", "suppliers", fn)))
             for fn in os.listdir(os.path.join(ROOT, "wiki", "suppliers"))}
    items = {fn[:-5]: json.load(open(os.path.join(ROOT, "wiki", "items", fn)))
             for fn in os.listdir(os.path.join(ROOT, "wiki", "items"))}

    def approved(sid, k, as_of):
        p = pages.get(sid)
        return bool(p) and k in p.get("approved_new_items", []) and p["expires"] >= as_of

    def means(sid, k):
        ms = [sum(inv_p[(sid, k)]) / len(inv_p[(sid, k)])]
        w = wh.get(sid, {}).get("unit_price_by_sku", {}).get(k)
        if w:
            ms.append(w["mean"])
        return ms

    def maxes(co, sid, k):
        ms = [qmax[(co, sid, k)]]
        w = wh.get(sid, {}).get("qty_max_by_company_sku", {}).get("%s|%s" % (co, k))
        if w:
            ms.append(w)
        return ms

    def near(a, b):
        if a == b or a.translate(UNDO) == b.translate(UNDO):
            return False
        if a.startswith(b) or b.startswith(a):
            return abs(len(a) - len(b)) <= 2
        if len(a) != len(b):
            return False
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]])

    for split, (per, nb) in TARGET.items():
        path = os.path.join(ROOT, "data", split + ".jsonl")
        cases = [json.loads(l) for l in open(path, encoding="utf-8")]
        if len(cases) != 7 * per + nb:
            fail(split, "size %d" % len(cases))
        cnt = collections.Counter()
        for c in cases:
            cid, lab = c["case_id"], c["label"]
            g = lab["gold"]
            po, asn, gr, inv = g["po"], g["shipping_notice"], g["gr"], g["invoice"]
            sid, co, as_of = c["supplier_id"], c["company"], c["as_of_date"]
            kind = lab["reason_code"] if lab["real_discrepancy"] else lab["benign_type"]
            cnt[(kind, co)] += 1
            if SUPPLIERS_TEST_ONLY == sid or not skus[sid]:
                fail(cid, "supplier without train history")
            if any(c["documents"][d] is None for d in ("po", "shipping_notice", "gr", "invoice")):
                fail(cid, "all four documents must be present")
            if not lab.get("context_basis"):
                fail(cid, "missing context_basis")
            nt = lab["noise_types"]
            if len(nt) > 2 or not set(nt) <= SAFE:
                fail(cid, "noise %s" % nt)
            if "number_format" in nt and kind in ("price_above_history", "pack_size_changed", "quantity_spike",
                                                  "benign_price_within_band", "benign_qty_moderate"):
                fail(cid, "number noise on the anomaly-critical field")
            # ---- three-way match passes (in the documents' own terms)
            if not (inv["po_number"] == po["po_number"] == gr["po_number"] == asn["po_number"]):
                fail(cid, "PO references disagree")
            if po["total"] != inv["total"]:
                fail(cid, "invoice total != PO total")
            pack_lines = []
            for il in inv["lines"]:
                k = il["sku"]
                pl = next(l for l in po["lines"] if l["sku"] == k)
                al = next(l for l in asn["lines"] if l["sku"] == k)
                gl = next(l for l in gr["lines"] if l["sku"] == k)
                if il["amount"] != pl["amount"]:
                    fail(cid, "line amount differs from PO")
                if "stated_pack" in il:
                    sp = il["stated_pack"]
                    pack_lines.append((k, sp, pl))
                    if al.get("stated_pack") != sp or gl.get("counted_cases") != sp["cases"]:
                        fail(cid, "notice/receipt do not state the same packs")
                    if not (il["qty"] == al["qty_shipped"] == gl["qty_received"] == sp["cases"] * sp["size"]):
                        fail(cid, "pack EA counts inconsistent")
                    txt = "{:,} CS ({:,} EA)".format(sp["cases"], sp["cases"] * sp["size"])
                    for d in ("invoice", "shipping_notice"):
                        if txt not in c["documents"][d]:
                            fail(cid, "%s text lacks %r" % (d, txt))
                    if "Received" not in c["documents"]["gr"] and "RCVD" not in c["documents"]["gr"] or \
                            "{:,} CS".format(sp["cases"]) not in c["documents"]["gr"] or \
                            "{:,} EA".format(sp["cases"] * sp["size"]) in c["documents"]["gr"]:
                        fail(cid, "receipt must show only the case count")
                else:
                    if not (il["qty"] == pl["qty"] == al["qty_shipped"] == gl["qty_received"] == gl["qty_ordered"]):
                        fail(cid, "quantities disagree")
                    if il["unit_price"] != pl["unit_price"]:
                        fail(cid, "price disagrees with PO")
            for h in g["billing_history"]:
                if h["invoice_number"].translate(UNDO) == inv["invoice_number"].translate(UNDO):
                    fail(cid, "exact duplicate in history")
            if c["billing_history"] != g["billing_history"]:
                fail(cid, "billing_history != gold")

            # ---- context signals from train history + wiki
            sig = set()
            risk = 0
            for il in inv["lines"]:
                k = il["sku"]
                if k not in skus[sid] and k not in wh.get(sid, {}).get("unit_price_by_sku", {}):
                    if not approved(sid, k, as_of):
                        sig.add("new_item_for_supplier")
                        if not any(k in skus[o] for o in skus if o != sid):
                            fail(cid, "new item not bought from any other supplier in train")
                        if k not in co_skus[co]:
                            fail(cid, "company never bought the new item")
                    continue
                if "stated_pack" in il:
                    continue
                ms = means(sid, k)
                p = il["unit_price"]
                if p > max(ms) * 1.10:
                    sig.add("price_above_history")
                    if not (len(inv_p[(sid, k)]) >= 5 and min(ms) * 1.15 <= p <= max(ms) * 1.40):
                        fail(cid, "price anomaly outside 15-40% or <5 observations")
                    risk += round((p - ms[0]) * il["qty"], 2)
                elif abs(p / ms[0] - 1) > 0.05:
                    fail(cid, "price neither normal nor anomalous (%.3f)" % (p / ms[0]))
                mx = maxes(co, sid, k)
                if il["qty"] >= 5 * max(mx):
                    sig.add("quantity_spike")
                    risk += (il["qty"] - qmax[(co, sid, k)]) * il["unit_price"]
                elif il["qty"] > 2 * min(mx):
                    fail(cid, "quantity between 2x and 5x history max")
            for k, sp, pl in pack_lines:
                wiki = items[k]["pack_conversions"].get("CS")
                if wiki and wiki != sp["size"]:
                    sig.add("pack_size_changed")
                    risk += (pl["qty"] - sp["cases"] * sp["size"]) * pl["unit_price"]
                    if pl["qty"] != sp["cases"] * wiki:
                        fail(cid, "PO qty is not the wiki pack count")
                    if not SUPPLIERS_PACKS[sid]:
                        fail(cid, "pack anomaly on a supplier that does not bill in packs")
            if canon_site(inv["remit_to"]) not in {canon_site(s) for s in remit[sid]}:
                sig.add("remit_to_changed")
                if inv["remit_to"] not in c["documents"]["invoice"] or "Remit payment to" not in c["documents"]["invoice"]:
                    fail(cid, "remit block not in invoice text")
            if canon_site(asn["ship_from"]) not in {canon_site(s) for s in ship[sid]}:
                sig.add("ship_from_unusual")
                if asn["ship_from"] not in c["documents"]["shipping_notice"]:
                    fail(cid, "ship_from not in notice text")
            if wh.get(sid):
                if inv["remit_to"] not in wh[sid].get("remit_to", []) and kind not in (
                        "remit_to_changed", "benign_remit_reformatted"):
                    fail(cid, "remit_to not in wiki/history")
                if asn["ship_from"] not in wh[sid].get("ship_from", []) and kind != "ship_from_unusual":
                    fail(cid, "ship_from not in wiki/history")
            for h in g["billing_history"]:
                if near(h["invoice_number"], inv["invoice_number"]):
                    same = h["po_number"] == po["po_number"] and sorted(
                        (l["sku"], l["qty"], l["amount"]) for l in h["lines"]) == sorted(
                        (l["sku"], l["qty"], l["amount"]) for l in inv["lines"])
                    if same:
                        sig.add("near_duplicate_invoice")
                    elif kind != "benign_near_match_other_po":
                        fail(cid, "unexpected near-match number in history")
                    elif h["po_number"] == po["po_number"] or {l["sku"] for l in h["lines"]} & {
                            l["sku"] for l in inv["lines"]}:
                        fail(cid, "benign near-match shares PO or SKUs")
                elif h["po_number"] == po["po_number"]:
                    fail(cid, "history on the same PO in a non-near-duplicate case")
            if kind in ("near_duplicate_invoice", "new_item_for_supplier", "remit_to_changed", "ship_from_unusual"):
                risk = inv["total"] if kind in sig else risk

            # ---- compare with label
            if lab["real_discrepancy"]:
                if lab["stratum"] != "context_anomaly" or sig != {kind} or lab["next_step"] != ANOMALIES[kind] \
                        or lab["leg"] is not None:
                    fail(cid, "anomaly %s: signals %s" % (kind, sorted(sig)))
                if abs(lab["at_risk_usd"] - round(risk, 2)) > 0.02 or lab["at_risk_usd"] <= 0:
                    fail(cid, "at_risk %s != %s" % (lab["at_risk_usd"], round(risk, 2)))
            else:
                if lab["stratum"] != "context_benign" or sig or lab["reason_code"] != "none" or \
                        lab["next_step"] != "pay" or lab["at_risk_usd"] != 0 or kind not in BENIGN:
                    fail(cid, "benign %s has signals %s" % (kind, sorted(sig)))
                k = lab["signal_sku"]
                il = next(l for l in inv["lines"] if l["sku"] == k)
                if kind == "benign_price_within_band" and not all(abs(il["unit_price"] / m - 1) <= 0.03
                                                                  for m in means(sid, k)):
                    fail(cid, "benign price outside +/-3%")
                if kind == "benign_qty_moderate" and not all(1.3 * m <= il["qty"] <= 2 * m for m in maxes(co, sid, k)):
                    fail(cid, "benign qty outside 1.3-2x")
                if kind == "benign_remit_reformatted" and inv["remit_to"] in remit[sid]:
                    fail(cid, "benign remit not reformatted")
                if kind == "benign_new_item_approved" and (k in skus[sid] or not approved(sid, k, as_of)):
                    fail(cid, "benign new item not new or not approved")
                if kind == "benign_near_match_other_po" and not any(near(h["invoice_number"], inv["invoice_number"])
                                                                   for h in g["billing_history"]):
                    fail(cid, "benign near-match missing")
        for kind in ANOMALIES:
            for co in ("northside", "caseworks"):
                if cnt[(kind, co)] != per // 2:
                    fail(split, "%s/%s count %d" % (kind, co, cnt[(kind, co)]))
        for kind in BENIGN:
            tot = cnt[(kind, "northside")] + cnt[(kind, "caseworks")]
            if abs(tot - nb / len(BENIGN)) > 1 or abs(cnt[(kind, "northside")] - cnt[(kind, "caseworks")]) > 1:
                fail(split, "benign %s counts %d/%d" % (kind, cnt[(kind, "northside")], cnt[(kind, "caseworks")]))
    mp = os.path.join(ROOT, "data", "context_manifest.json")
    m = json.load(open(mp))
    for f, info in m["files"].items():
        if hashlib.sha256(open(os.path.join(ROOT, f), "rb").read()).hexdigest() != info["sha256"]:
            fail("manifest", "hash " + f)
    if FAIL:
        print("CONTEXT CHECK FAILED: %d problems" % len(FAIL))
        for f in FAIL[:60]:
            print("  " + f)
        sys.exit(1)
    print("CONTEXT CHECK PASSED: dev_context=%d, test_context=%d" % (7 * 4 + 14, 7 * 20 + 70))


sys.path.insert(0, HERE)
from world import SUPPLIERS, TEST_ONLY_SUPPLIER  # noqa: E402
SUPPLIERS_TEST_ONLY = TEST_ONLY_SUPPLIER
SUPPLIERS_PACKS = {s: v["bills_in_packs"] for s, v in SUPPLIERS.items()}

if __name__ == "__main__":
    main()
