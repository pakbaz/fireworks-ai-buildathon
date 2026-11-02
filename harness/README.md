# Harness

Runs the four rows from [docs/plan.md](../docs/plan.md) section 5 over a split and writes one prediction per case to `runs/<row>/<split>[_images].jsonl` (format in [docs/work-split.md](../docs/work-split.md)).

| Row | Model | What it does |
|---|---|---|
| `kimi_alone` | Kimi K3 | Frontier baseline: one call with the whole packet and wiki pages; risk from the token probability of its action |
| `glm_alone` | GLM 5.3 Flash | Same single call; risk from its own stated confidence |
| `glm_harness` | GLM 5.3 Flash | Read all documents in one call, code checks, re-read only on a failed check or unreadable critical value, code classifier, business dial. No wiki |
| `glm_harness_wiki` | GLM 5.3 Flash | Same, plus company wiki: pack conversions in code and supplier and item hints on the re-read |

```bash
cp .env.example .env            # put your Fireworks key in .env (git-ignored)
python3 -m harness.run --row kimi_alone --split dev --limit 50
python3 -m harness.run --row glm_harness_wiki --split test
python3 -m harness.run --row glm_harness_wiki --split test --images   # the image subset, read from PNGs
```

- Every model response is cached in `runs/cache/` by a hash of model, settings and messages. Reruns are free, and the two harness rows share the first read.
- Swap the harness model with `HARNESS_MODEL=accounts/fireworks/models/<id>`; add its price to `config.py`.
- `risk` is uncalibrated; the scorer calibrates it on dev. `action` applies the business dial (escalate when risk × cost of a miss > (1 − risk) × review cost) with the company's wiki defaults.
- Honesty note: the harness was written from the plan and the case format, without reading the generator code. The same assistant wrote the generator's brief, so the normalizer is not fully blind; the held-out template and supplier in test are the guard.
