#!/usr/bin/env python3
"""Assemble the narration: trimmed lines from the original take plus new result lines, with exact timing.

usage: vo_build.py SCRATCH  (reads vo/maya_raw.wav, vo/maya_words.json, vo/pickups/r1-5.wav + r1-5.json)
"""
import json, re, subprocess, sys
import numpy as np, soundfile as sf
SP = sys.argv[1]
TEMPO = 1.05
GAP = .22
SENT, COMMA = .17, .10
# Word index ranges kept from the take, per scene. Dropped lines shorten the scene.
KEEP = [[(0, 18)], [(19, 32)], [(33, 47)], [(57, 87)], [(88, 105)], [(106, 116), (123, 148)], [(153, 159), (167, 188)], [(189, 204)], [(205, 231)]]
HOLD_AFTER = {3: .55, 5: .35}  # beats for "Three of four were nothing" and "Both get the same documents"
END_HOLD = 1.0
BUCKETS = 7
a, sr = sf.read(f"{SP}/vo/maya_raw.wav")
W = json.load(open(f"{SP}/vo/maya_words.json"))


def runs_of(y):
    win = int(sr * .01); n = len(y) // win
    db = 20 * np.log10(np.sqrt(np.array([np.mean(y[k * win:(k + 1) * win] ** 2) for k in range(n)]) + 1e-12))
    out = []; k = 0
    while k < n:
        if db[k] < -38:
            j = k
            while j < n and db[j] < -38:
                j += 1
            if j - k >= 6:
                out.append((k * .01, j * .01))
            k = j
        else:
            k += 1
    return out


def fade(c):
    n = min(int(sr * .012), len(c) // 2)
    if n:
        c = c.copy(); c[:n] *= np.linspace(0, 1, n); c[-n:] *= np.linspace(1, 0, n)
    return c


def tighten(y, words, t0, t1, runs):
    """Audio for y[t0:t1] with shortened pauses; returns samples and word timings relative to its start."""
    pieces = []; cur = 0.0; tmap = [(t0, 0.0)]; last = t0
    for s, e in runs:
        if s <= t0 or e >= t1:
            continue
        d = e - s
        tgt = SENT if d >= .3 else COMMA
        if d <= tgt:
            continue
        c = fade(y[int(last * sr):int((s + tgt / 2) * sr)])
        pieces.append(c); tmap.append((s + tgt / 2, cur + len(c) / sr)); cur += len(c) / sr
        last = e - tgt / 2; tmap.append((last, cur))
    c = fade(y[int(last * sr):int(t1 * sr)])
    pieces.append(c); cur += len(c) / sr; tmap.append((t1, cur))
    tx, ty = zip(*tmap)
    return np.concatenate(pieces), [dict(w, s=float(np.interp(w["s"], tx, ty)), e=float(np.interp(w["e"], tx, ty))) for w in words]


def snap(t, runs, prefer_end):
    near = [r for r in runs if r[0] - .3 <= t <= r[1] + .3]
    if near:
        r = min(near, key=lambda r: abs((r[1] if prefer_end else r[0]) - t))
        return r[1] - .03 if prefer_end else r[0] + .05
    return t - .02 if prefer_end else t + .03


raw_runs = runs_of(a)
def build(pads):
  global out, cur, words, sections, onsets, ends
  out = []; cur = 0.0; words = []; sections = []; onsets = []; ends = []
  def add(seg, ws, gap_after):
    global cur
    sections.append(len(words)); onsets.append(cur)
    for w in ws:
        words.append(dict(w, s=w["s"] + cur, e=w["e"] + cur))
    out.append(seg); cur += len(seg) / sr; ends.append(cur)
    out.append(np.zeros(int(gap_after * sr))); cur += gap_after
  for i, ranges in enumerate(KEEP):
      segs = []; ws = []; c0 = 0.0
      for r, (w0, w1) in enumerate(ranges):
          t0 = snap(W[w0]["s"], raw_runs, True); t1 = snap(W[w1]["e"], raw_runs, False)
          seg, wl = tighten(a, [dict(W[j], old=j) for j in range(w0, w1 + 1)], t0, t1, raw_runs)
          if r:
              segs.append(np.zeros(int(.12 * sr))); c0 += .12
          ws += [dict(w, s=w["s"] + c0, e=w["e"] + c0) for w in wl]
          segs.append(seg); c0 += len(seg) / sr
      add(np.concatenate(segs), ws, GAP + HOLD_AFTER.get(i, 0))
  for i in range(1, 6):
      y, s2 = sf.read(f"{SP}/vo/pickups/r{i}.wav")
      assert s2 == sr
      rr = runs_of(y)
      t0 = rr[0][1] - .03 if rr and rr[0][0] < .02 else 0.0
      t1 = rr[-1][0] + .05 if rr and rr[-1][1] > len(y) / sr - .03 else len(y) / sr
      wl = json.load(open(f"{SP}/vo/pickups/r{i}.json"))
      seg, wl = tighten(y, [w for w in wl], t0, t1, rr)
      add(seg, wl, (GAP + pads.get(i, 0)) if i < 5 else 0)


build({})
k = 1 / TEMPO
def centre_gap():
    c = (onsets[BUCKETS] + onsets[BUCKETS + 1]) / 2 - .17
    return 2 * c - (cur + END_HOLD * TEMPO)
d = centre_gap()
pads = {}
if d > 0:
    pads = {i: min(.6, d / 4) for i in (1, 2, 3, 4)}
    build(pads)
    d = centre_gap()
elif d < 0:
    HOLD_AFTER[5] += -d / 2
    HOLD_AFTER[6] = HOLD_AFTER.get(6, 0) + -d / 2
    build(pads)
    d = centre_gap()
print("after padding, centre error", round(d * k, 3), "pads", {i: round(v, 2) for i, v in pads.items()})
if d < -.05:
    print("WARNING: before the buckets is shorter than after; add holds before scene", BUCKETS)
extra_end = max(0.0, d) * k
y = np.concatenate(out)
sf.write(f"{SP}/vo/built.wav", y, sr, subtype="PCM_24")
subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", f"{SP}/vo/built.wav", "-af", f"atempo={TEMPO}", "-ar", "48000", f"{SP}/vo/built_tempo.wav"], check=True)
timed = dict(words=[dict(w, s=w["s"] * k, e=w["e"] * k) for w in words], sections=sections, onsets=[o * k for o in onsets], ends=[e * k for e in ends], dur=cur * k, end_hold=END_HOLD + extra_end)
json.dump(timed, open(f"{SP}/vo/timed2.json", "w"))
names = "papers agree maria nothing cantread frontier knows BUCKETS dial test score why ordinary pumps".split()
b = timed["onsets"][7]; be = timed["onsets"][8]
for n, o, e in zip(names, timed["onsets"], timed["ends"]):
    print(f"{n:9s} {o:6.2f}-{e:6.2f} {e-o:5.2f}")
print("total", round(timed["dur"] + timed["end_hold"], 2), "end hold", round(timed["end_hold"], 2), "before", round(b, 2), "bucket", round(be - b, 2), "after", round(timed["dur"] - be, 2))
