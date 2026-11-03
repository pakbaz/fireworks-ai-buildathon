#!/usr/bin/env python3
"""Demo video cut: steady framing, spotlights, reveals timed to the narration, then animated result plots.

usage: cut.py ORIGINAL.mp4 ORIG_WORDS.json TIMED_VO.json OUT.mp4 [--stills DIR]
"""
import json, re, subprocess, sys
import cv2
import numpy as np
import charts

W, H, FPS = 1920, 1080, 30
SPOT_DIM = .94
SPOT_FADE = .3
SCENE_CUTS = [0, 7.4, 13.7, 22.8, 34.3, 40.7, 55.0667, 70.4, 76.7667, 89.3, 106.8]
SRC_END = 112.7
DISSOLVE_FRAMES = 8


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


# frame: the steady view for the scene, sized to hold everything the scene ever shows.
# src0: where the source starts, after its title has finished typing, so no scene opens empty.
# timemap: (phrase, source time) so each item has appeared by the time its line starts.
# spots: (from phrase, to phrase or None for scene end, rect) moves attention while the camera stays still.
# push: optional single slow move, (phrase, rect, seconds).
SCENES = [
    {"frame": (100, 90, 1820, 790), "src0": .25,
     "timemap": [("three papers", 2.8), ("the order", 4.6)],
     "spots": [("the order", "the delivery", (125, 415, 640, 775)),
               ("the delivery", "and the invoice", (705, 415, 1215, 775)),
               ("and the invoice", None, (1285, 415, 1795, 775))]},
    {"frame": (100, 90, 1820, 850), "src0": 8.3,
     "timemap": [("same item", 8.5), ("when they line", 9.8), ("the bill pays", 11.25)],
     "push": ("the bill pays", (640, 250, 1840, 890), 1.4),
     "spots": [("same item", "when they line", (130, 525, 1790, 675)),
               ("the bill pays", None, (1285, 420, 1795, 840))]},
    {"frame": (100, 180, 1800, 1000), "src0": 14.8,
     "timemap": [("about one", 15.2), ("gets flagged", 17.4)],
     "spots": [("about one", None, (1165, 185, 1765, 1000))]},
    {"frame": (100, 90, 1820, 960), "src0": 23.5,
     "timemap": [("twelve units", 24.7), ("account", 26.4), ("an order", 28.1), ("all fine", 28.7),
                 ("only the", 29.8), ("@end-.95", 31.2), ("@end-.45", 32.0)],
     "spots": [("twelve units", "account", (130, 290, 530, 850)),
               ("account", "an order", (550, 290, 950, 850)),
               ("an order", "all fine", (970, 290, 1370, 850)),
               ("all fine", "only the", (130, 290, 1370, 850)),
               ("only the", "@end-.95", (1390, 290, 1790, 850))]},
    {"frame": (110, 90, 1620, 850), "src0": 35.2,
     "timemap": [("the software", 35.8), ("read them", 36.5), ("and guessing", 37.2), ("so it", 38.1)],
     "spots": [("read them", "and guessing", (990, 460, 1570, 690)),
               ("so it", None, (985, 745, 1305, 835))]},
    {"frame": (100, 90, 1820, 970), "src0": 41.7,
     "timemap": [("a frontier", 42.6), ("reads the", 43.5), ("we split", 46.0), ("a model", 48.2),
                 ("using what", 50.5), ("@end-.5", 51.5)],
     "spots": [("a frontier", "we split", (130, 280, 930, 860)),
               ("we split", "@end-.5", (990, 280, 1790, 860))]},
    {"frame": (100, 90, 1880, 830), "src0": 56.6,
     "timemap": [("a case", 57.05), ("a pump", 60.7), ("without the", 64.2), ("with it", 66.4)],
     "spots": [("a case", "a pump", (130, 290, 690, 640)),
               ("a pump", "without the", (1304, 290, 1864, 640)),
               ("without the", "with it", (130, 740, 796, 825)),
               ("with it", None, (804, 740, 1068, 825))]},
    # The three-bucket slide: the centre of the video.
    {"frame": (100, 90, 1820, 1000), "src0": 71.2,
     "timemap": [("every invoice", 72.0), ("pay", 72.98), ("wait", 73.62), ("or ask", 74.86)],
     "spots": [("pay", "wait", (130, 550, 590, 1000)),
               ("wait", "or ask", (730, 550, 1190, 1000)),
               ("or ask", None, (1330, 550, 1790, 1000))]},
    {"frame": (100, 90, 1820, 990), "src0": 78.6,
     "timemap": [("two pumps", 79.3), ("ask a", 82.5), ("two phone", 82.6), ("cheaper", 83.0)],
     "spots": [("two pumps", "two phone", (130, 290, 930, 830)),
               ("two phone", None, (990, 290, 1790, 830))]},
]


def ease(p):
    p = float(np.clip(p, 0, 1))
    return p * p * p * (p * (6 * p - 15) + 10)


def rect_to_cam(rect, pad=1.03):
    x0, y0, x1, y1 = rect
    z = max(1.0, min(W / ((x1 - x0) * pad), H / ((y1 - y0) * pad)))
    return clamp_cam((x0 + x1) / 2, (y0 + y1) / 2, z)


def clamp_cam(cx, cy, z):
    hw, hh = W / 2 / z, H / 2 / z
    return float(np.clip(cx, hw, W - hw)), float(np.clip(cy, hh, H - hh)), z


def spot_lit(rect):
    """1 inside the spotlight, 0 outside, with a soft edge."""
    m = np.zeros((H // 4, W // 4), np.float32)
    x0, y0, x1, y1 = [int(v / 4) for v in rect]
    cv2.rectangle(m, (x0, y0), (x1, y1), 1.0, -1)
    return cv2.GaussianBlur(m, (0, 0), 4)


class Scene:
    def __init__(self, idx, spec, words, old, sec_start, sec_end, t0, t1):
        self.t0, self.t1 = t0, t1
        keys = [norm(w["w"]) for w in words]

        def word_index(phrase):
            ph = [norm(x) for x in phrase.split()]
            for j in range(sec_start, sec_end):
                if keys[j : j + len(ph)] == ph:
                    return j
            raise ValueError(f"scene {idx}: {phrase!r} not found")

        def find(phrase):
            if phrase is None:
                return t1
            if phrase.startswith("@end"):
                return t1 + float(phrase[4:])
            return words[word_index(phrase)]["s"]

        self.src1 = (SCENE_CUTS[idx + 1] - 1 / FPS) if idx + 1 < len(SCENE_CUTS) else SRC_END
        tx, sx = [t0], [spec["src0"]]
        for phrase, s in spec["timemap"]:
            t = find(phrase)
            if t > tx[-1] + .02 and s > sx[-1]:
                tx.append(t)
                sx.append(s)
        tx.append(t1)
        sx.append(self.src1)
        self.tx, self.sx = np.array(tx), np.array(sx)
        self.cam = rect_to_cam(spec["frame"])
        self.push = None
        if "push" in spec:
            self.push = (find(spec["push"][0]), rect_to_cam(spec["push"][1]), spec["push"][2])
        self.spots = [(find(a), find(b), spot_lit(r)) for a, b, r in spec.get("spots", [])]

    def camera(self, t):
        cx, cy, z = self.cam
        if self.push and t > self.push[0]:
            e = ease((t - self.push[0]) / self.push[2])
            bx, by, bz = self.push[1]
            cx, cy = cx + (bx - cx) * e, cy + (by - cy) * e
            z = float(np.exp(np.log(z) + (np.log(bz) - np.log(z)) * e))
        return clamp_cam(cx, cy, z)

    def mask(self, t):
        """Brightness map. Adjacent spots crossfade, so the surround holds steady through a handoff."""
        active = []
        for start, end, lit in self.spots:
            amt = ease((t - start) / SPOT_FADE) * (1 - ease((t - end) / SPOT_FADE))
            if amt > 0:
                active.append((amt, lit))
        if not active:
            return None
        total = min(1.0, sum(a for a, _ in active))
        lit = sum(a * m for a, m in active) / sum(a for a, _ in active)
        return 1 - (1 - SPOT_DIM) * total * (1 - lit)


def warp(img, cam):
    cx, cy, z = cam
    M = np.array([[z, 0, W / 2 - z * cx], [0, z, H / 2 - z * cy]], np.float32)
    if abs(z - 1) < 1e-3:
        return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    out = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    amt = min(.5, .55 * (z - 1))
    if amt > .02:
        blur = cv2.GaussianBlur(out, (0, 0), 1.3)
        out = cv2.addWeighted(out, 1 + amt, blur, -amt, 0)
    return out


class Render:
    def __init__(self, original, old, timed):
        cap = cv2.VideoCapture(original)
        self.frames = []
        while True:
            ok, f = cap.read()
            if not ok:
                break
            self.frames.append(f)
        self.bg = self.frames[5][1000, 1000].astype(np.uint8)
        # Cut on measured speech onsets; transcribed word starts drift into the pause.
        self.cuts = [0.0] + [s - .17 for s in timed["onsets"][1:]]
        self.total = timed["dur"] + timed["end_hold"]
        bounds = self.cuts + [self.total]
        secs = timed["sections"] + [len(timed["words"])]
        words = timed["words"]
        self.scenes = [Scene(i, SCENES[i], words, old, secs[i], secs[i + 1], bounds[i], bounds[i + 1]) for i in range(len(SCENES))]
        n = len(SCENES)
        self.plots = [plot(charts.Timeline(words[secs[n + i]:secs[n + i + 1]], bounds[n + i], bounds[n + i + 1])) for i, plot in enumerate(charts.PLOTS)]
        self.scenes += self.plots

    def view(self, scene, t):
        if callable(scene):
            return scene(t)
        idx = int(round(float(np.interp(t, scene.tx, scene.sx)) * FPS))
        frame = self.frames[min(idx, len(self.frames) - 1)]
        mask = scene.mask(t)
        if mask is not None:
            big = cv2.resize(mask, (W, H), interpolation=cv2.INTER_LINEAR)
            frame = np.clip(frame * big[..., None], 0, 255).astype(np.uint8)
        return warp(frame, scene.camera(t))

    def frame_at(self, t):
        half = DISSOLVE_FRAMES / 2 / FPS
        for i, c in enumerate(self.cuts[1:]):
            if c - half <= t < c + half:
                e = ease((t - (c - half)) / (2 * half))
                return cv2.addWeighted(self.view(self.scenes[i], t), 1 - e, self.view(self.scenes[i + 1], t), e, 0)
        i = np.searchsorted(self.cuts, t, side="right") - 1
        out = self.view(self.scenes[i], t)
        if t > self.total - .45:
            a = (self.total - t) / .45
            out = cv2.addWeighted(out, a, np.full_like(out, self.bg), 1 - a, 0)
        return out


def main():
    original, old_path, timed_path, out = sys.argv[1:5]
    r = Render(original, json.load(open(old_path)), json.load(open(timed_path)))
    print("duration", round(r.total, 2), "cuts", [round(c, 2) for c in r.cuts], flush=True)
    enc = subprocess.Popen(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", out], stdin=subprocess.PIPE)
    n = int(round(r.total * FPS))
    for f in range(n):
        enc.stdin.write(r.frame_at(f / FPS).tobytes())
    enc.stdin.close()
    enc.wait()
    print("done", flush=True)


if __name__ == "__main__":
    main()
