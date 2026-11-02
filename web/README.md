# Review site

The analyst dashboard from [dashboard/](../dashboard/README.md), as a plain website that runs from this repo: a threshold dial, a queue ranked by expected loss, and the scans with the disputed values highlighted. No dependencies and no build step.

```bash
python3 -m http.server 8765 --bind 127.0.0.1
```

Run it from the repo root and open http://127.0.0.1:8765/web/. The page loads scans from `data/images/`, so serving `web/` alone leaves them broken.

| File | Role |
|---|---|
| `index.html`, `styles.css`, `app.js` | The page |
| `cases.json` | The 25 flagged cases with scans. Generated, do not edit |
| `build_data.py` | Rebuilds `cases.json` from saved files, with no model calls: `python3 web/build_data.py` |

## What is real and what is not

- Cases and scans come from `data/test.jsonl` and `data/images/`. All synthetic.
- Risk, dollars at risk and ranking come from `runs/kimi_alone/test.jsonl`, run on text. They are not harness results, because the harness has no saved run on `test`.
- Headlines and highlighted values come from the answer key (`label`). A live app needs them from the harness.
- Where Kimi K3 and the answer key disagree (TEST-00403), the page says so on the case.
- The ÷5 caution margin behind Northside's suggested $2 is a proposal, and `wiki/policy.json` has no such field.

## Changes from the design

- **Upload:** "Try a sample" adds a held-back case from the saved run and says so. Real files get listed and a note that they were not read. The design ran a fake "reading" step and returned the same case for any file.
- **Add supplier notes or policy:** removed, because nothing stored the files or approved them.
- **Undo:** works per company. In the design it could restore a case from the other company.
- **Partly billed POs:** the PO crop notes what is left to bill, so "Ordered 426" next to "Billed 26" makes sense (TEST-00256).
- **Why it ranks:** also shows the `harness/dial.py` comparison and Kimi K3's explanation.

## Escalation rule

The page escalates when expected loss is above the dial's dollar threshold. `harness/dial.py` compares expected loss with `(1 - risk) × review cost`. On these 25 cases `dial.py` escalates all of them, so a dial built on it would have nothing to move. The site keeps the dollar threshold and shows the `dial.py` numbers per case.

## Not built yet

- Live checks on uploaded documents. This needs a small server around `harness.api.analyze`, a Fireworks key, and a way to turn uploaded files into a case (company, supplier, wiki pages, as-of date).
- Saved review state: "Mark done" and "Not a problem" reset on reload.
