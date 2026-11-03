"""Animated result plots, drawn in the explainer's visual language. Every value below is from results.md."""
import glob, os, re
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, S = 1920, 1080, 2  # drawn at 2x and downsampled for clean edges
BG, CARD, INK, INK2, MUTED, HAIR, TRACK = "#eff3ed", "#f7f9f6", "#04120b", "#47534d", "#6f7a74", "#d3dbd1", "#e0e6de"
KIMI, OURS, ORANGE, NEUTRAL = "#3d8bd4", "#0e8052", "#d16f3c", "#98a39d"  # KIMI/OURS checked with validate_palette.js
FONTS = os.environ.get("CUT_FONTS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"))


def _font(pattern, size, axes):
    f = ImageFont.truetype(glob.glob(os.path.join(FONTS, pattern))[0], size * S)
    if axes:
        info = f.get_variation_axes()
        f.set_variation_by_axes([axes.get(a["name"].decode() if isinstance(a["name"], bytes) else a["name"], a["default"]) for a in info])
    return f


_cache = {}
def head(size):
    return _cache.setdefault(("h", size), _font("Bricolage*", size, {"Weight": 750, "Width": 100, "Optical Size": 48}))
def body(size, weight=400):
    return _cache.setdefault(("b", size, weight), _font("Inter*", size, {"Weight": weight, "Optical Size": 24}))


def ease(p):
    p = float(np.clip(p, 0, 1))
    return p * p * p * (p * (6 * p - 15) + 10)


def mix(c1, c2, a):
    p = lambda c: np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], float)
    return tuple(int(x) for x in p(c1) * (1 - a) + p(c2) * a)


class Canvas:
    def __init__(self):
        self.img = Image.new("RGB", (W * S, H * S), BG)
        self.d = ImageDraw.Draw(self.img)

    def text(self, xy, s, font, fill=INK, anchor="la", alpha=1.0):
        if alpha <= 0:
            return
        c = mix(BG, fill, alpha) if isinstance(fill, str) else fill
        self.d.text((xy[0] * S, xy[1] * S), s, font=font, fill=c, anchor=anchor)

    def rect(self, x0, y0, x1, y1, fill, r=0, outline=None):
        self.d.rounded_rectangle((x0 * S, y0 * S, x1 * S, y1 * S), radius=r * S, fill=fill, outline=outline, width=S)

    def bar(self, x, y, w, h, color, r=6):
        """Square at the baseline, rounded at the data end."""
        if w <= 0:
            return
        if w < 2 * r:
            self.rect(x, y, x + max(w, 3), y + h, color)
            return
        self.rect(x, y, x + w, y + h, color, r)
        self.rect(x, y, x + r, y + h, color)

    def card(self, x0, y0, x1, y1):
        self.rect(x0 + 2, y0 + 4, x1 + 2, y1 + 4, "#e3e9e1", 10)
        self.rect(x0, y0, x1, y1, CARD, 10, HAIR)

    def swatch_legend(self, x, y, items, font):
        for color, label in items:
            self.rect(x, y + 5, x + 26, y + 31, color, 5)
            self.text((x + 38, y), label, font, INK2)
            x += 38 + font.getlength(label) / S + 46

    def chip(self, x, y, s, fill, alpha):
        if alpha <= 0:
            return
        f = body(27, 650)
        w = f.getlength(s) / S + 40
        c = mix(CARD, fill, alpha)
        self.rect(x, y, x + w, y + 50, c, 25)
        self.d.text(((x + 20) * S, (y + 25) * S), s, font=f, fill=mix(CARD, "#ffffff", alpha), anchor="lm")

    def done(self):
        return np.array(self.img.resize((W, H), Image.LANCZOS))[:, :, ::-1]


class Timeline:
    """Finds when a phrase is spoken, whichever way the transcript wrote the numbers."""
    def __init__(self, words, t0, t1):
        self.keys = [re.sub(r"[^a-z0-9]", "", w["w"].lower()) for w in words]
        self.words, self.t0, self.t1 = words, t0, t1

    def at(self, phrases, frac):
        for ph in phrases:
            p = [re.sub(r"[^a-z0-9]", "", x.lower()) for x in ph.split()]
            for j in range(len(self.keys)):
                if self.keys[j:j + len(p)] == p:
                    return self.words[j]["s"]
        print(f"  note: {phrases} not found, using {frac:.0%} of the scene")
        return self.t0 + (self.t1 - self.t0) * frac


GROW = .7


def panel(c, x, y, w, h, title, sub, rows, chip, t):
    """rows: (label, color, value, text, scale max, start, track)"""
    c.card(x, y, x + w, y + h)
    pad = 30
    c.text((x + pad, y + 26), title, body(34, 700))
    c.text((x + pad, y + 72), sub, body(25), MUTED)
    bar_w = w - 2 * pad - 118
    ry = y + 132
    for label, color, value, txt, vmax, start, track in rows:
        c.text((x + pad, ry), label, body(27, 500), INK2)
        by = ry + 42
        if track:
            c.bar(x + pad, by, bar_w, 58, TRACK)
        e = ease((t - start) / GROW)
        bw = bar_w * value / vmax * e
        if value == 0 and e > 0:
            c.rect(x + pad, by, x + pad + 4, by + 58, color)
        c.bar(x + pad, by, bw, 58, color)
        tip = (x + pad + bar_w + 14) if track else (x + pad + max(bw, 4) + 14)
        c.text((tip, by + 29), txt, body(38, 700), INK, "lm", alpha=ease((t - start - GROW * .4) / .3))
        ry += 152
    if chip:
        c.chip(x + pad, y + h - 76, chip[0], chip[1], ease((t - chip[2]) / .35))


def title(c, s, size=64, y=72, line=74):
    for i, l in enumerate(s.split("\n")):
        c.text((110, y + i * line), l, head(size))


FOOT = "All invoices are synthetic. Cost is model cost only."


class TestWaffle:
    def __init__(self, tl):
        self.fill = tl.at(["in one hundred forty", "in 140", "one hundred forty", "140"], .55)
        r = np.random.default_rng(4)
        self.order = np.zeros(210)
        pick = r.permutation(210)[:140]
        self.order[pick] = np.arange(1, 141)

    def __call__(self, t):
        c = Canvas()
        title(c, "The hard test: every document agrees.")
        c.text((110, 160), "210 invoices. Nothing looks wrong on the page.", body(32), INK2)
        c.swatch_legend(110, 226, [(ORANGE, "140 wrong compared with company history"), (CARD, "70 fine look-alikes")], body(30))
        c.rect(110 + 38 + body(30).getlength("140 wrong compared with company history") / S + 46, 231, 110 + 64 + body(30).getlength("140 wrong compared with company history") / S + 46, 257, CARD, 5, HAIR)
        cols, rows = 21, 10
        tw, th, gap = 72, 58, 9
        x0, y0 = 110, 300
        prog = ease((t - self.fill) / 1.5) * 140
        for i in range(210):
            x, y = x0 + (i % cols) * (tw + gap), y0 + (i // cols) * (th + gap)
            on = self.order[i] and self.order[i] <= prog
            c.rect(x, y, x + tw, y + th, ORANGE if on else CARD, 5, None if on else HAIR)
        return c.done()


class Scoreboard:
    def __init__(self, tl):
        k1 = tl.at(["caught"], .2)
        k2 = tl.at(["six false", "6 false", "with six", "with 6"], .4)
        o1 = tl.at(["ours caught"], .55)
        o2 = tl.at(["with none"], .75)
        o3 = tl.at(["at a"], .82)
        self.p = [("Problems caught", "out of 140 real problems", [("Kimi K3", KIMI, 121, "121", 140, k1, True), ("Our system", OURS, 139, "139", 140, o1, True)], ("18 more caught", OURS, o1 + .6)),
                  ("False alarms", "out of 70 fine invoices", [("Kimi K3", KIMI, 6, "6", 10, k2, False), ("Our system", OURS, 0, "0", 10, o2, False)], ("No false alarms", OURS, o2 + .4)),
                  ("Model cost", "per 100 invoices", [("Kimi K3", KIMI, 1.08, "$1.08", 1.08, o3 - .3, False), ("Our system", OURS, .0563, "$0.06", 1.08, o3 + .1, False)], ("19x cheaper", OURS, o3 + .6))]

    def __call__(self, t):
        c = Canvas()
        title(c, "Catches more, with no false alarms, far cheaper.")
        c.swatch_legend(110, 166, [(KIMI, "Kimi K3 alone, told exactly what to check"), (OURS, "Our system: GLM 5.3 Flash + checks + company knowledge")], body(29))
        w = 547
        for i, (a, b, rows, chip) in enumerate(self.p):
            panel(c, 110 + i * (w + 29.5), 250, w, 600, a, b, rows, chip, t)
        c.text((110, 890), FOOT, body(26), MUTED)
        return c.done()


class Why:
    def __init__(self, tl):
        self.a = tl.at(["without company", "without"], .15)
        self.b = tl.at(["with it"], .45)
        self.c = tl.at(["so a cheap", "so a"], .72)

    def __call__(self, t):
        c = Canvas()
        title(c, "Company knowledge makes the difference.")
        c.text((110, 160), "Problems caught, out of 140", body(32), INK2)
        c.card(110, 225, 1810, 845)
        rows = [("Cheap model + our checks, no company knowledge", NEUTRAL, 40, self.a), ("Cheap model + our checks + company knowledge (our system)", OURS, 139, self.b), ("Frontier model + our checks + company knowledge", KIMI, 140, self.c)]
        y = 262
        bw = 1500
        for label, color, v, start in rows:
            c.text((150, y), label, body(32, 500), INK2)
            c.bar(150, y + 50, bw, 62, TRACK)
            e = ease((t - start) / GROW)
            c.bar(150, y + 50, bw * v / 140 * e, 62, color)
            c.text((150 + bw + 16, y + 81), str(v), body(46, 700), INK, "lm", alpha=ease((t - start - .3) / .3))
            y += 190
        c.chip(110, 875, "The knowledge and the checks do the work. The reader can be the cheap one.", OURS, ease((t - self.c - .5) / .35))
        c.text((110, 950), FOOT, body(26), MUTED)
        return c.done()


class Ordinary:
    def __init__(self, tl):
        b = tl.at(["both catch"], .05)
        s = tl.at(["twelve", "12"], .3)
        o = tl.at(["the tradeoff", "the trade"], .5)
        k = tl.at(["to a person"], .85)
        self.p = [("Problems caught", "out of 375 real problems", [("Kimi K3", KIMI, 374, "374", 375, b, True), ("Our system", OURS, 373, "373", 375, b + .25, True)], ("About the same", OURS, b + 1.0)),
                  ("Fine invoices sent to a person", "out of 500 fine invoices", [("Kimi K3", KIMI, 1, "1", 30, k, False), ("Our system", OURS, 27, "27", 30, o + .5, False)], ("The trade-off", ORANGE, o + .3)),
                  ("Model cost", "for 1,000 invoices", [("Kimi K3", KIMI, 9.20, "$9.20", 9.20, s - .3, False), ("Our system", OURS, .757, "$0.76", 9.20, s, False)], ("12x cheaper", OURS, s + .6))]

    def __call__(self, t):
        c = Canvas()
        title(c, "On ordinary invoices: cheaper, with one trade-off.")
        c.swatch_legend(110, 166, [(KIMI, "Kimi K3 alone"), (OURS, "Our system: GLM 5.3 Flash + checks + company knowledge")], body(29))
        w = 547
        for i, (a, b, rows, chip) in enumerate(self.p):
            panel(c, 110 + i * (w + 29.5), 250, w, 600, a, b, rows, chip, t)
        c.text((110, 890), FOOT, body(26), MUTED)
        return c.done()


class Pumps:
    def __init__(self, tl):
        self.a = tl.at(["this hospital"], .3)
        self.b = tl.at(["eighty two", "82", "eightytwo", "one invoice"], .08)
        self.pay = tl.at(["says pay"], .65)
        self.ask = tl.at(["ours asks"], .85)

    def __call__(self, t):
        c = Canvas()
        title(c, "One invoice: 82 infusion pumps.")
        c.text((110, 160), "Every document agrees. The bill is $396,506.", body(32), INK2)
        c.card(110, 225, 1810, 575)
        y = 256
        for label, color, v, start in [("Most this hospital ever ordered", NEUTRAL, 11, self.a), ("This invoice", ORANGE, 82, self.b)]:
            c.text((150, y), label, body(32, 500), INK2)
            e = ease((t - start) / GROW)
            bw = 1500 * v / 82 * e
            c.bar(150, y + 50, bw, 72, color)
            c.text((150 + max(bw, 4) + 16, y + 86), str(v), body(54, 700), INK, "lm", alpha=ease((t - start - .3) / .3))
            y += 160
        for x, name, verdict, color, start in [(110, "Kimi K3 alone", "PAY", KIMI, self.pay), (975, "Our system", "ASK A PERSON", ORANGE, self.ask)]:
            c.card(x, 610, x + 835, 900)
            c.text((x + 40, 640), name, body(36, 600), INK2)
            e = ease((t - start) / .35)
            if e > 0:
                c.rect(x + 40, 710, x + 795, 860, mix(CARD, color, e), 14)
                c.d.text(((x + 417) * S, 785 * S), verdict, font=head(84), fill=mix(CARD, "#ffffff", e), anchor="mm")
        c.text((110, 950), "Synthetic invoice. Both systems recommend; neither makes payments.", body(26), MUTED)
        return c.done()


PLOTS = [TestWaffle, Scoreboard, Why, Ordinary, Pumps]
