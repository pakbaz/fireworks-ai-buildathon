# Invoice exception/escalation rates and measuring "unnecessary human escalation"

## Q1. Credible data: exception rates, straight-through processing (STP), cost per invoice, causes

### Takeaway
The best primary public source is Ardent Partners' *State of ePayables 2025*: average exception rate **18.4%**, average cost **$9.84/invoice**, average processing time **8.2 days**. Best-in-Class teams have a 47% lower exception rate and do 1.8× more STP. Third-party summaries of these numbers often disagree, and I found **no public primary breakdown of exceptions caused by data capture vs. real price or quantity mismatches**.

### Cited Findings
- Ardent Partners, State of ePayables 2025 ("AP's Unfinished Journey", serialized Jan 2026): average invoice exception rate **18.4%**, average processing cost **$9.84**, average processing time **8.2 days**, **57%** of suppliers can send e-invoices, and AP staff spend **21.9%** of their time dealing with suppliers. It describes exceptions as "the biggest single reason" benchmarks aren't lower — [Ardent Payables Place](https://payablesplace.ardentpartners.com/2026/01/state-of-epayables-part-nine-ap-benchmarks-and-best-in-class-performance/)
- In the same report, Best-in-Class teams (the 20% with the lowest cost plus shortest cycle time) have 79% lower cost, 79% faster processing, 47% lower exception rate, 1.4× more suppliers on e-invoicing, and more than 1.8× the STP rate of peers. The public post does not give the absolute STP % — [Ardent](https://payablesplace.ardentpartners.com/2026/01/state-of-epayables-part-nine-ap-benchmarks-and-best-in-class-performance/)
- In the 2024 edition, the Best-in-Class exception rate was **9%**, described as "less than half the rate of their peers". It reported 59% lower exceptions, 78% lower cost, 82% faster processing and 2.1× STP — [Ardent Payables Place (Jan 2025)](https://payablesplace.ardentpartners.com/2025/01/best-of-2024-ap-performance-advantages-of-best-in-class/). Secondary summaries put 2024 at $2.78 vs $12.88 and 22% for "all others"; I did not verify these against the primary source — [Bottomline summary](https://www.bottomline.com/resources/the-state-of-epayables-2024)
- **Conflict:** one vendor blog says Ardent 2025 shows a 14% average exception rate, $9.40/invoice and 32.6% average STP — [agastyaai (vendor)](https://www.agastyaai.co/insights/one-invoice-in-seven-becomes-an-exception). This contradicts Ardent's own post (18.4%, $9.84). Treat the vendor figures as unreliable.
- Methodology and sponsorship: Ardent's numbers are **self-reported surveys of AP leaders**. The reports are commonly distributed by AP vendors (Bottomline, Corcentric and others), which suggests sponsorship; I did not confirm the 2025 sponsor list. Each company defines "exception" differently. The same operation can honestly report 5%, 8.3%, 15% or 25%, depending on line-level vs. invoice-level counting, PO-only vs. all invoices, and whether holds cleared by an automatic re-match count — [Fragment wiki (vendor, but a careful explainer)](https://fragment.ai/wiki/invoice-exception-rate-benchmarks)
- Exception rate ≠ 1 − touchless rate. Invoices can miss touchless processing without an exception (for example manual keying or waiting for approval), and auto-cleared holds count as exceptions but still finish touchless — [Fragment](https://fragment.ai/wiki/invoice-exception-rate-benchmarks)
- APQC cost per invoice: secondary sources quote a median of about **$5.83–$6.00** and a top quartile of **≤$2.07**. The APQC page returned 403, so I could not verify it — [APQC (blocked)](https://www.apqc.org/What-Is-the-Average-Cost-to-Process-an-Invoice); [Aequo summary](https://www.aequoap.com/research/cost-to-process-an-invoice)
- A widely circulated cause breakdown ("missing fields 34%, low confidence 28%, vendor mismatch 18%, table parsing 12%, duplicate 8%") is attributed to IOFM, but only on a vendor statistics page. I found no IOFM primary source; **do not cite it** — [digiparser (vendor)](https://www.digiparser.com/statistics/exception-rate-in-document-automation)

### Inferences
- A realistic headline for the pitch: "Even the industry average is roughly 1 in 5 invoices raising an exception (Ardent 2025: 18.4%), and the best teams sit near 9–10%." That sets up why noise-driven escalations matter.
- The team's "real vs. document-only" split is exactly what public benchmarks don't measure. That gap justifies the hackathon framing; it shouldn't be presented as a known statistic.

### Gaps
- No primary Levvel, Hackett or IOFM public data found on the share of exceptions from data capture vs. real mismatches. These reports are paywalled; secondary claims of an "equal split" have no source.
- Ardent's absolute STP % for 2025 isn't in the public post.

## Q2. Exception categories and relative frequency

### Takeaway
The standard categories are price variance, quantity variance, missing or late goods receipt (including goods in transit), missing or invalid PO, duplicates, and vendor or master-data mismatch. **I found no credible, primary, published frequency distribution across them.**

### Cited Findings
- Common three-way match failures include price variance, quantity over receipt, and late goods receipts. In one example, 2,000 of 3,000 flagged PO invoices cleared on the overnight re-match once the receipt posted. That shows receipt-timing holds can dominate counts if they are included — [Fragment](https://fragment.ai/wiki/invoice-exception-rate-benchmarks) (illustrative example, not survey data)
- Tolerance bands (for example a 2% price variance or a one-unit quantity difference) shift the exception rate without changing reality — [Fragment](https://fragment.ai/wiki/invoice-exception-rate-benchmarks)
- Vendor blogs list price and quantity mismatches as the top causes, and quote duplicates at about 1–2% of volume, with no primary source — [Tier2 Systems](https://tier2systems.com/en/blog/invoice-exceptions-ap-cost/); [autopayables](https://autopayables.com/blog/invoice-exception-handling)

### Inferences
- In the synthetic set, the team should **choose and report** the category mix rather than claim it is realistic. Receipt timing / goods in transit should be its own label ("wait and re-match"), not "contact supplier".

### Gaps
- No trustworthy category frequencies found.

## Q3. Evaluation design (escalate = positive; missed real discrepancy = costly false negative)

### Takeaway
Treat this as **selective classification / learning to defer**. Recommended primary metric: **unnecessary-escalation rate (false positive rate on document-only/noisy-clean cases) with recall on real discrepancies held at ≥ a fixed target**, ideally 100% on the test set and reported with a confidence interval.

### Cited Findings
- Learning to defer: a model either predicts or defers to an expert, and Madras et al. (NeurIPS 2018) introduced the framing — [arXiv 1711.06664 (URL from memory)](https://arxiv.org/abs/1711.06664). Mozannar & Sontag (ICML 2020) frame deferral as cost-sensitive learning and provide a consistent surrogate loss; they show the Madras loss is not consistent — [PMLR](https://proceedings.mlr.press/v119/mozannar20b.html)
- Selective classification evaluates a model with a **risk–coverage curve**: risk is error on the cases it auto-decides, and coverage is the fraction not deferred. Selection with Guaranteed Risk (SGR) picks a threshold that guarantees a risk bound with high probability — [Geifman & El-Yaniv 2017](https://arxiv.org/abs/1705.08500); [SelectiveNet 2019](https://arxiv.org/abs/1901.09192)
- LLM prompt sensitivity: formatting-only prompt changes moved accuracy by up to 76 points for LLaMA-2-13B. The authors recommend reporting a range across formats (FormatSpread) rather than a single prompt — [Sclar et al., ICLR 2024](https://arxiv.org/abs/2310.11324)
- Position/option-order bias: LLMs prefer certain answer positions or IDs — [Zheng et al., "LLMs Are Not Robust Multiple Choice Selectors", ICLR 2024 (URL from memory)](https://arxiv.org/abs/2309.03882)

### Inferences (recommended metric set)
- **Primary:** False-positive escalation rate on the "clean but messy" cases = escalated ÷ all document-only (no real discrepancy) cases, **subject to a gate** of real-discrepancy recall = 100% (or ≥ 99%) on the test set. Report the Wilson CI. With n real cases and zero misses, the 95% upper bound on miss rate is about 3/n (the "rule of three"), so 100 real cases only shows a miss rate of about ≤ 3%.
- **Secondary:**
  - (a) Recall/false negative rate on real discrepancies, broken down by category.
  - (b) Coverage / automation rate, meaning the share of all cases auto-cleared.
  - (c) A risk–coverage curve if the agent outputs a confidence score.
  - (d) Expected cost = C_FN·FN + C_FP·FP, using stated assumptions. For example, C_FP is about one manual review, priced from Ardent's $9.84 average. C_FN is the invoice $ at risk, which is many times larger.
  - (e) Reason-code accuracy, i.e. whether the escalation cites the right discrepancy.
  - (f) Stability: the spread of the metrics across 3+ prompt paraphrases, shuffled document order, and repeated runs or seeds.
- Avoid accuracy and F1 as headline numbers, because both depend on the class mix and hide false negatives.

### Gaps
- No AP-specific published learning-to-defer benchmark found.

## Q4. Is the "basic agent escalates ~60%" guess plausible? How to measure it

### Takeaway
It is **unsourced and not comparable** to industry exception rates (18.4% average). An escalation rate is entirely a function of the test set's class mix and noise level, so measure it rather than assume it.

### Cited Findings
- Exception rates vary several-fold depending on the counting definition alone — [Fragment](https://fragment.ai/wiki/invoice-exception-rate-benchmarks); industry average 18.4% — [Ardent](https://payablesplace.ardentpartners.com/2026/01/state-of-epayables-part-nine-ap-benchmarks-and-best-in-class-performance/)
- LLM output varies with the prompt format, so a single-prompt baseline is unreliable — [Sclar et al.](https://arxiv.org/abs/2310.11324)

### Inferences
- Protocol:
  - Fix and publish the label mix. For example: 40% perfectly clean, 40% clean-but-messy (OCR noise, unit or format differences, date formats, line splits or merges, rounding), 15% real discrepancies (price, quantity, missing receipt, missing PO, duplicate), and 5% receipt-timing cases.
  - Run the frontier baseline with 3+ prompt variants and shuffled document order.
  - Report the escalation rate **per stratum**, not one blended number.
  - Also report the blended rate re-weighted to an alternative mix, for example ~18% real exceptions as in Ardent.
- A 60% blended rate is plausible only if messy cases dominate the set. Per-stratum reporting avoids that ambiguity.

### Gaps
- No public measurement of frontier LLM escalation rates on 3-way match.

## Q5 (optional). Daily PO assistant prioritization

### Takeaway
A simple, defensible ranking is **expected value at risk = P(real issue) × $ amount**, optionally with urgency weighting (for example, days to the due date or the discount deadline). Evaluate it with precision@k or nDCG@k against labeled "needs action" POs.

### Cited Findings
- Exceptions cause missed early-payment discounts — [Ardent 2024](https://payablesplace.ardentpartners.com/2025/01/best-of-2024-ap-performance-advantages-of-best-in-class/)

### Inferences
- With ~100 POs a day, use precision@10/@20, plus "$ captured@k" (the sum of $ at risk among the top k ÷ the total $ at risk). Compare against baselines that sort by amount only and by due date only. Keep this as a stretch goal.

### Gaps
- I found no published industry standard for an AP worklist ranking formula; the formula above is an inference.
