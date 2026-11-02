# Feedback on the invoice-reconciliation harness

Reviewed at commit `9f4d735` (November 2, 2026). Every number below was recomputed from the saved prediction files in `runs/` against the labels in `data/`, not taken from the README or dashboard. Nothing was rerun against the API.

## Summary

The history-problem result is real and held out: the harness code did not change between the 42-case dev run and the 210-case test run, and the test numbers reproduce exactly. The design (model reads, code decides, every decision explained) is sound.

The headline comparison with Kimi K3 is not yet a fair one, though. Kimi was never asked to look for history problems, and the harness has not been run on the 1,000-case document test. Two short runs would settle both points.

## What is working

- **Held-out history result.** On `test_context` the harness caught 139 of 140 problems, with 0 of 70 false alarms and the correct reason on 139 of 140. In a case-by-case comparison it caught 120 problems Kimi missed, and Kimi caught none that the harness missed.
- **Cost.** $0.25 against $2.08 for the 210 cases, at 1.19 calls per invoice.
- **Auditable decisions.** Each escalation names the failed check and shows the dial's math. The `remit_to_changed` example in `docs/comparison.md` makes the business value obvious.
- **Prompt-injection resistance by design.** Code never reads wiki text as instructions. On the 1,000-case document test, Kimi's only miss (`TEST-00851`, a $33,342 duplicate) came from `SUP-ATLAS`, the supplier with the poisoned "do not escalate" page. That may be the injection at work, but it can't be confirmed: Kimi caught the other 5 Atlas duplicates.
- **Honest reporting.** "Not run" stays "Not run", and the README is upfront about how blind the test is.

## Issues, in priority order

### 1. Kimi K3 is not asked the same question

`prompts.ALONE` tells Kimi to compare the four documents. It never mentions supplier history, and its `reason_code` enum lists none of the seven history codes. Kimi does receive the history facts (`rows._history_summary` now includes `remit_to`, `ship_from` and `qty_max_by_company_sku`), but it has no instruction to use them and no valid label to report them with.

That explains the 0 of 140 correct reasons. Its 19 catches are mostly in the two types that map onto codes it already has: `pack_size_changed` (11 of 20) and `near_duplicate_invoice` (6 of 20). As things stand, 19 of 140 measures what Kimi notices without being asked, not what it can do.

**Fix:** add one instruction to `ALONE` telling it to compare the invoice against the supplier history (payment destination, ship-from, usual prices, largest past quantities, items supplied before, near-duplicate invoice numbers), and add the seven codes to its enum. Then rerun `kimi_alone` on `test_context` (about $2).

### 2. No run separates the checks from the cheap model

The history win comes from `supplier_history.context_issues`: deterministic rules that work the same whichever model did the reading. Without a "Kimi reading plus the same checks" row, it is impossible to tell how much of the gain comes from the code and how much from GLM 5.3 Flash.

**Fix:** add a `kimi_harness_wiki` row, `dict(kind="harness", model=FRONTIER_MODEL, wiki=True)`, and run it on `test_context` and on a test sample. The question an investor or judge will ask is whether the model swap matters at all.

### 3. The harness has not been run on the 1,000-case document test

Kimi's result on `test.jsonl` is 374 of 375 caught and 1 of 625 false escalations, for $9.20. The harness has only the 50-case dev result, and that has slipped since the last revision. In the current `runs/glm_harness_wiki/dev.jsonl`:

- `DEV-00007` and `DEV-00014` are fine "messy" invoices escalated after GLM misread them (a missing receipt, an unreadable receipt quantity).
- `DEV-00027` escalated because of an HTTP 429. It failed safe, but it is still an error recorded as a decision.

Fine invoices escalated are now 2 of 28, but `docs/comparison.md` still says 0 of 28.

**Fix:** run `glm_harness_wiki` on `test.jsonl`, record API errors as errors rather than escalations, and update `comparison.md`.

### 4. The test checks the same seven types the rules were written for

`context_issues` has one rule per generated anomaly type, and the rules were committed with the dev context set (`b354209`). `test_context` uses a different seed but the same generator and the same seven types. The 139 of 140 shows the rules hold up on fresh examples of known patterns, not that they detect new kinds of fraud.

**Fix:** state this limit next to the headline. If time allows, include a handful of anomaly types the rules were not written for, to show what happens when no rule matches.

### 5. Hard-coded thresholds and slow worst cases

- **Thresholds:** `price_above_history` fires above 1.10 × the historical mean (with n ≥ 5), and `quantity_spike` above 3 × the past maximum. These belong in `wiki/policy.json` with the other company settings, and their false-alarm rate on genuine price changes should be reported.
- **Latency:** on `test_context`, p95 latency is 30.2 s against Kimi's 5.2 s, and p50 is 7.0 s against 3.2 s. It is worth stating, because an AP team processing thousands of invoices will notice.

### 6. The single miss was a reading error that the checks could not see

`TESTCTX-0184` (shipped from Manila, history Shenzhen) was paid with "all checks passed". GLM read `ship_from` as the supplier's letterhead address ("Shengda Mobile Supply (Shenzhen) Co., Ltd., Shenzhen, CN") instead of the `Manila, PH` cell in the shipment table, and it reported nothing unreadable. `_place_known` then matched Shenzhen to Shenzhen, so the check passed.

This is the main risk of having the model read and code decide: a confident misread is invisible to the code. **Fix:** in `prompts.READ`, define `ship_from` as the ship-from cell of the shipment table, never the letterhead. Better still, have code cross-check the value against the raw shipping-notice text, so that a city appearing in the table but not in the read value is flagged.

## Requested runs before final numbers

| Run | Why | Approx. cost |
|---|---|---|
| `kimi_alone` with history instructions and codes, on `test_context` | Makes the headline comparison fair | ~$2 |
| `glm_harness_wiki` on `test.jsonl` | Measures the harness on the original job | ~$1–2 |
| `kimi_harness_wiki` on `test_context` (and a `test` sample) | Shows whether the gain is the checks or the model | ~$2–5 |

If the harness still leads clearly after the first run and matches Kimi on the second, the claim "a cheap open model plus checks beats the frontier model" is well supported. If the third run shows Kimi plus the checks doing equally well, the honest pitch becomes "the checks are the product, and the model is interchangeable". That is still a strong story: auditable fraud and billing screening on every invoice at about an eighth of the model cost.

## How these numbers were computed

- **Real problem:** an invoice where `label.real_discrepancy` is true.
- **Caught:** a real problem whose prediction `action` is `ESCALATE`.
- **False alarm:** an invoice without a real problem that was escalated. This includes in-transit invoices that should have been WAIT, which is why some dev counts are out of 35 rather than 28.
- **Cost and latency:** taken from each prediction's `cost_usd` and `latency_ms` fields.
