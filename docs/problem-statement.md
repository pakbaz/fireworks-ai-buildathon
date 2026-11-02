# Problem statement

Invoice reconciliation for the Fireworks: Deploy hackathon, November 2, 2026. The build plan is in [plan.md](plan.md), the system flow in [system-flow.md](system-flow.md), and the source notes in [notes/](notes/).

## 1. Why this matters

Three-way matching is the control that stops a company paying for goods it did not order or did not receive. Before an invoice is paid, it is reconciled against the purchase order (PO) and the goods receipt (GR) on price, quantity, and reference. [Microsoft Dynamics 365](https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/accounts-payable-invoice-matching) and [Oracle](https://docs.oracle.com/cd/A60725_05/html/comnls/us/ap/point04.htm) define it the same way: invoice price against PO price, invoice quantity against received quantity, inside configured tolerances.

The control is expensive because it fails open to humans:

| Figure | Source |
|---|---|
| 18.4% of invoices raise an exception that a person must handle | [Ardent Partners, State of ePayables 2025](https://payablesplace.ardentpartners.com/2026/01/state-of-epayables-part-nine-ap-benchmarks-and-best-in-class-performance/) |
| $9.84 average fully loaded cost per invoice, 8.2 days average cycle time | Ardent Partners 2025 |
| Best-in-class teams run at 9%, roughly half the average | [Ardent Partners 2024](https://payablesplace.ardentpartners.com/2025/01/best-of-2024-ap-performance-advantages-of-best-in-class/) |
| About 49% touchless rate even for top performers | Hackett Group 2025, via [Corpay](https://www.corpay.com/en-CHI/resources/blog/ap-team-productivity-benchmarks) |
| In one open reconciliation project, rules were correct on 99.3% of clean documents, yet 48.4% of documents still went to human review because line-item extraction scored F1 0.37 | [docmatch](https://github.com/franklinmdev/docmatch) |

The last row is the mechanism. Matching logic is a solved problem on clean structured data. What breaks is upstream: the data is not clean. Invoices arrive as scans and PDFs in hundreds of layouts. Goods receipts are often paper, signed by a carrier, annotated by hand. When extraction cannot read a decision-critical field, or reads it with low confidence, every commercial system does the same thing: it escalates. [Stampli's documented design](https://www.stampli.com/resources/how-ai-invoice-processing-works/), for example, routes any field below a confidence threshold to review regardless of whether the documents agree.

The result is a review queue dominated by false positives. Public benchmarks do not measure this directly, but the arithmetic is unavoidable: if 18% of invoices are exceptions and the true discrepancy rate on PO-backed invoices is a few percent, most reviewed invoices were fine. Each one costs an analyst's time and delays payment, which forfeits early-payment discounts. No vendor publishes a false-escalation rate with a denominator.

## 2. The problem, stated precisely

Given a case packet consisting of a purchase order, an invoice, a goods receipt that may be absent, an optional shipping notice, the list of invoice numbers already paid against that PO, company reference knowledge, and an as-of date, produce one decision:

| Decision | Meaning |
|---|---|
| **CLEAR** | The documents agree on item, quantity, and price within policy tolerance. Pay without human review. |
| **ESCALATE** | The documents disagree on a clearly read field, or a decision-critical field cannot be read. A human must act. A reason code is attached. |
| **WAIT** | The receipt is absent but a shipping notice places the goods in transit. Re-check later. |

The two error types have asymmetric costs. A false CLEAR on a real discrepancy leaks money and breaks an audit control. A false ESCALATE on an agreeing invoice costs one manual review. This is a selective classification problem, in the sense of [Geifman and El-Yaniv](https://arxiv.org/abs/1705.08500), and a learning-to-defer problem, in the sense of [Mozannar and Sontag](https://proceedings.mlr.press/v119/mozannar20b.html): the system must decide not only what the answer is but whether it is safe to answer at all.

That shape dictates the metric. The objective is to minimize false escalations on agreeing cases subject to a hard constraint of 100% recall on real discrepancies, with uncertainty intervals on both. Accuracy and F1 are the wrong headline numbers because they trade the two error types against each other at the class mix of the test set.

## 3. Why it is not already solved

- **Rules cannot read.** Deterministic matching requires structured input. On a handwritten quantity or a reordered layout, a parser fails and the only safe rule is to escalate.
- **General OCR is not solved on messy documents.** On [OCRBench v2](https://arxiv.org/abs/2501.00321), most models score below 50 out of 100, weakest on handwriting, fine detail, and tables. [CC-OCR](https://arxiv.org/abs/2412.02210) documents hallucinated repeated line items as a common failure, and a hallucinated line looks exactly like a quantity discrepancy.
- **A frontier model alone is unsafe and expensive.** It will produce an answer for an unreadable field rather than abstain. Its output shifts materially with prompt formatting ([Sclar et al.](https://arxiv.org/abs/2310.11324)). Its self-reported confidence is not calibrated. At 100 invoices per analyst per day across an enterprise, per-token cost is a real line item.
- **The useful knowledge is local.** Whether a handwritten number on this supplier's receipt is authoritative, whether "1 CS" means 12 units for this SKU, whether this supplier ships from Reno though the PO says Dallas, is tribal knowledge held by analysts and absent from every model's training data.

## 4. What we test

Whether a harness built on open models on Fireworks, with deterministic checks as the authority, per-field abstention, targeted re-reading of only the fields that fail a check, and typed company knowledge looked up by ID, can lower the false escalation rate on agreeing invoices below that of a frontier model given identical inputs, while both catch every real discrepancy, at lower cost per invoice.

The benchmark, generator, scorer, and raw outputs are published so the claim can be checked. The exact case mix, metric definitions, baseline arms, and timeline are in [plan.md](plan.md).

## 5. In one sentence

We teach open models to tell the difference between an invoice that is wrong and an invoice that is merely hard to read, so people only look at the ones that are actually wrong.
