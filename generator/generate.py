"""Entry point: python3 -I generator/generate.py [--no-images] [--only SPLIT]

Writes wiki/, data/{train,dev,test}.jsonl, data/images/, data/manifest.json, then runs the checker.
Deterministic: same code + same seeds -> byte-identical outputs.
"""
import argparse
import hashlib
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from world import SPLITS, REASONS, GENERATOR_VERSION, write_wiki  # noqa: E402
from cases import build_case, SplitState  # noqa: E402

PREFIX = {"train": "TRAIN", "dev": "DEV", "test": "TEST"}


def stratum_counts(n):
    c = {"clean": n * 15 // 100, "messy": n * 35 // 100, "in_transit": n * 125 // 1000}
    c["real"] = n - sum(c.values())
    per, rem = divmod(c["real"], len(REASONS))
    reasons = {r: per + (1 if i < rem else 0) for i, r in enumerate(REASONS)}
    return c, reasons


def plan_split(name):
    size, seed = SPLITS[name]["size"], SPLITS[name]["seed"]
    c, reasons = stratum_counts(size)
    slots = []
    for s in ("clean", "messy"):
        slots += [(s, None)] * c[s]
    for r in REASONS:
        slots += [("real", r)] * reasons[r]
    slots += [("in_transit", None)] * c["in_transit"]
    slots = [(s, r, "northside" if i % 2 == 0 else "caseworks") for i, (s, r) in enumerate(slots)]
    rng = random.Random(seed)
    rng.shuffle(slots)
    held = [(False, False)] * size
    if name == "test":
        idx = rng.sample(range(size), size // 5)
        a, b = int(len(idx) * 0.4), int(len(idx) * 0.75)
        for k, i in enumerate(idx):
            held[i] = (True, False) if k < a else ((False, True) if k < b else (True, True))
    return seed, slots, held


def gen_split(name):
    seed, slots, held = plan_split(name)
    st = SplitState()
    cases = []
    for i, (stratum, reason, company) in enumerate(slots):
        cid = "%s-%05d" % (PREFIX[name], i + 1)
        cases.append(build_case(name, seed, i, cid, company, stratum, reason, held[i][0], held[i][1], st))
    return cases


def write_jsonl(path, cases):
    with open(path, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False, sort_keys=False) + "\n")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def summarize(cases):
    out = {"n": len(cases), "by_stratum": {}, "by_reason": {}, "by_company": {}, "by_stratum_company": {},
           "heldout_template": 0, "heldout_supplier": 0, "heldout_any": 0, "with_images": 0}
    for c in cases:
        lab = c["label"]
        for k, v in (("by_stratum", lab["stratum"]), ("by_reason", lab["reason_code"]),
                     ("by_company", c["company"]), ("by_stratum_company", lab["stratum"] + "/" + c["company"])):
            out[k][v] = out[k].get(v, 0) + 1
        out["heldout_template"] += c["heldout"]["template"]
        out["heldout_supplier"] += c["heldout"]["supplier"]
        out["heldout_any"] += c["heldout"]["template"] or c["heldout"]["supplier"]
        out["with_images"] += bool(c.get("images"))
    for k in ("by_stratum", "by_reason", "by_company", "by_stratum_company"):
        out[k] = dict(sorted(out[k].items()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-images", action="store_true")
    ap.add_argument("--no-check", action="store_true")
    a = ap.parse_args()

    data = os.path.join(ROOT, "data")
    os.makedirs(data, exist_ok=True)
    wiki_files = write_wiki(ROOT)
    summary = {}
    files = list(wiki_files)
    for name in ("train", "dev", "test"):
        cases = gen_split(name)
        if name == "test" and not a.no_images:
            from render_images import render_subset
            img_files = render_subset(cases, ROOT)
            files += img_files
        write_jsonl(os.path.join(data, name + ".jsonl"), cases)
        files.append("data/%s.jsonl" % name)
        summary[name] = summarize(cases)
        print(name, json.dumps(summary[name]["by_stratum"]), flush=True)
    manifest = {
        "generator_version": GENERATOR_VERSION,
        "entry_command": "python3 -I generator/generate.py",
        "seeds": {k: v["seed"] for k, v in SPLITS.items()},
        "sizes": {k: v["size"] for k, v in SPLITS.items()},
        "splits": summary,
        "files": {f: {"sha256": sha256(os.path.join(ROOT, f)), "bytes": os.path.getsize(os.path.join(ROOT, f))}
                  for f in sorted(files)},
    }
    with open(os.path.join(data, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    if not a.no_check:
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "check.py")])
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()
