# Company-specific "tribal knowledge" for an invoice-reconciliation LLM harness

Scope: per-supplier notes vs RAG vs knowledge graph; commercial AP precedent; ERP location/site semantics; governance/safety; afternoon MVP + ablation. Research bounded to ~15 tool calls on 2026-11-02.

## Q1. RAG vs GraphRAG vs structured memory — when does a graph win, and what does it cost?

### Takeaway
Primary papers show graphs help mainly for *global/sensemaking* questions over large unstructured corpora (~1M tokens), at the cost of LLM-driven indexing. Invoice reconciliation is the opposite case: entities (supplier, PO, receipt, site, item) and their relations already exist as structured ERP keys, so "the graph" is just SQL joins; LLM-built graphs add cost and extraction error without a clear benefit for a hackathon.

### Cited Findings
- GraphRAG paper: plain RAG "fails on global questions directed at an entire text corpus" (e.g., "main themes"); GraphRAG uses an LLM to build an entity knowledge graph, then pregenerates community summaries; improvements were shown "for a class of global sensemaking questions over datasets in the 1 million token range" on comprehensiveness and diversity — [arXiv 2404.16130](https://arxiv.org/abs/2404.16130)
- Reported win rates of 72–83% (comprehensiveness) / 62–82% (diversity) vs vector RAG, judged by an LLM — secondary summary [Emergent Mind](https://www.emergentmind.com/papers/2404.16130); a 2026 blog claims these wins shrink after correcting LLM-judge bias — [beancount.io](https://beancount.io/bean-labs/research-logs/2026/06/04/graphrag-local-to-global-query-focused-summarization) (secondary, not verified against paper).
- LightRAG: graph structures + vectors with dual-level retrieval and "an incremental update algorithm" for rapidly changing data; claims improved accuracy and efficiency vs existing approaches — [arXiv 2410.05779](https://arxiv.org/abs/2410.05779)
- MemGPT: "virtual context management" with memory tiers moved in/out of the context window, evaluated on large-document analysis and multi-session chat where agents "remember, reflect, and evolve" — [arXiv 2310.08560](https://arxiv.org/abs/2310.08560)

### Inferences
- The reconciliation questions are *local and keyed* ("which receipt matches this invoice line?", "what did reviewers decide last time for supplier X?"), which is the case where structured lookup beats both vector RAG and GraphRAG. The teammate's graph (reviewer→supplier→PO→invoice→receipt→warehouse→item) is better implemented as typed relational joins over ERP IDs than as an LLM-extracted graph.
- RAG over free-text reviewer notes is useful only once notes are numerous/unstructured; for an afternoon, a per-supplier JSON profile loaded by supplier_id is "memory" in the MemGPT sense (a small, pinned core-memory block) without retrieval error.
- GraphRAG/LightRAG cost = LLM extraction calls over every document plus re-indexing; not justified for a same-day test.

### Gaps
- No primary paper found evaluating GraphRAG vs RAG on transactional/accounting matching tasks.
- Did not verify claims (seen in search snippets) about GraphRAG version 3.3.0 incremental update or specific LightRAG token-cost figures; treat as unverified.
- "Human feedback as memory" papers not fetched within budget.

## Q2. Commercial AP automation: vendor-specific learning / reviewer feedback

### Takeaway
Verifiable official text (Stampli) describes learning *suggestions* (coding, approver routing) from the customer's own past decisions per vendor, gated by confidence thresholds with humans confirming. Deterministic tolerances (D365, Oracle) remain configured rules, not learned. No official doc found claiming learned auto-approval of price/quantity discrepancies.

### Cited Findings
- Stampli: coding is predicted by finding "how similar past invoices from the same vendor were coded"; "Predictions improve as the system accumulates your corrections"; "vendor is the strongest coding signal"; "It's pattern-matching on your own decisions, not a universal rule" — [Stampli](https://www.stampli.com/resources/how-ai-invoice-processing-works/)
- Stampli: each prediction has a confidence score and threshold; low-confidence values are flagged for human review; routing is learned from history of who approved similar invoices; "Humans confirm and can override"; it "can't predict a routing rule you've never demonstrated" — [Stampli](https://www.stampli.com/resources/how-ai-invoice-processing-works/)
- Stampli describes validation (duplicate checks, PO matching, tolerance tests) as a separate stage from learned coding/routing, and "structured rules to validate the result against your ERP" — [Stampli](https://www.stampli.com/resources/how-ai-invoice-processing-works/)
- D365 Finance: matching discrepancies are compared with configured tolerances (e.g., 5% net unit price tolerance per item category); exceeding it shows a variance and the invoice can be saved until resolved; supports totals, two-way, three-way, charges matching — [Microsoft Learn](https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/accounts-payable-invoice-matching)
- Oracle Purchasing: receiving tolerances (over-receipt %, days early/late) each have an action None/Reject/Warning, overridable "for specific suppliers, items, and purchase orders" — [Oracle docs](https://docs.oracle.com/cd/A60725_05/html/comnls/us/po/rcvstdro.htm)

### Inferences
- Industry precedent: per-supplier knowledge = (a) explicit, configured per-supplier tolerance overrides (Oracle) and (b) learned *suggestions* with confidence + human confirm (Stampli). Neither is "LLM note silently approves". This supports "notes as evidence, tolerances as governed config".

### Gaps
- Coupa, Basware, AppZen, Tipalti, SAP: only marketing pages/aggregator summaries surfaced; I did not verify specific official claims about vendor-specific learning or learned tolerances. SAP Help "Invoice Processing" page link surfaced ([SAP Help](https://help.sap.com/docs/sap_s4hana_cloud/0e602d466b99490187fcbb30d1dc897c/17b30887c1454e71a1089b88d850fd25.html?locale=en-us)) but was not fetched; SAP Cash Application (AR, not AP) is the clearest SAP "learns from accountant corrections" product ([SAP](https://www.sap.com/products/financial-management/cash-application.html)) — not verified in-session.

## Q3. ERP handling of multi-ship-to POs, supplier sites, ship-to vs receiving location, cross-site receipts

### Takeaway
ERPs model location at the PO *shipment/line* level and decide policy explicitly: Oracle can None/Warn/Reject receipts whose receiving location differs from ship-to; D365 three-way matching matches invoice quantities to the product receipts *selected for the invoice*. Deterministic joins can shortlist candidates; ambiguity remains when multiple open POs/receipts share supplier+item+date windows.

### Cited Findings
- Oracle receiving controls include "Enforce Ship-To Location" with None (receiving location may differ), Reject (not permitted), Warning (warn but permit); controls set at more specific levels (order) override organization-level — [Oracle Applications Help via search](https://docs.oracle.com/cd/A60725_05/html/comnls/us/po/rcvov03.htm) (option text quoted from search summary; page not directly fetched)
- Oracle also supports "Allow Unordered Receipts" — "You can later match the unordered receipts to a purchase order", and substitute receipts — [Oracle docs](https://docs.oracle.com/cd/A60725_05/html/comnls/us/po/rcvstdro.htm)
- D365 three-way matching: "match the quantity information on the invoice to the quantity information on the product receipts that are selected for the invoice" — [Microsoft Learn](https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/accounts-payable-invoice-matching)
- D365 product receipt and inbound docs: [Product receipt against POs](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/product-receipt-against-purchase-orders), [Inbound load handling](https://learn.microsoft.com/en-us/dynamics365/supply-chain/warehousing/inbound-load-handling) (surfaced, not fetched)
- Ship-to vs deliver-to: ship-to is where the supplier delivers; deliver-to is the internal final destination — practitioner sources [ShipERP blog](https://blog.shiperp.com/ship-to-vs-deliver-to), [oracleapplications.com](http://www.oracleapplications.com/2015/02/ship-to-location-vs-deliver-to-location.html) (secondary)

### Inferences
- Deterministic candidate search for "wrong warehouse/wrong PO": join receipts on supplier_id (incl. all supplier sites of same parent) + item/SKU + qty within tolerance + receipt date in [invoice_date − N, invoice_date + M] + open (un-invoiced) quantity > 0; then rank by exact PO ref, ship-to==receiving site, price match. Also check inter-site transfer records from the PO ship-to site to the actual site.
- Remains ambiguous: multiple open POs at different prices for same supplier/item (multi-site pricing); split/consolidated shipments; receipts at a site with no transfer record; supplier invoicing from a different supplier site than the PO's. These should escalate with the ranked candidate list rather than auto-resolve.
- A rerouted receipt is a *location* discrepancy, not necessarily a price/qty one; policy (None/Warn/Reject analogue) should be explicit config per company, not inferred from notes.

### Gaps
- SAP plant/storage-location and GR-based invoice verification docs not fetched; Oracle Fusion supplier-site docs not fetched.

## Q4. Safety/governance: keep notes from becoming silent auto-approve rules

### Takeaway
OWASP treats any external/document content as potential prompt injection and recommends least privilege, deterministic output validation, segregating untrusted content, and human approval for high-risk actions. Apply: notes are cited *evidence* that can only lower friction within hard deterministic limits; anything that would change a tolerance becomes a reviewed, versioned config change.

### Cited Findings
- Indirect prompt injection occurs when an LLM accepts input from external sources such as files; injections need not be human-visible; RAG and fine-tuning "do not fully mitigate" prompt injection — [OWASP LLM01](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
- Mitigations: constrain behavior; define/validate output formats "using deterministic code"; input/output filtering; least privilege with functions handled in code; "Require human approval for high-risk actions"; "Segregate and identify external content"; adversarial testing — [OWASP LLM01](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
- OWASP 2025 list also includes data and model poisoning (LLM04), relevant to memory/knowledge stores — secondary summaries [Kodem](https://www.kodemsecurity.com/resources/owasp-top-10-for-llm-applications), [Invicti](https://www.invicti.com/blog/web-security/owasp-top-10-risks-llm-security-2025) (primary LLM04 page not fetched)
- Stampli design: low-confidence outputs surfaced to humans; humans confirm/override — [Stampli](https://www.stampli.com/resources/how-ai-invoice-processing-works/)

### Inferences (proposed governance pattern)
- Note schema: {supplier_id, scope (site/item), claim, type: observation|tolerance_proposal, author, approved_by, created, expires, source_invoice_ids, version}. Only reviewer-authored, approved notes load; nothing extracted from invoice/PDF text is ever written to notes automatically.
- Notes can (a) explain a known benign pattern and (b) suggest a candidate join (e.g., "ships to DC-2 for PO site DC-1"), but the final pass/fail is computed by deterministic code with hard caps (amount, % variance, qty) that notes cannot raise. Tolerance changes = config PR with approver.
- Wrap document text as untrusted data in the prompt; require structured output citing note IDs and receipt IDs; code verifies cited IDs exist and numbers match.
- Expiry + "last confirmed" date; auto-escalate if a note is used > N times without re-confirmation; log every decision that relied on a note for audit/sampling.

### Gaps
- No primary standard found specifically on governing LLM "memory" in finance; SOX/internal-control guidance not researched.

## Q5. Simplest afternoon MVP and ablation

### Takeaway
Build: (1) deterministic candidate search over receipts/POs; (2) a hand-written supplier_profiles.json (5–10 suppliers) injected by supplier_id; (3) LLM decides pass/escalate with cited evidence under hard caps. Measure as a 2×2 ablation on a labeled synthetic set.

### Cited Findings
- Deterministic tolerances and three-way matching semantics to replicate: [Microsoft Learn](https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/accounts-payable-invoice-matching); per-supplier override precedent: [Oracle docs](https://docs.oracle.com/cd/A60725_05/html/comnls/us/po/rcvstdro.htm)
- Confidence-threshold trade-off (too low → confident garbage, too high → everything to humans) — [Stampli](https://www.stampli.com/resources/how-ai-invoice-processing-works/)

### Inferences (recommendation)
- Data: ~40–60 synthetic cases, labeled true_discrepancy / benign_exception, covering: supplier no-qty-cap over-ship, handwritten overwrite, multi-site same supplier with different PO prices, rerouted receipt (with/without transfer record), wrong-PO reference, plus 3–5 adversarial cases (invoice text "approved per supplier note", a stale/expired note, a note that would mask a real price error).
- Arms: A = rules only; B = LLM, no notes, no candidate search; C = LLM + candidate search; D = LLM + candidate search + supplier notes. Optional E = D with notes via vector RAG instead of direct lookup (expect no gain at this scale).
- Metrics: escalation rate on benign cases (want ↓), recall on true discrepancies (must stay ~100%; any miss is a blocker), false-auto-approve count on adversarial cases (must be 0), correct-candidate@1 for reroute/wrong-PO cases, citation validity rate.
- Skip GraphRAG/Neo4j today; express the "graph" as SQL/pandas joins and show the traversal path in the explanation. Revisit graph/RAG only when notes exceed what fits in a per-supplier block.

### Gaps
- No public benchmark dataset for 3-way match with location rerouting found within budget.
