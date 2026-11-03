# Submission text (copy into the HackerSquad project form)

Form: https://hackersquad.io/builders/dashboard/events/cmvhfug2f0014pg23mya02wru/builder#project
Judged commit: `3073420` (use the latest commit on `main` if more changes land before submitting, and say which).
Repository: https://github.com/pakbaz/fireworks-ai-buildathon (must be public before judging)
Demo video (1 min 56 s): https://github.com/pakbaz/fireworks-ai-buildathon/blob/main/media/demo-video.mp4
Live results dashboard: https://claude.ai/artifact/NyWmdZFGwhRAp6yQZBsFue (share it from its Share menu first)

## Project name

Invoice Reconciliation: catching what the paperwork can't show

## One-line summary

An open model on Fireworks reads invoices; plain code checks them against what the company already knows. It catches 139 of 140 problems a frontier model misses 19 of, at about a nineteenth of the cost.

## Task and intended user

Accounts-payable analysts must confirm that a purchase order, shipping notice, goods receipt and invoice agree before paying. About one invoice in five is escalated to a person at roughly $10 each, yet the costliest problems pass every document check: a changed payment address, a quantity far above anything ever ordered, an item the supplier never sold, a price above what it always charges, a near-duplicate invoice. Only company history reveals them.

## Approach

GLM 5.3 Flash (Fireworks serverless, low reasoning) reads all four documents into fields and marks anything it cannot read. Deterministic code then runs the three-way match, chain-of-custody diagnosis (supplier shipped short vs lost in transit), duplicate and remaining-quantity checks, and history checks against company knowledge: supplier history built from past invoices, item pages (pack sizes, value, category) and supplier pages. A business dial turns risk and dollars at stake into Pay, Wait or Ask a person, with defaults from what the company knows. Every escalation names the failed check. No payment is ever made automatically.

## Business value

Fewer invoices on the analyst's desk, and the expensive history problems caught on every invoice at about $0.06 per 100 invoices in model cost. The checks are explicit and auditable, and the reader model is interchangeable, so the cheapest adequate model can be used.

## Evaluation

- **Baseline:** Kimi K3 (`accounts/fireworks/models/kimi-k3`), one call per invoice with the same documents and company knowledge, explicitly told to check supplier history. Original runs without that instruction are kept and labelled.
- **Our model:** GLM 5.3 Flash (`accounts/fireworks/models/glm-5p3-flash`), reasoning_effort low.
- **Data:** synthetic, generated with fixed seeds and checked by `generator/check.py`. History test: 210 invoices (140 anomalies across seven types, 70 benign look-alikes). Document test: 1,000 invoices (375 real problems across six types, 500 correct or messy, 125 in transit). Separate train and dev splits; test frozen before any run; one layout and one supplier held out in test.
- **Metrics:** problems caught, fine invoices sent to a person, reason correct, model cost, latency. API errors counted and excluded, never treated as decisions.

| Test | Kimi K3 alone | Ours |
|---|---|---|
| History problems: caught | 121 / 140 | **139 / 140** |
| History problems: false alarms | 6 / 70 | **0 / 70** |
| History problems: cost per 100 invoices | $1.08 | **$0.06** |
| Documents (1,000): caught | 374 / 375 | 373 / 375 |
| Documents: fine invoices sent to a person | **1 / 500** | 27 / 500 |
| Documents: cost for 1,000 | $9.20 | **$0.76** |

- Same checks with Kimi reading: 140/140. Our checks without company knowledge: 40/140. The knowledge and checks do the work; the cheap model is enough.
- Low vs default reasoning on GLM, same invoices: 56 to 73% cheaper, 2.5 to 4.4x faster, same catch rate.

## Limitations

All data is synthetic. The history test covers the seven anomaly types the checks were written for (new examples, unseen seed). On ordinary document problems and on scanned images, Kimi K3 raises fewer false alarms (images: 2/50 vs our 18/50). Payment-address checks compare locations, not verified bank identities. Risk values are heuristic, not calibrated.

## How to reproduce

```bash
python3 -I generator/generate.py && python3 -I generator/context.py   # data (or use the committed files)
cp .env.example .env    # add a Fireworks key
GLM_REASONING=low python3 -m harness.run --row glm_harness_wiki --split test_context --tag low
python3 -m harness.run --row kimi_alone --split test_context
python3 eval/dashboard_data.py   # recompute reported numbers from saved predictions, no API calls
```

Full results with the file behind every number: `results.md`.

## Sponsor track

Built on Fireworks serverless inference (GLM 5.3 Flash and Kimi K3). No NVIDIA- or Microsoft-specific components.
