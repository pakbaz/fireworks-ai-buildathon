# Plan review 2 (1:25 PM)

Review of [plan.md](plan.md) and [problem-statement.md](problem-statement.md) as of commit `de43ecc`. The first review is in [plan-review.md](plan-review.md).

The new direction is good. It makes a stronger story: one open model, before and after, the business dial, and the chain-break diagnosis. The problem statement reads well for judges. My points are about **time, model access, and the one rule that could cost points**.

## Blockers (decide in the next 10 minutes)

### 1. No code is in the repo yet, and the timeline is about an hour behind

`main` has only docs. The plan expected 50 dev cases at 12:30, the before row on dev at 12:45, and the test set frozen at 1:15. If the code lives on laptops, push it now, even unfinished, so everyone builds against the same generator and schema.

About 2 hours of build remain (runs must finish by about 2:45 for a 3:15 video). Suggested cut line:

| Tier | Item | If late |
|---|---|---|
| **Must** | Generator (text), 50 dev + 200 test, frozen and hashed | Drop to 150 test |
| **Must** | Before row and after row on test, raw outputs saved | — |
| **Must** | Scorer: false escalation rate, safety gate count, Wilson intervals, one McNemar (after vs before) | — |
| **Must** | README results table, tradeoffs, limitations; repo public | — |
| Should | Ablation row (harness, no wiki) | Report as future work |
| Should | Business dial with two companies, cost per 100 invoices | Use one fixed threshold per company, no sweep |
| Could | 40 image cases | Show 3 to 5 image cases in the video only, no table |
| Could | Calibration curve, threshold sweep plot | Skip; report Brier score only |

Decide now which "Should" and "Could" items are dropped if a checkpoint slips, so nobody debates it at 2:30.

### 2. Kimi K2.5 may not be serverless

- The current [Fireworks serverless pricing page](https://docs.fireworks.ai/serverless/pricing) lists **Kimi K3**, not Kimi K2.5. Our earlier research found the K2.5 model page says "Serverless Not Supported". Its public page today only describes on-demand (dedicated GPU) deployment.
- An on-demand deployment costs GPU-hours and takes time to start. That does not fit $50 and two hours.
- **Action:** if the 12:15 live test did not return a serverless response from `accounts/fireworks/models/kimi-k2p5`, switch now. The fallback in the plan (`qwen3-vl-235b-a22b-instruct`) also needs a live check. If both fail, use a model listed on the serverless pricing page. Swap it into all three rows, as the plan says.

### 3. Budget: "never cut a run to save credits" is not safe on a big model

Rough call count: 240 cases × (before: 3 samples) + (harness: about 3 extractions + up to 3 re-reads + 1 classifier) ≈ 2,500 to 3,000 calls, plus the ablation, plus images (image tokens are large).

At Kimi K3 serverless prices ($3 input / $15 output per 1M tokens), 3,000 calls × 4,000 input tokens is about $36 of input alone, before output. Reasoning ("thinking") output at $15 per 1M can double that.

**Action:**
- Turn reasoning off or set it low for every call, in every row equally.
- Run all rows on the 50 dev cases first, read the `usage` totals, and multiply by 4.8 (240 / 50) before starting test.
- Cache every response to disk by case ID and row, so a crash never re-bills.
- If the projection exceeds about $40, cut the before row to 1 sample with logprob-free risk, or drop images to 20 cases.

## High risk for judging (40% of score)

### 4. "Frontier baseline" is in the official rubric

The rubric says: "A meaningful, reliable advantage over a **frontier-model baseline**." The mentor advice (one model, before and after) is a fair reading only if judges accept the bare open model as the frontier baseline.

**Cheap insurance (about 15 minutes, if anyone has a closed-model key):** run one closed frontier model, single prompt, temperature 0, on the 200 test cases, as a **reference row** in the results table. It is not a leaderboard. It answers the judge's question "how does this compare to GPT or Claude?" If the harness beats it, that is the headline. If not, the before/after story still stands.

If no key is available, add one sentence to the README: "Kimi K2.5 is an open frontier-class model; our baseline is that model with the same documents, wiki pages, and output schema, prompted directly." Ask a judge or mentor to confirm this reading before 3:00.

### 5. Make the safety gate the first number on screen

With the dial, Caseworks may write off small discrepancies by design. That is a sound business argument, but a judge skimming the table may read "misses." Put the Northside (hospital) gate first, as `X/37 caught`, then the dial results. Label Caseworks write-offs as "written off by policy, $ amount" in the same row.

## Consistency fixes in plan.md (5 minutes)

| Where | Issue | Fix |
|---|---|---|
| Overview diagram | Mentions "small open model" and "large open model"; one model is now used | Say "Kimi K2.5 (read)" and "Kimi K2.5 (re-read)" |
| Overview diagram | `A4 -.-> PKT` refers to a node that no longer exists | Change to `A3 -.-> PKT` |
| Section 3.1 | Says real images are a stretch goal | 3.5a makes 40 images core. Pick one. If images are "Could" per the cut line, say so in both places |
| Section 5, steps 2 and 4 | "Small open text model" and "larger open text model" | "Kimi K2.5" |
| Section 8 | "Documents are OCR-style noisy text, not images" | "Text for all cases; images for a 40-case subset" (already in a later bullet) |
| problem-statement.md flow | Same "small" and "large" model labels | Same fix |
| Section 4 | Safety gate example says `37/37` | Northside has about 37 or 38 discrepancies depending on rounding. Say "all N Northside discrepancies." |

## Method notes (keep, but be honest)

- **Calibration on 50 dev cases** gives only about 19 discrepancy cases. A monotone fit on that is noisy. Report it as "lightly calibrated," show the Brier score, and do not tune the dial threshold on test.
- **Before row at temperature 0.7 × 3** is fair as a risk estimate. Also report the single temperature-0 answer, because that is how people actually use a model.
- **Blind normalizer** is a strong idea. Mention it in the README under "how we kept ourselves honest."
- **Rate limits:** run cases with a small concurrency (8 to 16) and backoff on 429. Serial runs of ~3,000 calls will not finish in time.

## Unchanged and correct

Real discrepancies drive escalation at the hospital default. The chain-break codes (short_shipped vs lost_in_transit) are a great business detail. The wiki rules and the poisoned and expired pages are solid. Only ESCALATE counts as caught. Wilson intervals and McNemar tests are in. No fine-tuning. The repo must be public before submitting; it is still **private**.

## Next 10 minutes

1. Push whatever code exists to `main`.
2. Confirm which model actually answered serverless, and the token cost of one case.
3. Agree on the cut line above.
4. Decide on the closed-model reference row.
