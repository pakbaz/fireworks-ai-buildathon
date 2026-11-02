"""Layout templates: turn a structured (gold) document into OCR-style page text.

Four layout families. t1..t3 are shared by all splits; t4 is used only in the test split.
Each render returns (text, tokens). A token records exactly how a decision-critical value
was written, so the checker can re-derive the value from the text.
"""
import random

from world import COMPANIES, SUPPLIERS, ITEMS
from noise import (fmt_money, fmt_date, fmt_po_ref, fmt_qty, fmt_unit_price, fmt_int,
                   ocr_swap_one, ocr_text_noise)

LABELS = {
    1: {"po_number": "PO Number", "po_date": "PO Date", "revision": "Revision", "buyer": "Buyer",
        "terms": "Terms", "vendor_id": "Vendor ID", "ship_to": "Ship To", "asn_number": "ASN No.",
        "ship_date": "Ship Date", "po_ref": "Customer PO", "carrier": "Carrier", "tracking": "Tracking No.",
        "ship_from": "Ship From", "cartons": "Cartons", "gr_number": "Receipt No.", "received_date": "Date Received",
        "supplier": "Supplier", "received_by": "Received By", "dock": "Dock", "invoice_number": "Invoice No.",
        "invoice_date": "Invoice Date", "due_date": "Due Date", "customer": "Customer", "remit_to": "Remit From",
        "line": "Ln", "sku": "Item", "desc": "Description", "qty": "Quantity", "unit_price": "Unit Price",
        "amount": "Amount", "qty_shipped": "Qty Shipped", "qty_ordered": "Qty Ordered",
        "qty_received": "Qty Received", "subtotal": "Subtotal", "tax": "Sales Tax", "total": "Total",
        "to_po": "Vendor", "to_inv": "Bill To", "to_asn": "Ship To", "to_gr": "Vendor"},
    2: {"po_number": "Purchase Order #", "po_date": "Order Date", "revision": "Rev", "buyer": "Requested By",
        "terms": "Payment Terms", "vendor_id": "Supplier No", "ship_to": "Deliver To", "asn_number": "Packing Slip #",
        "ship_date": "Shipped On", "po_ref": "Your Order Ref", "carrier": "Ship Via", "tracking": "Waybill",
        "ship_from": "Dispatched From", "cartons": "Pkgs", "gr_number": "Receiving Report #",
        "received_date": "Received On", "supplier": "Vendor", "received_by": "Checked By", "dock": "Location",
        "invoice_number": "Invoice #", "invoice_date": "Date", "due_date": "Payment Due", "customer": "Sold To",
        "remit_to": "Branch", "line": "#", "sku": "SKU", "desc": "Item Description", "qty": "Qty",
        "unit_price": "Price", "amount": "Ext. Price", "qty_shipped": "Shipped", "qty_ordered": "Ordered",
        "qty_received": "Received", "subtotal": "Sub-total", "tax": "Tax", "total": "Amount Due",
        "to_po": "Supplier", "to_inv": "Sold To", "to_asn": "Consignee", "to_gr": "From Vendor"},
    3: {"po_number": "ORDER NO", "po_date": "ORDER DATE", "revision": "REV", "buyer": "BUYER",
        "terms": "TERMS", "vendor_id": "VENDOR", "ship_to": "DELIVERY ADDR", "asn_number": "DELIVERY NOTE NO",
        "ship_date": "DESPATCH DATE", "po_ref": "CUST PO NO", "carrier": "CARRIER", "tracking": "CONSIGNMENT",
        "ship_from": "DESPATCH POINT", "cartons": "CTNS", "gr_number": "GRN NO", "received_date": "RCPT DATE",
        "supplier": "SUPPLIER", "received_by": "CLERK", "dock": "BAY", "invoice_number": "INVOICE NO",
        "invoice_date": "INVOICE DATE", "due_date": "DUE", "customer": "CUSTOMER", "remit_to": "OFFICE",
        "line": "POS", "sku": "ARTICLE", "desc": "DESCRIPTION", "qty": "QTY", "unit_price": "UNIT PRICE",
        "amount": "NET AMOUNT", "qty_shipped": "QTY DESP", "qty_ordered": "QTY ORD", "qty_received": "QTY RCVD",
        "subtotal": "NET TOTAL", "tax": "VAT/TAX", "total": "GROSS TOTAL",
        "to_po": "SUPPLIER", "to_inv": "INVOICE TO", "to_asn": "DELIVER TO", "to_gr": "SUPPLIER"},
    4: {"po_number": "P/O", "po_date": "dt", "revision": "rv", "buyer": "byr", "terms": "trm",
        "vendor_id": "vnd", "ship_to": "dlv", "asn_number": "desp.ref", "ship_date": "desp.dt",
        "po_ref": "ref(P/O)", "carrier": "carr", "tracking": "trk", "ship_from": "from", "cartons": "pkgs",
        "gr_number": "rcpt.ref", "received_date": "rcpt.dt", "supplier": "vnd", "received_by": "by",
        "dock": "loc", "invoice_number": "doc.no", "invoice_date": "doc.dt", "due_date": "due.dt",
        "customer": "cust", "remit_to": "office", "line": "ln", "sku": "item", "desc": "desc",
        "qty": "qty/um", "unit_price": "u.pr", "amount": "ext", "qty_shipped": "desp", "qty_ordered": "ord",
        "qty_received": "rcvd", "subtotal": "net", "tax": "tax", "total": "TOTAL DUE",
        "to_po": "vendor", "to_inv": "bill-to", "to_asn": "consignee", "to_gr": "vendor"},
}
TITLES = {
    "po": ["PURCHASE ORDER", "Purchase Order", "P U R C H A S E   O R D E R", "PURCH. ORDER"],
    "shipping_notice": ["ADVANCE SHIP NOTICE", "Packing Slip", "DELIVERY NOTE", "DESPATCH ADVICE"],
    "gr": ["GOODS RECEIPT", "Receiving Report", "GOODS RECEIVED NOTE", "INBOUND RECEIPT LOG"],
    "invoice": ["INVOICE", "Invoice", "COMMERCIAL INVOICE", "BILL / INVOICE"],
}
RIGHT = {"qty", "unit_price", "amount", "qty_shipped", "qty_ordered", "qty_received"}
OCR_P = {"qty": 0.45, "money": 0.45, "po_ref": 0.45, "id": 0.45, "sku": 0.15}


def tpl_family(tpl_id):
    return int(tpl_id[-1])


class Builder:
    def __init__(self, doc_type, cfg, rng_ocr, supplier_id):
        self.doc_type = doc_type
        self.cfg = cfg
        self.rng_ocr = rng_ocr
        self.tokens = []
        self.region = SUPPLIERS[supplier_id]["number_format"]

    def tok(self, field, kind, text, sku=None):
        if self.cfg["ocr"] and kind in OCR_P and self.rng_ocr.random() < OCR_P[kind]:
            region = None
            if kind in ("po_ref", "id", "sku"):
                # only touch the digit part after the last letter-prefix
                first_digit = next((i for i, c in enumerate(text) if c.isdigit()), len(text))
                if kind == "po_ref" and text.startswith("PO-"):
                    first_digit = 3
                region = (first_digit, len(text))
            text = ocr_swap_one(text, self.rng_ocr, region)
        self.tokens.append({"doc": self.doc_type, "field": field, "kind": kind, "sku": sku, "text": text})
        return text

    def soft(self, text):
        if self.cfg["ocr"]:
            return ocr_text_noise(text, self.rng_ocr)
        return text

    def date(self, iso):
        return fmt_date(iso, self.cfg["date"], self.region)

    def money(self, cents):
        return fmt_money(cents, self.cfg["num"])

    def qty(self, q, sku):
        return fmt_qty(q, sku, self.cfg["num"], self.cfg["pack"])

    def po_ref(self, po_number):
        n = int(po_number.split("-")[1])
        return fmt_po_ref(n, self.cfg["po_ref"])


def _cents(x):
    return int(round(x * 100))


def supplier_lines(b, sid):
    s = SUPPLIERS[sid]
    name = b.cfg["alias"] or s["name"]
    site = b.cfg["site"] or s["sites"][0]
    return [b.soft(name), b.soft(site)]


def company_lines(b, company):
    c = COMPANIES[company]
    return [c["name"]] + [b.soft(x) for x in c["address"]]


def model_po(b, g, ctx):
    po = g["po"]
    hdr = [("po_number", b.tok("po_number", "po_ref", po["po_number"])),
           ("po_date", b.tok("po_date", "date", b.date(po["po_date"])))]
    if po["revision"] > 1:
        hdr.append(("revision", str(po["revision"])))
    hdr += [("buyer", po["buyer"]), ("terms", "Net 30"), ("vendor_id", ctx["supplier_id"]),
            ("ship_to", "Main receiving")]
    rows = []
    for ln in po["lines"]:
        q, uom = b.qty(ln["qty"], ln["sku"])
        rows.append({"line": str(ln["line"]), "sku": b.tok("sku", "sku", ln["sku"], ln["sku"]),
                     "desc": b.soft(ln["description"]),
                     "qty": b.tok("qty", "qty", q, ln["sku"]),
                     "unit_price": b.tok("unit_price", "money",
                                         fmt_unit_price(_cents(ln["unit_price"]), ln["sku"], b.cfg["num"], uom), ln["sku"]),
                     "amount": b.tok("amount", "money", b.money(_cents(ln["amount"])), ln["sku"])})
    remarks = []
    for ln in po["lines"]:
        if ln["qty_previously_billed"]:
            remarks.append("PO status line %d %s: ordered %s EA; %s EA previously received and paid on %s; "
                           "open balance %s EA." % (ln["line"], ln["sku"], fmt_int(ln["qty"]),
                                                    fmt_int(ln["qty_previously_billed"]),
                                                    po["prior_invoice"], fmt_int(ln["qty_open"])))
    remarks.append("Deliver to receiving dock. Reference PO number on all paperwork.")
    return {"from": company_lines(b, ctx["company"]), "to_key": "to_po", "to": supplier_lines(b, ctx["supplier_id"]),
            "header": hdr, "columns": ["line", "sku", "desc", "qty", "unit_price", "amount"], "rows": rows,
            "totals": [("total", b.tok("total", "money", b.money(_cents(po["total"]))))], "remarks": remarks}


def model_asn(b, g, ctx):
    a = g["shipping_notice"]
    hdr = [("asn_number", b.tok("asn_number", "id", a["asn_number"])),
           ("ship_date", b.tok("ship_date", "date", b.date(a["ship_date"]))),
           ("po_ref", b.tok("po_ref", "po_ref", b.po_ref(a["po_number"]))),
           ("carrier", a["carrier"]), ("tracking", a["tracking"]),
           ("ship_from", b.soft(b.cfg["site"] or a["ship_from"])), ("cartons", str(a["cartons"]))]
    rows = []
    for i, ln in enumerate(a["lines"], 1):
        q, _ = b.qty(ln["qty_shipped"], ln["sku"])
        rows.append({"line": str(i), "sku": b.tok("sku", "sku", ln["sku"], ln["sku"]),
                     "desc": b.soft(ln["description"]),
                     "qty_shipped": b.tok("qty_shipped", "qty", q, ln["sku"])})
    return {"from": supplier_lines(b, ctx["supplier_id"]), "to_key": "to_asn",
            "to": company_lines(b, ctx["company"]), "header": hdr,
            "columns": ["line", "sku", "desc", "qty_shipped"], "rows": rows, "totals": [],
            "remarks": ["Goods remain property of seller until paid in full."]}


def model_gr(b, g, ctx, hw):
    r = g["gr"]
    s = SUPPLIERS[ctx["supplier_id"]]
    hdr = [("gr_number", r["gr_number"]),
           ("received_date", b.tok("received_date", "date", b.date(r["received_date"]))),
           ("po_ref", b.tok("po_ref", "po_ref", b.po_ref(r["po_number"]))),
           ("supplier", b.soft(b.cfg["alias"] or s["name"])),
           ("received_by", r["received_by"]), ("dock", "Dock %d" % r["dock"])]
    rows, remarks = [], []
    for i, ln in enumerate(r["lines"], 1):
        qo, _ = b.qty(ln["qty_ordered"], ln["sku"])
        spec = hw.get(ln["sku"])
        if spec is None:
            q, _ = b.qty(ln["qty_received"], ln["sku"])
            cell = b.tok("qty_received", "gr_qty", q, ln["sku"])
        else:
            if spec["variant"] == "tick":
                q, _ = b.qty(ln["qty_received"], ln["sku"])
                cell = "%s [handwritten: '%s']" % (q, spec["written"])
            elif spec["variant"] == "blank":
                cell = "____ [handwritten: '%s']" % spec["written"]
            elif spec["variant"] == "struck":
                q, _ = fmt_qty(spec["printed"], ln["sku"], b.cfg["num"], b.cfg["pack"])
                cell = "[struck-out: %s] [handwritten: '%s']" % (q, spec["written"])
            else:  # printed is the true received qty, explanation written in remarks
                q, _ = b.qty(ln["qty_received"], ln["sku"])
                cell = q
            cell = b.tok("qty_received", "gr_qty", cell, ln["sku"])
            if spec.get("remark"):
                remarks.append("Line %d: [handwritten: '%s']" % (i, spec["remark"]))
        rows.append({"line": str(i), "sku": b.tok("sku", "sku", ln["sku"], ln["sku"]),
                     "desc": b.soft(ln["description"]),
                     "qty_ordered": b.tok("qty_ordered", "qty", qo, ln["sku"]), "qty_received": cell})
    remarks.append("Received subject to inspection. Count verified at dock.")
    return {"from": company_lines(b, ctx["company"]), "to_key": "to_gr",
            "to": supplier_lines(b, ctx["supplier_id"]), "header": hdr,
            "columns": ["line", "sku", "desc", "qty_ordered", "qty_received"], "rows": rows,
            "totals": [], "remarks": remarks}


def model_invoice(b, g, ctx):
    v = g["invoice"]
    hdr = [("invoice_number", b.tok("invoice_number", "id", v["invoice_number"])),
           ("invoice_date", b.tok("invoice_date", "date", b.date(v["invoice_date"]))),
           ("po_ref", b.tok("po_ref", "po_ref", b.po_ref(v["po_number"]))),
           ("due_date", b.tok("due_date", "date", b.date(v["due_date"]))),
           ("terms", "Net 30"), ("customer", COMPANIES[ctx["company"]]["ap"]),
           ("remit_to", b.soft(b.cfg["site"] or v["remit_to"]))]
    rows = []
    for ln in v["lines"]:
        q, uom = b.qty(ln["qty"], ln["sku"])
        rows.append({"line": str(ln["line"]), "sku": b.tok("sku", "sku", ln["sku"], ln["sku"]),
                     "desc": b.soft(ln["description"]), "qty": b.tok("qty", "qty", q, ln["sku"]),
                     "unit_price": b.tok("unit_price", "money",
                                         fmt_unit_price(_cents(ln["unit_price"]), ln["sku"], b.cfg["num"], uom), ln["sku"]),
                     "amount": b.tok("amount", "money", b.money(_cents(ln["amount"])), ln["sku"])})
    totals = [("subtotal", b.tok("subtotal", "money", b.money(_cents(v["subtotal"])))),
              ("tax", b.money(_cents(v["tax"]))),
              ("total", b.tok("total", "money", b.money(_cents(v["total"]))))]
    return {"from": supplier_lines(b, ctx["supplier_id"]), "to_key": "to_inv",
            "to": company_lines(b, ctx["company"]), "header": hdr,
            "columns": ["line", "sku", "desc", "qty", "unit_price", "amount"], "rows": rows,
            "totals": totals, "remarks": (["Remit payment to: %s / Bank: %s" % (v["remit_to"], v["remit_bank"])]
                                          if v.get("remit_bank") else [])
            + ["Please quote invoice number with remittance. Thank you for your business."]}


# ---------------------------------------------------------------- layouts

def _wrap(text, width):
    words, out, cur = text.split(" "), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w) if cur else w
    out.append(cur)
    return out


def _table(m, L, sep="  ", desc_w=24, pipes=False):
    cols = m["columns"]
    head = [L[c] for c in cols]
    wrapped = [{c: (_wrap(r[c], desc_w) if c == "desc" else [r[c]]) for c in cols} for r in m["rows"]]
    widths = [max([len(head[i])] + [len(x) for w in wrapped for x in w[c]]) for i, c in enumerate(cols)]

    def fmt_row(cells):
        parts = [cells[i].rjust(widths[i]) if cols[i] in RIGHT else cells[i].ljust(widths[i])
                 for i in range(len(cols))]
        if pipes:
            return ("| " + " | ".join(parts) + " |").rstrip()
        return sep.join(parts).rstrip()

    out = [fmt_row(head)]
    out.append("-" * len(out[0]))
    for w in wrapped:
        n = max(len(w[c]) for c in cols)
        for k in range(n):
            out.append(fmt_row([w[c][k] if k < len(w[c]) else "" for c in cols]))
    return out


def layout_1(m, L, title):
    out = [m["from"][0].ljust(44) + title]
    out += m["from"][1:]
    out += ["", L[m["to_key"]] + ":"] + ["   " + x for x in m["to"]] + [""]
    cells = ["%s: %s" % (L[k], v) for k, v in m["header"]]
    for i in range(0, len(cells), 2):
        pair = cells[i:i + 2]
        out.append((pair[0].ljust(max(40, len(pair[0]) + 3)) + (pair[1] if len(pair) > 1 else "")).rstrip())
    out = [x.rstrip() for x in out]
    out.append("")
    out += _table(m, L)
    out.append("")
    for k, v in m["totals"]:
        out.append(("%s:" % L[k]).rjust(52) + "  " + v.rjust(16))
    if m["remarks"]:
        out.append("")
        for r in m["remarks"]:
            out += _wrap(r, 76)
    out += ["", "Page 1 of 1"]
    return out


def layout_2(m, L, title):
    out = [title, m["from"][0]]
    rest = ", ".join(m["from"][1:])
    # OCR often splits the address line mid-way
    cut = rest.find(", ")
    out += [rest[:cut + 1], rest[cut + 2:]] if cut > 0 else [rest]
    out += ["", "%s: %s" % (L[m["to_key"]], m["to"][0])] + ["    " + x for x in m["to"][1:]] + [""]
    for k, v in m["header"]:
        lab = L[k]
        out.append("%s %s %s" % (lab, "." * max(2, 22 - len(lab)), v))
    out += ["", "ITEMS", "-----"]
    for r in m["rows"]:
        others = [c for c in m["columns"] if c not in ("line", "desc")]
        out.append("%02d  %s" % (int(r["line"]), "   ".join(
            "%s: %s" % (L[c], r[c]) for c in others if c == "sku")))
        out += ["    " + x for x in _wrap(r["desc"], 60)]
        rest_cols = [c for c in others if c != "sku"]
        out.append("    " + "   ".join("%s: %s" % (L[c], r[c]) for c in rest_cols))
    out.append("")
    for k, v in m["totals"]:
        out.append("%s: %s" % (L[k], v))
    if m["remarks"]:
        out.append("")
        for r in m["remarks"]:
            out += _wrap(r, 76)
    out += ["", "-- end of document --"]
    return out


def layout_3(m, L, title):
    body = []
    hdr = m["header"]
    for i in range(0, len(hdr), 3):
        chunk = hdr[i:i + 3]
        ws = [max(len(L[k]), len(v)) for k, v in chunk]
        body.append("| " + " | ".join(L[k].ljust(w) for (k, _), w in zip(chunk, ws)) + " |")
        body.append("| " + " | ".join(v.ljust(w) for (_, v), w in zip(chunk, ws)) + " |")
    table = _table(m, L, desc_w=20, pipes=True)
    width = max([len(x) for x in body + table] + [60])
    out = ["=" * width, "| %s   %s" % (title, m["from"][0]), "| " + " / ".join(m["from"][1:]), "=" * width]
    out += body + ["-" * width] + table + ["-" * width]
    for k, v in m["totals"]:
        out.append("| %s | %s |" % (L[k].rjust(30), v.rjust(16)))
    out += [""] + _wrap("%s: %s" % (L[m["to_key"]], " / ".join(m["to"])), 76)
    for r in m["remarks"]:
        out += _wrap(r, 76)
    return out


def layout_4(m, L, title):
    out = [m["from"][0].upper()] + m["from"][1:]
    out += ["%s: %s" % (L[m["to_key"]], "; ".join(m["to"])), "", "LINE ITEMS"]
    for r in m["rows"]:
        parts = ["%s=%s" % (L[c], r[c]) for c in m["columns"] if c != "line"]
        line = "#%s " % r["line"]
        for p in parts:
            if len(line) + len(p) + 2 > 78 and line.strip():
                out.append(line.rstrip())
                line = "     "
            line += p + "; "
        out.append(line.rstrip().rstrip(";"))
    if m["totals"]:
        out.append(" ; ".join("%s=%s" % (L[k], v) for k, v in m["totals"]))
    out += ["", "---- %s ----" % title]
    cells = ["%s=%s" % (L[k], v) for k, v in m["header"]]
    for i in range(0, len(cells), 2):
        out.append("  ;  ".join(cells[i:i + 2]))
    for r in m["remarks"]:
        out += _wrap(r, 76)
    return out


LAYOUTS = {1: layout_1, 2: layout_2, 3: layout_3, 4: layout_4}
MODELS = {"po": model_po, "shipping_notice": model_asn, "invoice": model_invoice}


def render_document(doc_type, tpl_id, gold, ctx, cfg, hw, rng_ocr):
    b = Builder(doc_type, cfg, rng_ocr, ctx["supplier_id"])
    if doc_type == "gr":
        m = model_gr(b, gold, ctx, hw)
    else:
        m = MODELS[doc_type](b, gold, ctx)
    fam = tpl_family(tpl_id)
    if cfg["reorder"]:
        r = random.Random(cfg["reorder"])
        r.shuffle(m["header"])
        rest = m["columns"][1:]
        r.shuffle(rest)
        m["columns"] = m["columns"][:1] + rest
    lines = LAYOUTS[fam](m, LABELS[fam], TITLES[doc_type][fam - 1])
    text = "\n".join(x.rstrip() for x in lines) + "\n"
    for t in b.tokens:
        if t["text"] not in text:
            raise AssertionError("token not rendered: %r in %s" % (t, doc_type))
    return text, b.tokens
