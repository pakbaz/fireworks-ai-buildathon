# Existing solutions for AI-assisted three-way (PO / GR / invoice) matching & exception handling (as of 2026-11-02)

## Commercial products: what they claim for matching/exceptions

### Takeaway
Every major suite advertises extraction + tolerance-based 2/3-way matching that "involves reviewers only when necessary", but none publishes a reproducible, per-discrepancy-type benchmark or a false-escalation rate on messy (scanned/handwritten) documents. Accuracy figures (e.g. "99%") are marketing claims, mostly about extraction, not matching decisions.

### Cited Findings
- **Coupa (+ Rossum T-LLM)** (official page, fetched): ingests "any document, in any format… zero templates"; line-level data "arrives 100% ERP-ready"; "two-way and three-way matching while setting tolerance levels to involve reviewers only when necessary"; auto-match to POs "with configurable tolerances and auto-approval". "100% ERP-ready" = UNVERIFIED marketing claim; no matching accuracy/false-escalation metric published. — [Coupa Invoicing](https://www.coupa.com/products/ap-automation/invoicing/)
- **Oracle Fusion IDR** (official docs, fetched): extracts invoices from email, ML "learns from corrections"; invoices land as "Incomplete" (needs attention) or "Not Validated"; human corrects in Interactive Viewer. The IDR page describes extraction/correction, not AI matching — matching/holds are standard Payables tolerance logic. No accuracy number. — [Oracle IDR docs 25D](https://docs.oracle.com/en/cloud/saas/financials/25d/fappp/intelligent-document-recognition.html)
- **Microsoft Dynamics 365 Finance**: Invoice capture creates vendor invoices from invoice images via OCR (doc updated 2026-07/09); three-way matching is configured as policies (header/line). No published AI matching accuracy found. — [Invoice capture overview](https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/invoice-capture-overview); [Three-way matching policies](https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/three-way-matching-policies)
- **SAP**: SAP Community post on S/4HANA Cloud Public Edition 2608 describes a Joule-based "Receivables & Payables Clearing Agent" that generates clearing proposals with explanations for accountant approval (clearing, not PO/GR/invoice 3-way match). SAP News (Oct 2025) mentions Joule capabilities in next-gen Ariba incl. invoice creation and planned agents for disputes. A "98%+ accuracy" figure for Joule appeared only on a third-party comparison blog → UNVERIFIED, not from SAP. — [SAP Community 2608](https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-sap/what-s-new-in-sap-business-ai-for-sap-s-4hana-cloud-public-edition-2608/ba-p/14434537); [SAP News Oct 2025](https://news.sap.com/2025/10/sap-connect-spend-management-procurement/); third-party: [business-software.com](https://www.business-software.com/blog/vendor-comparison-sap-vs-microsoft-vs-oracle-ai-erp-solutions/)
- **Hypatos** (vendor knowledge-base article, a competitor comparison written by Hypatos itself): claims agents read live PO/GR from SAP/Oracle, handle tolerances, partial/blanket orders; "high matching accuracy in production" — no number; self-interested source. — [Hypatos KB](https://www.hypatos.ai/knowledge-base/three-way-po-matching-ai-vendors)
- **Stampli (Billy)**: "97–100%" PO-matching accuracy reported via aggregator blog citing stampli.com/billy; not confirmed by direct fetch → UNVERIFIED. — [Stampli Billy](https://www.stampli.com/billy/); [kenfromfinance (3rd party)](https://www.kenfromfinance.com/blog/stampli-vs-vic-ai)
- **Vic.ai**: "99% invoice accuracy" and autonomous 2/3/4-way PO matching, per search summary of vendor page (not fetched) → UNVERIFIED marketing. — [Vic.ai PO matching](https://www.vic.ai/accounts-payable/po-matching)
- **Ramp**: Ramp's own blog lists AI AP agents; third-party reviews say Ramp offers 3-way match, Brex primarily 2-way PO matching via policy engine. Not verified on official product pages. — [Ramp blog](https://ramp.com/blog/agentic-ai/best-ai-agents-for-ap-automation); [TechRepublic Ramp vs Brex](https://www.techrepublic.com/article/ramp-vs-brex/)
- **Rossum**: "99%+ extraction accuracy" appears only in aggregator summaries → UNVERIFIED; it's an extraction (not matching) claim.

### Inferences
- The industry pattern is: AI extraction → deterministic tolerance rules → human queue. "Exception" ≈ any tolerance breach OR low-confidence extraction, so messy-but-agreeing documents plausibly inflate review queues (inference; no vendor publishes this rate).
- Vendor metrics conflate extraction accuracy with decision quality; none report false-escalation (clean docs sent to humans) vs missed-discrepancy separately.

### Gaps
- Did not fetch Basware, Medius, AppZen, Tipalti, Brex, Stampli, Vic.ai, Rossum official pages directly (time budget); their claims above are from search summaries and should be treated as unverified.
- Azure Document Intelligence prebuilt-invoice model: not researched in this pass (no matching capability; extraction only, per docmatch's use of it as a backend).
- No vendor publishes cost/token per document or open-model options.

## Open-source projects / GitHub repos

### Takeaway
A few serious OSS projects exist; the strongest (docmatch) already has a reproducible benchmark with injected discrepancies and a clean-case false-positive rate — but uses closed models (Gemini, GPT, Azure DI), and its end-to-end review rate is still high (0.484).

### Cited Findings
- **docmatch** (franklinmdev): VLM extraction → deterministic validation gate → entity resolution → rules-based 3-way match → human review; "Models structure text; deterministic code does the arithmetic and makes the decisions." Uses DocILE dataset; synthetic POs/GRs with injected discrepancies (price variance, short/over-ship, missing/extra line, unit variant, tax mismatch); clean cases have in-tolerance rounding drift that must not fire. Results: matching per-type precision/recall 0.977–1.000, clean-case FPR 0.007; extraction field F1 0.615, line-item F1 0.374 (Gemini, $0.00203/doc); end-to-end p95 10.03 s, $0.00236/doc, **review rate 0.484**; CI regression gate. Backends: gemini-3.1-flash-lite, Azure DI prebuilt-invoice, gpt-5.6-luna. — [docmatch](https://github.com/franklinmdev/docmatch)
- **phase1-three-way-match** (bwcaputo): Odoo-integrated agent; approve / route for review / block; "The model never computes a dollar amount or decides the final action". Scorecard on 30–35 scenarios: Sonnet 4.6 baseline 96.7%; tight tolerance 90%; no duplicate tool 77.1% and catches 0% duplicates; 10/10 prompt-injection payloads ignored. Small n; synthetic ERP data, not messy scans. — [phase1-three-way-match](https://github.com/bwcaputo/phase1-three-way-match)
- Others (not inspected in depth): Three-Way-Match-Engine (Gemini, line-level) — [repo](https://github.com/akshaychavan23031998/Three-Way-Match-Engine); InvoiceFlow (Azure Form Recognizer + LLM) — [repo](https://github.com/StephaneWamba/InvoiceFlow); 3-way-match-financetool (pandas, no LLM) — [repo](https://github.com/DanCallen02/3-way-match-financetool); ReconMitra hackathon (GST reconciliation) — [Devpost](https://devpost.com/software/reconmitra).

### Inferences
- docmatch's 48% review rate despite near-perfect matching rules suggests extraction noise/gating is the dominant driver of human escalation — exactly the problem the hackathon targets.
- Shared design consensus: LLM for reading/normalizing + explanation, deterministic code for arithmetic and the final decision.

### Gaps
- No OSS project found that benchmarks open-weight models (e.g., Llama/Qwen/Gemma) vs frontier models specifically on 3-way match decisions with handwriting/scan degradation.

## Research papers (2024–2026)

### Takeaway
Academic work covers invoice extraction benchmarking, not end-to-end three-way-match decisions; dedicated 3-way-match LLM papers are scarce and low-venue.

### Cited Findings
- arXiv 2509.04469 (Aug 2025): benchmarks 8 multimodal LLMs (GPT-5, Gemini 2.5, open Gemma 3) zero-shot on three open invoice datasets; native image processing generally beats markdown-parsing-first; code available. Extraction only. — [arXiv 2509.04469](https://arxiv.org/abs/2509.04469)
- IJCRT (2026) "Automation of three-way matching for bill payment using LLMs": OCR + LLM pipeline for PO/GR/invoice with discrepancy flags; low-tier venue, claims not independently checked. — [IJCRT2602673](https://ijcrt.org/papers/IJCRT2602673.pdf)
- DocILE dataset used by docmatch as the labeled invoice source. — [docmatch](https://github.com/franklinmdev/docmatch)

### Inferences
- Evidence that an open model (Gemma 3) is in the comparison set supports a Fireworks open-model vs frontier framing, but no paper measures escalation-rate trade-offs.

### Gaps
- No peer-reviewed benchmark found for false-escalation rate in 3-way matching; limited time (~15 calls) means more papers may exist.

## Gap analysis & positioning

### Takeaway
Underserved: (1) a public, reproducible benchmark that separately reports false escalations on messy-but-agreeing documents and recall on real discrepancies; (2) open-model cost/latency vs frontier; (3) evidence-linked decisions (each field/verdict tied to a document region/quote).

### Cited Findings
- Vendors advertise "reviewers only when necessary" with no published false-escalation metric. — [Coupa](https://www.coupa.com/products/ap-automation/invoicing/)
- Best OSS reference still routes 48.4% of docs to review end-to-end with closed models; matching FPR on clean structured data only 0.007 — so the noise is upstream. — [docmatch](https://github.com/franklinmdev/docmatch)
- Oracle IDR flags "Incomplete" extractions for human correction — messy-document extraction gaps become human work. — [Oracle IDR](https://docs.oracle.com/en/cloud/saas/financials/25d/fappp/intelligent-document-recognition.html)

### Inferences
- Credible 3-hour demo: synthetic held-out set with paired clean/messy renderings (scan noise, handwriting fonts, layout shuffles) of identical PO/GR/invoice triples + injected discrepancies; metrics = false-escalation rate on agreeing triples, discrepancy recall (must ≈100%), $/doc and latency; open model on Fireworks vs frontier baseline; deterministic matcher + LLM normalization with cited evidence spans; "abstain/escalate" only when evidence conflicts.
- Positioning: "Commercial AP suites claim touchless matching but publish no false-escalation numbers; we release an open, reproducible benchmark showing open models on Fireworks cut false human escalations on messy-but-correct documents while keeping 100% recall on real discrepancies, at a fraction of frontier cost, with every decision linked to evidence."

### Gaps
- Real customer escalation rates are not public, so the improvement claim must be framed relative to the team's own baseline on synthetic data.
