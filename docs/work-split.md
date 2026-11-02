# Work split (2:00 PM)

Five people, about 1.5 hours of build left. Submit from 3:30, video by 4:00, close 4:30 PT. Cut line: [plan.md section 6a](plan.md).

## Shared contracts (do not change without telling everyone)

**Case file**, one JSON object per line in `data/{train,dev,test}.jsonl`, written by the generator:

```text
case_id, split, company (northside | caseworks), supplier_id, as_of_date,
documents: {po, shipping_notice | null, gr | null, invoice}   (OCR-style text)
billing_history: [{invoice_number, lines, status}]
wiki_refs: {supplier | null, items, policy}
images: {doc: path} (100 test cases only)
heldout: {template, supplier}
label: {stratum, real_discrepancy, reason_code, next_step, at_risk_usd, leg, noise_types, gold}
```

**Prediction file**, one JSON object per line in `runs/<row>/<split>[_images].jsonl`, written by the harness:

```text
case_id, row, model,
action (PAY | WAIT | ESCALATE)          the action at the company's default dial
model_action                             what the model itself said, where it said one
risk (0..1), at_risk_usd, reason_code, next_step, evidence,
features {...}                           harness only: checks, unreadable fields, read confidence
calls, tokens_in, tokens_out, cost_usd, latency_ms
```

Rows: `kimi_alone` (frontier baseline), `glm_alone` (before), `glm_harness` (middle, no wiki), `glm_harness_wiki` (after).

Every model response is cached on disk under `runs/cache/` by a hash of model, settings and messages. Reruns never re-bill. The Fireworks key lives in a local `.env` that is git-ignored; never commit it.

## Owners

| Who | Owns | Done when |
|---|---|---|
| **Deeksha** (data and model) | Dataset generator (running), harness on GLM 5.3 Flash, the four rows, dev then test runs, budget projection after dev | Dev runs by 2:30, test runs by 2:50, prediction files pushed |
| **Person 2** (evaluation) | `eval/score.py`: reads cases and prediction files. Safety gate first ("all N Northside discrepancies caught"), false escalation rate on agreeing cases, reviews, misses and dollars per 100 invoices per company at the default dial, Wilson and exact intervals, McNemar after vs frontier and after vs middle, reason-code accuracy (including short_shipped vs lost_in_transit), calibration fit on dev and Brier on test, threshold sweep curve PNG, a markdown results table for text and one for images, model calls and cost per 100 invoices per row | Works on a fake prediction file by 2:20, on real dev output by 2:40 |
| **Person 3** (data QA) | Hand-check 40 test cases (10 per stratum) and 15 images against their labels; log any wrong label in `docs/data-qa.md`; write `data/README.md` (data card: what is in each split, how it was made, license CC BY 4.0, limits) | QA log and data card by 2:45 |
| **Person 4** (story and submission) | Final README (problem, method, results table pasted from person 2, tradeoffs, limitations, how to reproduce), the 10-minute presentation, video update with real numbers, submission form, repo public at 3:00 and tested signed out, mentor sign-off on the baseline wording (plan section 5a) | README draft 2:45, deck 3:15, submitted 3:45 |
| **Person 5** (demo and dial) | A small demo notebook or page: walk one messy invoice through the harness (documents, fields read, checks, risk, dollars at risk, dial decision for Northside vs Caseworks), plus the dial explained with the sweep curve from person 2 | Demo ready for the video at 3:00 |

## Order of work for the next hour

1. 2:05 to 2:20: generator finishes; Deeksha pushes `data/` and `wiki/`. Person 2 builds the scorer against the contract above with a fake prediction file. Person 3 starts QA as soon as data lands.
2. 2:20 to 2:40: all four rows on dev. Projected test cost checked against the $50 credit.
3. 2:40 to 2:55: test runs; scorer on test; results table.
4. 2:55 onward: README, deck, video, submit.

If a checkpoint slips, take the fallback in plan section 6a. Nobody re-debates scope after 2:15.
