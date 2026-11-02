"""Render a fixed subset of test cases to scanned-looking grayscale PNGs (Pillow only).

Printed text: Courier (t1/t3) or Helvetica (t2/t4) laid out on the character grid of the OCR text.
Handwriting ("[handwritten: '...']"): Bradley Hand Bold, with the tick drawn as a polyline (the font
has no U+2713 glyph). "[struck-out: X]": X printed and struck through by hand.
Then: optional rubber stamp, paper texture, speckle, rotation 1-3 deg, downscale/upscale, gaussian blur.
"""
import math
import os
import random
import re
import shutil

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

COURIER = "/System/Library/Fonts/Courier.ttc"
HELVETICA = "/System/Library/Fonts/Helvetica.ttc"
HAND = "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf"
W, H = 773, 1000
MARGIN = 30
MARK = re.compile(r"\[handwritten: '([^']*)'\]|\[struck-out: ([^\]]*)\]")
TICK = "✓"
_FONTS = {}


def font(path, size, index=0):
    key = (path, size, index)
    if key not in _FONTS:
        _FONTS[key] = ImageFont.truetype(path, size, index=index)
    return _FONTS[key]


def select_cases(cases, n_per_stratum=25, seed=3003):
    rng = random.Random(seed * 7 + 1)
    chosen = []
    for k, s in enumerate(("clean", "messy", "real", "in_transit")):
        for j, co in enumerate(("northside", "caseworks")):
            want = 13 if (k + j) % 2 == 0 else 12
            pool = sorted((c for c in cases if c["label"]["stratum"] == s and c["company"] == co),
                          key=lambda c: c["case_id"])
            struck = [c for c in pool if "[struck-out" in (c["documents"]["gr"] or "")]
            hand = [c for c in pool if c not in struck and "[handwritten" in (c["documents"]["gr"] or "")]
            first = rng.sample(struck, min(4, len(struck))) + rng.sample(hand, min(2, len(hand)))
            rest = [c for c in pool if c not in first]
            chosen += first + rng.sample(rest, want - len(first))
    return chosen


def draw_tick(d, x, y, size, ink):
    pts = [(x, y + size * 0.55), (x + size * 0.3, y + size * 0.9), (x + size * 0.85, y + size * 0.1)]
    d.line(pts, fill=ink, width=max(2, size // 8), joint="curve")
    return x + size


def draw_hand(page, x, y, text, fs, rng):
    """Draw handwriting on its own layer, baseline-aligned with the printed line, slightly rotated."""
    hf = font(HAND, int(fs * 1.6))
    base = int(fs * 2)
    layer = Image.new("L", (int(fs * 1.6 * (len(text) + 2) * 0.75) + 40, int(fs * 3)), 0)
    ld = ImageDraw.Draw(layer)
    cx = 10
    for part in re.split("(%s)" % TICK, text):
        if part == TICK:
            # Bradley Hand has no U+2713 glyph: draw the tick as a polyline
            cx = draw_tick(ld, cx, base - int(fs * 1.1), int(fs * 1.1), 255) + int(fs * 0.3)
        elif part:
            ld.text((cx, base), part, font=hf, fill=255, anchor="ls")
            cx += int(ld.textlength(part, font=hf))
    layer = layer.crop((0, 0, cx + 10, layer.height))
    w0, h0 = layer.size
    layer = layer.rotate(rng.uniform(-5, 5), resample=Image.BICUBIC, expand=True)
    dx, dy = (layer.width - w0) // 2, (layer.height - h0) // 2
    ink = Image.new("L", layer.size, rng.randint(10, 45))
    page.paste(ink, (int(x - dx), int(y + fs * 0.8 - base - dy + rng.uniform(-2, 2))), layer)
    return x + cx


def render_text_page(text, tpl, rng):
    global W, H
    lines = text.rstrip("\n").split("\n")
    maxlen = max(len(MARK.sub(lambda m: "x" * (len(m.group(1) or m.group(2)) + 2), l)) for l in lines)
    # wide pages are scanned in landscape so the long side stays ~1000 px
    W, H = (1000, 773) if maxlen > 88 else (773, 1000)
    fs = int(min(17, (W - 2 * MARGIN) / (max(maxlen, 40) * 0.61), (H - 2 * MARGIN) / (len(lines) * 1.3)))
    lh = fs * 1.3
    mono = tpl[-1] in "13"
    pf = font(COURIER, fs, 1) if mono else font(HELVETICA, fs)
    page = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(page)
    # grid pitch = real advance of the monospace face (hinted advances differ from 0.6 em)
    cw = d.textlength("M" * 100, font=font(COURIER, fs, 1)) / 100.0
    ink = rng.randint(15, 45)
    y = MARGIN + rng.uniform(0, 12)
    for line in lines:
        x0 = MARGIN + rng.uniform(-1.5, 1.5)
        pos, col, xcur = 0, 0, x0

        def plain(seg, col, xmin):
            if mono:
                xs = max(x0 + col * cw, xmin)
                for i, ch in enumerate(seg):  # strict character grid keeps columns aligned
                    if ch != " ":
                        d.text((xs + i * cw, y), ch, font=pf, fill=ink)
                return xs + len(seg) * cw
            xe = xmin
            for m in re.finditer(r"\S+(?: \S+)*", seg):  # cells = text separated by 2+ spaces
                xs = max(x0 + (col + m.start()) * cw, xe + cw * 0.5 if xe > x0 else xe)
                d.text((xs, y), m.group(0), font=pf, fill=ink)
                xe = xs + d.textlength(m.group(0), font=pf)
            return max(xe, xmin)

        for m in MARK.finditer(line):
            seg = line[pos:m.start()]
            xcur = plain(seg, col, xcur)
            col += len(seg)
            if m.group(2) is not None:  # struck-out printed value
                s = m.group(2)
                xs = max(x0 + col * cw, xcur)
                d.text((xs, y), s, font=pf, fill=ink)
                xe = xs + d.textlength(s, font=pf)
                yy = y + fs * 0.42
                d.line([(xs - 3, yy + rng.uniform(-2, 2)), (xe + 3, yy + rng.uniform(-2, 2))],
                       fill=rng.randint(10, 50), width=max(2, fs // 7))
                if rng.random() < 0.5:
                    d.line([(xs - 2, yy - fs * 0.3), (xe + 2, yy + fs * 0.35)], fill=40, width=max(1, fs // 9))
                xcur = xe + cw
            else:
                hx = xcur + cw * 0.5 if (m.start() - pos <= 1 and pos > 0) else max(x0 + col * cw, xcur) + cw * 0.5
                xcur = draw_hand(page, hx, y, m.group(1), fs, rng) + cw
            col += len(m.group(0))
            pos = m.end()
        plain(line[pos:], col, xcur)
        y += lh
    return page


def stamp(page, rng, doc):
    word = "RECEIVED" if (doc == "invoice" or rng.random() < 0.8) else "PAID"
    sf = font(HELVETICA, rng.randint(30, 42))
    tmp = Image.new("L", (10, 10))
    tw = int(ImageDraw.Draw(tmp).textlength(word, font=sf))
    layer = Image.new("L", (tw + 40, 120), 0)
    ld = ImageDraw.Draw(layer)
    ld.rectangle([4, 4, tw + 35, 115], outline=255, width=4)
    ld.rectangle([12, 12, tw + 27, 107], outline=255, width=2)
    ld.text((20, 18), word, font=sf, fill=255)
    ld.text((22, 72), "AP DEPT  %02d %s" % (rng.randint(1, 28), rng.choice(["JAN", "MAR", "JUN", "SEP", "NOV"])),
            font=font(HELVETICA, 18), fill=255)
    # broken ink
    for _ in range(300):
        x, y = rng.randrange(layer.width), rng.randrange(layer.height)
        ld.ellipse([x, y, x + 3, y + 3], fill=0)
    layer = layer.rotate(rng.uniform(-25, 25), resample=Image.BICUBIC, expand=True)
    layer = layer.point(lambda v: int(v * rng.uniform(0.55, 0.8)) if False else int(v * 0.7))
    x = rng.randint(W // 6, W - layer.width - 20)
    y = rng.randint(H // 6, int(H * 0.6))
    page.paste(Image.new("L", layer.size, rng.randint(70, 110)), (x, y), layer)


def degrade(page, rng):
    # paper texture: low-frequency mottling
    gw, gh = 24, 31
    tex = Image.new("L", (gw, gh))
    tex.putdata([rng.randint(242, 255) for _ in range(gw * gh)])
    tex = tex.resize((W, H), Image.BICUBIC)
    page = ImageChops.multiply(page, tex)
    d = ImageDraw.Draw(page)
    for _ in range(rng.randint(800, 2500)):
        x, y = rng.randrange(W), rng.randrange(H)
        r = rng.choice([0, 0, 0, 1, 1, 2])
        d.ellipse([x, y, x + r, y + r], fill=rng.randint(60, 190))
    ang = rng.uniform(1, 3) * rng.choice([-1, 1])
    page = page.rotate(ang, resample=Image.BICUBIC, expand=False, fillcolor=rng.randint(200, 235))
    f = rng.uniform(0.6, 0.8)
    page = page.resize((int(W * f), int(H * f)), Image.BILINEAR).resize((W, H), Image.BILINEAR)
    page = page.filter(ImageFilter.GaussianBlur(rng.uniform(0.8, 1.6)))
    # quantize to 32 gray levels (scanner-like and keeps files small)
    return page.point(lambda v: (v // 8) * 8 + 4)


def render_case(case, root, rng):
    out = {}
    files = []
    rel_dir = os.path.join("data", "images", case["case_id"])
    os.makedirs(os.path.join(root, rel_dir), exist_ok=True)
    for doc in ("po", "shipping_notice", "gr", "invoice"):
        text = case["documents"][doc]
        if text is None:
            continue
        page = render_text_page(text, case["template_ids"][doc], rng)
        if rng.random() < 0.5:
            stamp(page, rng, doc)
        page = degrade(page, rng)
        rel = os.path.join(rel_dir, doc + ".png")
        page.save(os.path.join(root, rel), optimize=True)
        out[doc] = rel
        files.append(rel)
    return out, files


def render_subset(cases, root):
    img_root = os.path.join(root, "data", "images")
    if os.path.isdir(img_root):
        shutil.rmtree(img_root)
    files = []
    chosen = select_cases(cases)
    for c in sorted(chosen, key=lambda c: c["case_id"]):
        rng = random.Random("img-" + c["case_id"])
        c["images"], f = render_case(c, root, rng)
        files += f
    return files
