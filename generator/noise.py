"""Value formatting (canonical and noisy) and per-case noise configuration.

Noise only changes how a value is written, never the value itself.
"""
import datetime

from world import SUPPLIERS, ITEMS, NOISE_TYPES

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ---------------------------------------------------------------- formatting

def _group(n, sep):
    s = str(n)
    out = []
    while len(s) > 3:
        out.insert(0, s[-3:])
        s = s[:-3]
    out.insert(0, s)
    return sep.join(out)


def fmt_money(cents, style="us"):
    whole, frac = divmod(cents, 100)
    if style == "us":
        return "%s.%02d" % (_group(whole, ","), frac)
    if style == "us_sym":
        return "$%s.%02d" % (_group(whole, ","), frac)
    if style == "us_plain":
        return "%d.%02d" % (whole, frac)
    if style == "us_code":
        return "%s.%02d USD" % (_group(whole, ","), frac)
    if style == "eu":
        return "%s,%02d" % (_group(whole, "."), frac)
    if style == "eu_code":
        return "USD %s,%02d" % (_group(whole, "."), frac)
    if style == "eu_sym":
        return "%s,%02d $" % (_group(whole, "."), frac)
    raise ValueError(style)


def fmt_int(n, style="us"):
    if style.startswith("eu"):
        return _group(n, ".")
    if style == "us_plain":
        return str(n)
    return _group(n, ",")


def fmt_date(iso, style="iso", region="US"):
    d = datetime.date.fromisoformat(iso)
    if style == "iso":
        return iso
    if style == "dmy_text":
        return "%d %s %d" % (d.day, MONTHS[d.month - 1], d.year)
    if style == "mdy_text":
        return "%s %d, %d" % (MONTHS[d.month - 1], d.day, d.year)
    if style == "dmy_upper":
        return "%02d-%s-%02d" % (d.day, MONTHS[d.month - 1].upper(), d.year % 100)
    if style == "num":
        # numeric only when unambiguous (day > 12); otherwise fall back to text
        if d.day <= 12:
            return "%d %s %d" % (d.day, MONTHS[d.month - 1], d.year)
        if region == "EU":
            return "%02d/%02d/%02d" % (d.day, d.month, d.year % 100)
        return "%02d/%02d/%d" % (d.month, d.day, d.year)
    raise ValueError(style)


def po_str(n):
    return "PO-%06d" % n


def fmt_po_ref(n, style="dash"):
    if style == "dash":
        return "PO-%06d" % n
    if style == "hash":
        return "#%d" % n
    if style == "dots":
        return "P.O. %d" % n
    if style == "bare":
        return "%d" % n
    raise ValueError(style)


def fmt_qty(qty, sku, style="us", pack_mode=None):
    """pack_mode None -> '120 EA'; 'paren' -> '10 CS (120 EA)'; 'bare' -> '10 CS'. Returns (text, uom)."""
    pack = ITEMS[sku]["pack"]
    if pack_mode and pack and qty % pack["size"] == 0:
        n = qty // pack["size"]
        if pack_mode == "paren":
            return "%s %s (%s EA)" % (fmt_int(n, style), pack["unit"], fmt_int(qty, style)), pack["unit"]
        return "%s %s" % (fmt_int(n, style), pack["unit"]), pack["unit"]
    return "%s EA" % fmt_int(qty, style), "EA"


def fmt_unit_price(cents_per_ea, sku, style="us", uom="EA"):
    if uom == "EA":
        return fmt_money(cents_per_ea, style)
    size = ITEMS[sku]["pack"]["size"]
    return "%s/%s" % (fmt_money(cents_per_ea * size, style), uom)


# ---------------------------------------------------------------- OCR swaps

DIGIT_SWAP = {"0": ["O"], "1": ["l", "I"], "5": ["S"]}
TEXT_SWAP = {"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "0": "O", "1": "l", "5": "S"}


def ocr_swap_one(text, rng, region=None):
    """Swap exactly one digit (0/1/5) in text (restricted to char range `region`) if possible."""
    lo, hi = region if region else (0, len(text))
    cands = [i for i in range(lo, hi) if text[i] in DIGIT_SWAP]
    if not cands:
        return text
    i = rng.choice(cands)
    return text[:i] + rng.choice(DIGIT_SWAP[text[i]]) + text[i + 1:]


def ocr_text_noise(text, rng, rate=0.04):
    out = []
    for ch in text:
        if ch in TEXT_SWAP and rng.random() < rate:
            out.append(TEXT_SWAP[ch])
        else:
            out.append(ch)
    return "".join(out)


# ---------------------------------------------------------------- noise config

def canonical_doc_cfg():
    return {"date": "iso", "num": "us", "pack": None, "po_ref": "dash", "alias": None,
            "site": None, "reorder": None, "ocr": False}


def pack_applicable(case_lines):
    """case_lines: list of (sku, qty_list) -> True if some line can be written in packs."""
    for sku, qtys in case_lines:
        pack = ITEMS[sku]["pack"]
        if pack and any(q > 0 and q % pack["size"] == 0 for q in qtys):
            return True
    return False


def choose_noise_types(rng, stratum, present_docs, has_pack):
    applicable = [t for t in NOISE_TYPES
                  if (t != "handwritten_note" or "gr" in present_docs)
                  and (t != "uom_pack" or has_pack)]
    if stratum == "clean":
        return []
    if stratum == "messy":
        k = rng.choice([2, 3, 3, 4])
    elif stratum == "real":
        k = rng.choice([0, 1, 1, 2])
    else:  # in_transit: light noise, presentation only
        k = rng.choice([0, 1, 2])
    k = min(k, len(applicable))
    return sorted(rng.sample(applicable, k), key=NOISE_TYPES.index)


def build_noise_cfg(rng, types, supplier_id, present_docs, pack_docs=None, big_docs=None):
    """pack_docs: docs where at least one line can be written in packs.
    big_docs: docs with a value >= 1000 (so a no-separator style is visibly different)."""
    pack_docs = pack_docs if pack_docs is not None else list(present_docs)
    big_docs = big_docs if big_docs is not None else list(present_docs)
    s = SUPPLIERS[supplier_id]
    eu = s["number_format"] == "EU"
    cfg = {d: canonical_doc_cfg() for d in present_docs}
    supplier_docs = [d for d in ("invoice", "shipping_notice") if d in present_docs]

    def pick_docs(cands, p=0.7):
        chosen = [d for d in cands if rng.random() < p]
        if not chosen:
            chosen = [rng.choice(cands)]
        return chosen

    if "date_format" in types:
        for d in pick_docs(present_docs):
            cfg[d]["date"] = rng.choice(["dmy_text", "mdy_text", "dmy_upper", "num", "num"])
    if "number_format" in types:
        for d in pick_docs(present_docs):
            if d in supplier_docs and eu:
                cfg[d]["num"] = rng.choice(["eu", "eu", "eu_code", "eu_sym"])
            else:
                cfg[d]["num"] = rng.choice(["us_sym", "us_plain", "us_code"] if d in big_docs
                                           else ["us_sym", "us_code"])
    if "uom_pack" in types and pack_docs:
        first = ["invoice"] if (s["bills_in_packs"] and "invoice" in pack_docs) else []
        rest = [d for d in pack_docs if d not in first]
        chosen = set(first) | set(d for d in rest if rng.random() < 0.5)
        if not chosen:
            chosen = {rng.choice(pack_docs)}
        for d in sorted(chosen):
            cfg[d]["pack"] = rng.choice(["paren", "bare"])
    if "po_ref_format" in types:
        style = s["po_ref_style"] if s["po_ref_style"] != "dash" else rng.choice(["hash", "dots", "bare"])
        cands = [d for d in present_docs if d != "po"]
        for d in pick_docs(cands, 0.8):
            cfg[d]["po_ref"] = style if (d in supplier_docs or rng.random() < 0.5) else \
                rng.choice(["hash", "dots", "bare"])
    if "vendor_alias" in types:
        for d in pick_docs(present_docs):
            cfg[d]["alias"] = rng.choice(s["aliases"])
    if "field_reorder" in types:
        for d in pick_docs(present_docs):
            cfg[d]["reorder"] = rng.randrange(1, 10 ** 9)
    if "ocr_char_noise" in types:
        for d in pick_docs(present_docs):
            cfg[d]["ocr"] = True
    return cfg
