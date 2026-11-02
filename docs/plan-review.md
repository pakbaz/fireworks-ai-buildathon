# Plan review: suggested changes to plan.md

Reviewed November 2, 2026, 12:00 PM PT, against the Builder Guide, the Submission & judging page, Fireworks docs, and new research on existing products. [plan.md](plan.md) is strong. These are the changes I recommend, in priority order. Each is small.

Sources: [Builder Guide](https://hackersquad.io/events/fireworks-deploy-with-microsoft-nvidia/resources), [Submission & judging](https://hackersquad.io/events/fireworks-deploy-with-microsoft-nvidia/resources?tab=submission), [Fireworks pricing](https://docs.fireworks.ai/serverless/pricing), [System One decisions API](https://docs.fireworks.ai/api-reference/post-systemone.md), [existing solutions notes](notes/existing-solutions.md).

## What the official pages say (verified today)

| Item | Official text |
|---|---|
| Start submitting | "Start submitting by 3:30 PM and aim to finish by 4:00 PM." |
| Video | **"Video Submission by 4:00 PM"**, under 120 seconds, aim for under 60 |
| Close | 4:30 PM Pacific, fully uploaded and processed |
| Repo | "Public open-source repository", with setup and evaluation code |
| Results | Baseline model, dataset, metric, method, what improved, **tradeoffs disclosed** |
| Evidence | Same held-out cases, 100+ varied examples, **uncertainty estimates or statistical testing** |
| Scoring | Benchmark 40%, Business value 25%, Technical 20%, Presentation 10%, Docs 5% |
| Prizes | 1st $10,000, 2nd $5,000, 3rd $3,000, **NVIDIA Best-Use Award (DGX Spark)**. All require Fireworks. |
| Optional | Clickable app, fine-tuning. A notebook or API demo can earn full marks. |

Note: the "Resources" tab has no links yet. The Builder Guide links a sample "great submission" on Notion; open it in a browser, it does not render without JavaScript.

## Must fix

### 1. Safety-gate scoring bug

plan.md section 4 says: "a WAIT prediction on a non-WAIT case counts as ESCALATE." That means a real discrepancy predicted as WAIT would count as **caught**. It is not caught. Nobody looks at it.

**Change:** for the safety gate, only an `ESCALATE` prediction counts as caught. A `WAIT` or `CLEAR` on a real-discrepancy case is a miss. For the false-escalation metric on agreeing cases, keep counting `WAIT` as not-clear (conservative).

### 2. Timeline uses relative clock; deadlines are earlier than it assumes

plan.md says "two hours" and "submission open 3:30." Actual:

| Clock (PT) | Checkpoint |
|---|---|
| 12:15 | Schema frozen. Fireworks models verified live. Frontier key confirmed. |
| 12:30 | 50 **dev** cases in repo (see fix 3). |
| 1:15 | 150 test cases frozen and hashed. Baseline run started. |
| 2:30 | All arms run. Results table generated from saved outputs. |
| 2:45 | Repo public, README results, tradeoffs, limitations. |
| 3:15 | Video recorded (under 60 seconds if possible). |
| 3:30 | Start submitting. Video in by 4:00. Done by 4:30. |

### 3. Add a dev split; keep test truly held out

plan.md uses "50 sample cases" for everyone to test against, then freezes 150 test cases. If the 50 come from the test set, prompts and rules get tuned on test data.

**Change:** generate 50 **dev** cases with a different seed. Tune prompts, regexes, and any threshold only on dev. Freeze and hash the 150 test cases before any arm runs on them.

### 4. Add uncertainty and a paired test

The rules ask for uncertainty estimates or statistical testing.

**Change:** report Wilson or exact 95% intervals for false-escalation rate and the safety gate count. Compare arm 4 against arm 2 with a paired McNemar test on the 105 agreeing cases (same cases, escalated or not). This is a few lines of `scipy` or `statsmodels`.

## Should change

### 5. Pick text models, not vision models

plan.md chose OCR-style text, which is right for 3 hours. But the arm 4 candidates are vision models (`qwen3-vl-8b-instruct`, `qwen3-vl-235b`). Use text models with verified serverless pricing (input / cached / output per 1M tokens):

| Role | Model | Price | Why |
|---|---|---|---|
| Extractor | `accounts/fireworks/models/nemotron-lightning-3p5-30b-a3b` | $0.05 / $0.01 / $0.20 | Cheapest. NVIDIA model, which makes us a candidate for the **NVIDIA Best-Use Award**. |
| Extractor fallback | `accounts/fireworks/models/glm-5p3-flash` | $0.15 / $0.03 / $0.50 | Used in Fireworks structured-output docs |
| Re-read | `accounts/fireworks/models/deepseek-v4p1-flash` or `gpt-oss-120b` | $0.30 / $0.006 / $1.20 or $0.15 / $0.015 / $0.60 | Stronger, still cheap |
| Arm 3 (open, simple) | Same model as the re-read step | | Keeps the arm 3 vs 4 ablation clean |

Live-test each with one JSON-schema call at 12:15. Catalog listing does not prove account access. Model IDs above follow the pricing page links; confirm exact IDs in the console.

### 6. Use Fireworks Rune for a calibrated decision (new arm or harness step)

Fireworks has a decision model, **Rune** (`accounts/fireworks/models/rune`), served through the System One decisions API. It reads a state once and returns **calibrated probabilities** for typed questions. It never generates output tokens. Price: $0.042 per 1M input tokens. Text only.

Why it fits:

- plan.md logs a self-reported `confidence` and does not score it, correctly. Rune gives a real probability instead.
- With a probability we can draw a **risk vs. coverage curve** and pick a threshold on dev. That is strong benchmark evidence.
- It is a distinctive Fireworks feature, which helps with Fireworks judges.

Suggested use (one request per case):

```json
{
  "model": "accounts/fireworks/models/rune",
  "state": { "extracted": "...", "check_results": "...", "supplier_notes": "..." },
  "questions": {
    "documents_agree": { "type": "noul", "instructions": "Do the PO, invoice and goods receipt agree on item, quantity and price?" },
    "reason": { "type": "choice", "instructions": "Main issue, if any", "criteria": { "none": "...", "qty_mismatch": "...", "price_mismatch": "...", "wrong_po": "...", "wrong_warehouse": "...", "duplicate_invoice": "...", "in_transit": "...", "unreadable": "..." } }
  }
}
```

Keep the code checks as the authority. Rune only decides among cases the code could not settle (for example, an `unreadable` field after re-read). Fail closed if the call errors. Measure it as arm 4 with and without Rune if time allows; otherwise make it stretch goal 1.

### 7. Fine-tuning: drop it today

A fine-tuned model needs a dedicated deployment. That costs time and GPU spend against $50 of credits, and it would need its own dev/test discipline. Move to "future work."

### 8. Strengthen "Existing solutions" with the closest prior work

Add to section 1a:

- **[docmatch](https://github.com/franklinmdev/docmatch)** (closed models only): matching rules are near-perfect on clean data and fire wrongly on 0.7% of clean cases, but **48.4% of documents still go to human review end to end**, because extraction is weak (line-item F1 0.374). This is the best evidence that reading, not rules, drives escalation. It directly supports our hypothesis.
- Oracle Fusion Intelligent Document Recognition marks unclear invoices "Incomplete" for a person to fix; matching is tolerance rules ([Oracle docs](https://docs.oracle.com/en/cloud/saas/financials/25d/fappp/intelligent-document-recognition.html)).
- Vendor accuracy claims (Vic.ai 99%, Stampli 97 to 100%, Coupa "100% ERP-ready") have no published denominator. Label them unverified.

**Positioning sentence for README and video:**

> Commercial AP suites promise touchless matching but publish no false-escalation numbers. We publish an open benchmark showing whether open models on Fireworks cut false escalations on messy but agreeing invoices, while still catching every real discrepancy, at lower cost than a frontier model.

### 9. Budget check

150 test + 50 dev cases, about 3,000 tokens each, across arms 3 and 4 with re-reads, is well under $1 on the models above. The $50 credit is enough for several full reruns. Cost is not a constraint; do not cut runs to save money.

## Nice to have

- **Frontier prompt sensitivity:** run the baseline with 2 prompt wordings on dev, report the spread. Shows the baseline was fair.
- **Cost per 100 invoices:** express the result in the README as "reviews avoided per 100 invoices" and "$ per 100 invoices." Business value is 25%.
- **Demo:** one messy-but-agreeing invoice: frontier escalates, harness clears it with field-level evidence, then the results table with intervals. Keep under 60 seconds.

## Unchanged and correct

- Real discrepancies always escalate.
- OCR-style text instead of images.
- JSON supplier notes, not a graph.
- No supplier-email agent.
- Fail closed on unreadable decision-critical fields.
- Identical case packet for every arm.
- Primary metric with a safety gate.

## Action items

1. Fix the safety-gate scoring rule (fix 1).
2. Redeem the $50 Fireworks credit: the code is claimed in the HackerSquad Builder Terminal. Log in to fireworks.ai, click your name at the bottom left, **Credits**, **Redeem Promo**.
3. Live-test Nemotron Lightning, GLM 5.3 Flash, and Rune at 12:15.
4. Make the repo public before 3:30 and test the link signed out.
