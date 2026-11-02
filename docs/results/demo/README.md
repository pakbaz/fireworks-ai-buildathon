# Fireworks demo — presentation figures (updated)

**Latest benchmark source reviewed:** [root results.md](../../../results.md), commit \`e9489c8a51666a845e69eddf10d7d54a04ec8270\` (November 2, 2026).
**What is new:** the complete **1,000-case document** result and the full **210-case low-reasoning history** result replace the earlier 300-case/default-reasoning figures.
**Provenance:** Every number comes from saved synthetic predictions and the repository's final \`results.md\`. No additional model inference was run for this presentation. The original full 1,000 GLM low-mode JSONL is too large for our review tool to ingest completely, so the full-document totals are taken from the team's committed \`results.md\`; we verified the 210-case low-mode prediction file directly.

## Open the presentation

**[Presentation deck (HTML)](index.html)** — self-contained, keyboard-controlled deck referencing the SVGs in this folder. **After cloning or downloading this folder, open \`index.html\` in a browser.** In GitHub's code view it displays as source; it is not a deployed website.

- Arrow keys / space: next or previous slide; **N**: show presenter notes; **F**: fullscreen.
- All illustrations are 1600 × 900 SVGs with legible text, reusable in a conventional slide deck. No external fonts or remote image dependencies.
- Slides 1–7 are the main story. Slides 8–9 are optional *business economics and scanned-image* backups; do not use the economics assumptions as realized ROI.
- Charts were authored from the benchmark evidence, not produced by the model, and are independent of the separately mocked analyst dashboard in \`dashboard/\`.

## Figures (presentation sequence)

| Slide | Use | File |
|---|---|---|
| 1 | **What is technically different?** Explain model reading, executable checks, company knowledge and controlled review | [07-harness-architecture.svg](07-harness-architecture.svg) |
| 2 | **One compelling failure:** 82 pumps compared with 11 historically; model recommends PAY, harness holds | [05-case-82-pumps.svg](05-case-82-pumps.svg) |
| 3 | **Headline:** 139/140 vs 121/140 context anomalies; no false alerts vs six; ~19× cheaper inference | [01-context-headline.svg](01-context-headline.svg) |
| 4 | **Causal story:** 40/140 without supplier knowledge, 139/140 with it | [06-causal-ablation.svg](06-causal-ablation.svg) |
| 5 | **Which checks add value?** Seven issue types, same Kimi reader with/without verification code | [02-anomaly-types.svg](02-anomaly-types.svg) |
| 6 | **Engineering optimization:** low reasoning versus default on 300 document cases | [04-low-reasoning-dev.svg](04-low-reasoning-dev.svg) |
| 7 | **Honest limitation:** complete 1,000-case document test, recall, review burden and cost | [03-document-tradeoff.svg](03-document-tradeoff.svg) |
| 8 | **Finance/controller backup:** a $10/review assumption shows why inference cost is not total cost | [08-review-economics-backup.svg](08-review-economics-backup.svg) |
| 9 | **Scanned-image robustness backup:** Kimi reads the synthetic scans better | [09-scanned-images-limit.svg](09-scanned-images-limit.svg) |

## Exact figures, denominator and qualification

### A. 210-case history-context benchmark

All four documents agree. **140** cases contain one of seven synthetic history anomalies; **70** are benign look-alikes. The frontier standalone model receives explicit history-check instructions.

| System | Detected of 140 | False alerts of 70 | Inference cost per 100 |
|---|---:|---:|---:|
| Kimi K3 alone | 121 (86.4%) | 6 (8.6%) | $1.080 |
| Kimi K3 + harness + wiki | 140 (100%) | 0 | $1.391 |
| **GLM 5.3 Flash low-reasoning + harness + wiki** | **139 (99.3%)** | **0** | **$0.056** |

- Directly inspected \`runs/glm_harness_wiki_low/test_context.jsonl\`: **210 cases**, 139 \`ESCALATE\` and 71 \`PAY\`, total model cost **$0.11824990** (dividing by 210 and multiplying by 100 yields **$0.0563 per 100**).
- For the same small GLM reader, removing company history/wiki (\`runs/glm_harness_low/test_context.jsonl\`) produced **40 escalations out of 140** synthetic anomalies and **170 PAY** total; the result is reported as **40/140** in \`results.md\`.
- In the **same Kimi reader** comparison, Kimi alone detects 121/140 while Kimi + deterministic checks detects 140/140. This is a strong demonstration of a *system design* gain, not that frontier models are intrinsically unable to compare history.
- About **19.2× lower model-inference cost** for GLM low-reasoning harness vs Kimi-alone; cost comparison **excludes human reviewers, application hosting, and financial losses**.
- Original Kimi baseline without explicit history instructions caught 19/140. That is **not** the fair headline and should only be shown as an example of prompt sensitivity.

### B. Full 1,000-case document benchmark

| System | Correctly escalated of 375 real discrepancies | False escalations of 500 correct | Total model inference cost |
|---|---:|---:|---:|
| Kimi K3 standalone | **374** (99.73%) | **1** (0.2%) | $9.20 |
| **GLM low-reasoning harness + wiki** | 373 (99.47%) | 27 (5.4%) | **$0.76** |

**Tradeoff:** roughly **12× lower model-inference cost**, but **one additional miss and 26 additional false human-review alerts**. Median per-invoice latency is approximately **3.4 s for Kimi**, **4.6 s for our system** (committed \`results.md\`). *Do not* claim equal detection performance or proven labor savings. Some cases are in transit and require \`WAIT\`; fine-invoice denominators exclude these.

### C. Reasoning-effort engineering experiment

**Same first 300 document cases**, default versus low-reasoning GLM harness, as reported in \`results.md\`:

| Metric | Default | Low | Interpretation |
|---|---:|---:|---|
| Recall on document discrepancies | 117/117 | 117/117 | Equal *on this 300-case subset only* |
| False escalations of 148 fine | 20 | 9 | Fewer false positives in low mode |
| Model cost / 100 | $0.29 | $0.08 | ~73% cheaper |
| Median latency | 22.2 s | 5.1 s | ~4.4× faster |

On the **separate 210-case history** comparison, default-reasoning GLM harness (versioned \`runs/glm_harness_wiki_v2/test_context.jsonl\`) caught **140/140**; low mode caught **139/140**. Thus low reasoning was not universally equally accurate. The current low-mode full results are the primary headline.

### D. Evidence-grounded single case

From \`examples/demo/TESTCTX-0149.json\`:
- Synthetic hospital invoice: **82** infusion pumps × **$4,835.44** = **$396,506.08**.
- Supplier history: largest prior buyer–supplier–item quantity **11**; executable condition: **quantity > 3 × 11 = 33**.
- Standalone Kimi, explicitly instructed to check the history, **recommended PAY** and said quantity was below the threshold.
- Harness result **ESCALATE**, reason \`quantity_spike\`. The human reviewer verifies the unusual order. No payment is executed.
- Invoice total is **not** an amount proven lost or saved; it is a synthetic invoice value. \`at_risk_usd\` is a synthetic policy-based exposure estimate.

### E. Scanned-image subset — backup result

The repository's latest `results.md` adds **100 synthetic rendered document scans**. Both systems were evaluated on the same 100 cases: **25 real problems, 50 fine invoices, 25 in transit**. I independently inspected both 100-row prediction files and verified the totals of decisions and model-cost sums (the correctness breakdown below comes from the root `results.md`).

| System | True discrepancies detected | False alerts among 50 fine | In-transit correctly WAIT | Model cost for 100 |
|---|---:|---:|---:|---:|
| Kimi K3 alone | **25/25** | **2/50** | **25/25** | $1.90 |
| GLM low + wiki harness | 24/25 | 18/50 | 21/25 | **$0.13** |

This is a serious input-quality limitation: the smaller model's image extraction creates many false disputes and some incorrect `WAIT` decisions. These are synthetically rendered documents, not a clinical real-invoice OCR test. **Do not** claim the full text-based benchmark proves scanned-image robustness. Source: `runs/glm_harness_wiki_low/test_images.jsonl` and `runs/kimi_alone_v2/test_images.jsonl`.

## Recommended ~100-second narration

- **0–10 s / architecture:** "A model extracts the evidence. Code checks it against the company's facts. A business dial routes exceptions to a person."
- **10–30 s / concrete case:** "The same documents all agree, but 82 infusion pumps is far beyond the historical maximum of 11. The frontier model recommended paying; our checks reliably flag the inconsistency."
- **30–50 s / headline:** "On 140 designed context anomalies, we catch 139; the explicitly prompted frontier model finds 121. We raise zero false alarms among 70 look-alikes and spend ~19× less on model inference."
- **50–65 s / components:** "Without the company knowledge, this model-and-check pipeline catches only 40 of the history anomalies."
- **65–80 s / efficiency:** "Switching GLM to low reasoning reduces our median time from 22 to 5 seconds on a paired 300-case document subset."
- **80–100 s / caveat and conclusion:** "On 1,000 general invoices, we catch 373/375 compared with Kimi's 374/375, but we create more false alerts. Better extraction and selective routing are our next steps. The advantage is auditable, executable business checks—not a magic prompt."

## Evaluator, design, and stakeholder guidance

- **ML evaluator:** compare **matched test cases**; show exact numerator/denominator; keep original and new prompts separate; disclose that the seven anomaly types were predefined and improved prompts followed prior feedback. "Zero observed false alarms" is not a population guarantee.
- **AP analyst:** prefer a specific issue code, source field and verified comparison over a vague model score. \`PAY\` means *recommendation*, not an automated payment.
- **Finance/controller:** token savings do not imply savings in human-review workload. At the project's illustrative $10/review, 26 extra false alerts would add **$260** in labor assumptions, dwarfing the **$8.44** model savings over the 1,000 document cases. Slide 8 is an **assumption-driven backup**, not measured ROI; it also excludes costs of missed problems.
- **UX/judge:** start with one striking case, then evidence of generality, component ablation, meaningful tradeoffs, and transparent limitations. Avoid tiny legends and unsupported fraud-prevention claims.
- **Security:** no verified supplier bank-account identity registry, no autonomous payments, no validated production financial data. The separate mocked \`dashboard/\` design has answer-key-derived highlights and should not be represented as live detection.

## Source-of-truth files

- Primary published summary: [../../../results.md](../../../results.md)
- 210 context cases: \`runs/glm_harness_wiki_low/test_context.jsonl\`, \`runs/glm_harness_low/test_context.jsonl\`, \`runs/kimi_alone/test_context.jsonl\`, \`runs/kimi_harness_wiki/test_context.jsonl\`.
- General documents: \`runs/glm_harness_wiki_low/test.jsonl\`, \`runs/kimi_alone/test.jsonl\`.
- Reasoning comparison: \`runs/glm_harness_wiki/test.jsonl\` (300 default), \`runs/glm_harness_wiki_v2/test_context.jsonl\` (210 default), corresponding low files.
- Example: \`examples/demo/TESTCTX-0149.json\`.
- Source code: \`harness/\`, \`generator/\`. Historical first-round charts in \`docs/results/dashboard/\` **have not** been rebuilt for all the new low-reasoning runs; this demo folder deliberately uses the updated sources.

**Rule for any future rerun:** update the source commit here and all affected numerator/denominator/cost values before presenting. Never silently overwrite a published result with a different prompt or reasoning setting.
