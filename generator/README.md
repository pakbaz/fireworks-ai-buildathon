# Synthetic PO / invoice reconciliation data

One command rebuilds everything (wiki, three splits, test images, manifest) and then runs the checker:

```bash
python3 -I generator/generate.py            # ~1 min; exits non-zero if the checker fails
python3 -I generator/generate.py --no-images  # skip PNG rendering (checker will then fail on the image subset)
python3 -I generator/check.py                 # re-check existing outputs only
```

Python 3 standard library plus Pillow. Fully deterministic: same code and seeds give byte-identical files
(seeds: train 1001, dev 2002, test 3003; images seeded by case id). No network, no model calls.

| File | Role |
|---|---|
| `world.py` | Companies, items, suppliers (+1 test-only), templates (3 shared + 1 test-only per doc type), policy, wiki pages |
| `noise.py` | Canonical and noisy value formatting, OCR swaps, per-case noise configuration (8 noise types) |
| `templates.py` | Four layout families that render a structured document to OCR-style text and record how each decision-critical value was written |
| `cases.py` | Builds one case: gold records, mutation, billing history, open POs, handwriting, templates, label |
| `generate.py` | Split plans (exact stratum/reason/company counts), writes `data/*.jsonl`, `wiki/`, `data/manifest.json` |
| `render_images.py` | 100 test cases (25 per stratum) rendered to degraded grayscale PNGs under `data/images/<case_id>/<doc>.png` |
| `check.py` | Recomputes every label from gold only, re-derives every rendered critical value from the text, checks counts, billing history, held-out isolation, wiki, images, manifest hashes |

## Case fields beyond the brief
- `open_pos`: other open POs of the same supplier (key facts only). In `wrong_po` cases it holds the PO the invoice cites;
  ~30% of other cases carry unrelated open POs as distractors.
- `billing_history[*]` also has `po_number` and `invoice_date`. Entries are either (a) a prior paid partial delivery on
  this PO (the PO states ordered / previously paid / open balance and the receipt and invoice cover only the open
  balance), (b) the duplicate itself in `duplicate_invoice` cases, or (c) paid invoices on other POs for SKUs that are
  not on this invoice.
- `label.mutation` (what was changed) and `label.render_meta` (noise config per doc, handwriting, rendered tokens) are
  hidden debugging aids for the checker.
- `images` (test only): `{doc: "data/images/<case_id>/<doc>.png"}`.

## Text conventions
- Handwriting is transcribed as `[handwritten: '12 ✓ JM']`; a struck-out printed value as `[struck-out: 10 EA]`.
  A handwritten received quantity is authoritative.
- Numeric dates (`25/11/26` EU, `11/25/2026` US) are only used when the day is > 12, so they are never ambiguous;
  otherwise the date_format noise uses `3 Nov 2026`, `Nov 3, 2026` or `03-NOV-26`.

## Context-anomaly set

```bash
python3 -I generator/context.py   # writes data/dev_context.jsonl (seed 2102), data/test_context.jsonl (seed 3103),
                                  # data/context_manifest.json, then runs generator/context_check.py
```

All four documents agree (a three-way match passes); the problem is visible only against supplier history built from
`data/train.jsonl` gold (and `wiki/history/` when present) or the wiki. Seven anomaly types (stratum `context_anomaly`)
and five benign look-alikes (stratum `context_benign`, `label.benign_type`). Each label has `context_basis` (one
sentence) and `signal_sku`. Invoices in this set carry a `Remit payment to / Bank` line (`gold.invoice.remit_bank`).
Pack-change lines carry `stated_pack` in gold. The only wiki edit is `approved_new_items` on SUP-MERIDIAN,
SUP-VOLTEDGE and SUP-KESTREL (`world.APPROVED_NEW_ITEMS`); their new hashes are in `data/context_manifest.json`, which
`check.py` accepts. `check.py` also runs the context checker when the context files exist.
