# Review dashboard (design)

Design source for the analyst dashboard: a threshold dial, a queue ranked by expected loss, and the scanned documents with the disputed values highlighted.

Live version: [Invoice Review Dashboard](https://claude.ai/artifact/VxUudva72Qh8v7u8eNHSq9) (private until shared).

| File | Role |
|---|---|
| `Main.dc.html` | The page, in the Claude Design canvas format |
| `canvas.json` | Canvas index for that page |
| `locate_disputes.py` | Finds where each disputed value sits on the scans in `data/images/` |
| `located.json` | Output of that script for the 25 flagged test cases with scans |

`Main.dc.html` runs inside the Claude Design canvas, not on its own. Its `/_blob/...` image links resolve only in the published artifact, and the same scans are in `data/images/`. The version that runs from this repo is in [web/](../web/README.md).

## Rebuild the highlight boxes

Needs Pillow and NumPy, and the fonts `generator/render_images.py` uses (macOS).

```bash
python3 -I dashboard/locate_disputes.py                  # writes dashboard/located.json
python3 -I dashboard/locate_disputes.py /tmp/sheet.png   # also draws every box for checking by eye
```

The script replays the image renderer, then aligns each page to the committed scan, because the replay does not match the scans pixel for pixel.

## What is real and what is not

- Cases and scans come from `data/test.jsonl` and `data/images/`.
- Risk, dollars at risk and ranking come from `runs/kimi_alone/test.jsonl`, run on text. They are not harness results.
- Headlines and disputed fields come from the answer key (`label`). A live app needs them from the harness.
- Upload is simulated: any upload adds one held-back case to the queue.
- The escalation rule is expected loss above the threshold, which differs from `harness/dial.py`.
- The ÷5 caution margin behind Northside's suggested $2 is a proposal, and `wiki/policy.json` has no such field.
