# Ideas review: research and our take

This document reviews the ideas from brainstorm sessions 2 and 3 in [IDEA.md](../IDEA.md). Research was done on November 2, 2026. Detailed notes with all sources are in [docs/notes/](notes/).

Nothing here has been built or measured yet. All numbers below are from public sources, not from our system.

## TL;DR

1. **The session 3 scope is right.** Target "document-only" escalations: the PO, invoice, and goods receipt (GR) agree, but scans, handwriting, or layout cause a false escalation. Real discrepancies always go to a human.
2. **Reading messy documents is not solved.** Clean pages are close to solved. Handwriting, rotated scans, and tables are not. This supports our hypothesis.
3. **Split the evaluation into two tracks.** This settles the "is it reading or reasoning?" debate with data instead of opinion.
4. **Skip the knowledge graph and RAG for today.** A small JSON profile per supplier plus a fixed receipt search tests the same idea in an hour.
5. **Primary metric:** share of clean-but-messy cases escalated, counted only while recall on real discrepancies stays at 100%.
6. **Fine-tuning is a stretch goal.** A fine-tuned Fireworks model needs a dedicated deployment.
7. **Do not cite "60% escalation."** No source supports it. The best public benchmark is an 18.4% average exception rate (Ardent Partners, 2025, self-reported).

## 1. Problem framing

### What the research says

- No credible public source breaks exceptions down into "data capture problems" versus "real price or quantity mismatches." Several vendor pages quote an "IOFM" breakdown, but we could not find the primary source.
- Ardent Partners' *State of ePayables 2025* reports an 18.4% average invoice exception rate, $9.84 average cost per invoice, and 8.2 days average processing time. Best-in-class teams report 47% fewer exceptions. The data is self-reported by AP leaders ([Ardent Partners](https://payablesplace.ardentpartners.com/2026/01/state-of-epayables-part-nine-ap-benchmarks-and-best-in-class-performance/)).
- Exception rates depend heavily on how you count (per line or per invoice, PO invoices only or all, auto-cleared holds included or not).

### Our take

- The share of escalations that are document-only is unknown. We should say so openly. It is the **hypothesis** our benchmark tests, not a known fact.
- The session 3 split is clean and defensible:
  - **Real discrepancy** (goods received differ from invoice): always escalate. Out of scope for automation.
  - **Document-only escalation** (documents agree, noise causes escalation): the target.
  - **Goods in transit** (invoice arrives before the GR): add as a small labeled class. The correct answer is "wait," not "escalate" and not "approve." It is cheap to include and shows we thought about timing.
- **Agreed:** leave the supplier-email agent out. It adds risk and no benchmark value today.

## 2. Reading or reasoning? Measure both

### What the research says

| Benchmark | What it shows |
|---|---|
| [OmniDocBench](https://github.com/opendatalab/OmniDocBench) (mostly clean pages) | Small open OCR models (around 1B parameters) score highest, ahead of large frontier models |
| [OCRBench v2](https://arxiv.org/abs/2501.00321) | Most models score below 50/100. Weak on handwriting, fine detail, layout, complex tables |
| [CC-OCR](https://arxiv.org/abs/2412.02210) | Rotated text and repeated (hallucinated) lines are common failure modes |

A hallucinated repeated line item is dangerous for us. It looks like a real quantity discrepancy.

### Our take

Both teammates are partly right. Clean reading is close to solved. Messy reading is not. Instead of debating, **measure each part separately**:

| Track | Input | What it isolates |
|---|---|---|
| A. Reasoning track | Gold structured JSON for PO, invoice, GR | Pure decision quality, no reading errors |
| B. System track | Rendered images (clean and messy) of the same cases | Reading + decision, end to end |

The gap between track A and track B for the same model is the error caused by reading. This becomes a strong slide in the demo: "X% of false escalations came from reading, Y% from reasoning."

### Design recommendations

1. Straighten rotated pages first.
2. Extract each field as `{value, status: ok | unreadable | absent}`. The model must never guess a value it cannot read.
3. Run cheap code checks across documents:
   - line items sum to subtotal
   - subtotal plus tax equals total
   - quantity times unit price equals line amount
   - PO number matches across all three documents
   - remove repeated line rows
4. Re-read **only** fields that fail a check or are marked handwritten. Ask three times and take the majority. This spends tokens only where they matter, which is the token-efficiency story.
5. If every disagreement traces to an `unreadable` field, label the case "document quality." If a disagreement exists on fields read clearly, it is a real discrepancy.

## 3. Company knowledge: supplier profiles, not a graph

### What the research says

- In the [GraphRAG paper](https://arxiv.org/abs/2404.16130), the graph clearly beat plain RAG mainly on broad "global" questions over large text collections. Building it costs many LLM calls.
- Invoice-to-receipt matching is a narrow lookup on IDs that the ERP already stores. A "graph traversal" here is mostly database joins.
- [Stampli](https://www.stampli.com/resources/how-ai-invoice-processing-works/) describes learning from past decisions per supplier for coding and approver suggestions, with human confirmation. Matching against tolerances stays a separate rules step. We found no official doc where learned behavior auto-approves price or quantity mismatches.
- Oracle allows receiving controls (over-receipt, date windows, ship-to location) at the supplier, item, or PO level, with None, Warning, or Reject actions ([Oracle receiving controls](https://docs.oracle.com/cd/A60725_05/html/comnls/us/po/rcvstdro.htm)).
- [OWASP LLM01](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) says RAG does not prevent prompt injection.

### Our take

The graph idea is good long term. It is too much for this afternoon, and it does not change the benchmark result. Build the smallest thing that tests the same claim:

**Supplier profile (JSON), example:**

```json
{
  "supplier_id": "SUP-ACME",
  "sites": ["ACME-DALLAS", "ACME-RENO"],
  "notes": [
    {
      "text": "Writes received quantity by hand on top of the packing slip.",
      "effect": "reading_hint",
      "author": "reviewer-2",
      "approved_by": "ap-lead",
      "version": 1,
      "expires": "2027-06-30"
    }
  ]
}
```

**Rules for notes:**

- Notes are **hints for reading and candidate search**. They never widen tolerances or approve anything.
- Each note has an author, approver, version, and expiry date.
- Nothing extracted from invoice text is ever written into a note automatically.

**Wrong warehouse / wrong PO search** (sessions 2 and 3): a fixed query, not a model guess.

1. Same supplier (any of its sites).
2. Same item.
3. Quantity within tolerance.
4. Receipt date within a window around the invoice date.
5. Open quantity left to invoice on that PO line.
6. Rank results. Also look for a transfer record from the PO's warehouse to the receiving warehouse.

If exactly one candidate fits and the price matches, propose it. If several open POs have different prices, or no transfer record exists, escalate **with the ranked candidates attached**. That still saves the reviewer time even when it escalates.

**Measure it as an ablation:** run with and without supplier profiles on the same cases. Include adversarial cases: a stale (expired) note, and invoice text that says "already approved by AP." Both must still escalate.

## 4. Metrics

### What the research says

- Accuracy and F1 shift with the case mix and can hide missed discrepancies.
- Prompt formatting alone can swing LLM accuracy a lot ([Sclar et al.](https://arxiv.org/abs/2310.11324)).
- This task is a form of "learning to defer" and selective classification ([Mozannar and Sontag](https://proceedings.mlr.press/v119/mozannar20b.html); [Geifman and El-Yaniv](https://arxiv.org/abs/1705.08500)).

### Our take

**Primary metric:**

> False escalation rate on clean-but-messy cases, reported only when recall on real discrepancies is 100%.

**Secondary metrics:**

- Recall per discrepancy type.
- Share of all cases cleared automatically.
- Tokens and cost per case (the efficiency story).
- Reading-gap: track B minus track A.
- Spread across 3 prompt wordings and shuffled document order (for the baseline too, to keep it fair).
- Expected cost: false escalation ≈ one manual review (about $9.84 per Ardent); missed discrepancy ≈ dollar amount at risk.

**Case mix (proposed, published with results):**

| Class | Share | Correct answer |
|---|---:|---|
| Clean match | 30% | No escalation |
| Clean but messy (scan, handwriting, layout) | 40% | No escalation |
| Real discrepancy (quantity, price, wrong PO) | 25% | Escalate |
| Goods in transit | 5% | Wait |

**Be honest about sample size.** Zero misses on 100 real-discrepancy cases means the true miss rate is likely at most about 3% (95% confidence). It does not mean zero.

## 5. Models and fine-tuning

### What the research says

- Fireworks lists several vision models: `kimi-k2p5` (used in the vision docs), `qwen3-vl-30b-a3b-instruct`, `qwen3-vl-235b-a22b-instruct`, `qwen3-vl-8b-instruct`, `gemma-4-31b-it`, `llama4-maverick-instruct-basic`, and others ([Fireworks vision guide](https://docs.fireworks.ai/guides/querying-vision-language-models)).
- No page confirms that JSON schema output works together with image input. Catalog pages show mixed "serverless" labels.
- Fireworks supports supervised fine-tuning of vision models, but a fine-tuned model must run on a dedicated deployment ([Fireworks fine-tuning](https://docs.fireworks.ai/fine-tuning/fine-tuning-models)).
- Evidence that a small fine-tuned model beats a large general model on invoice fields is thin.

### Our take

- **First 15 minutes of build:** one live call each to 2 vision models with an image plus a JSON schema. Pick whichever works. Do not plan around a model we have not called.
- **Fine-tuning:** stretch goal only. The tax-form point is valid: knowing which fields matter helps. We can get most of that today through the prompt (list of critical fields per document type) and the targeted re-read in section 2. Fine-tuning can come later and be measured as another ablation.

## 6. Daily PO assistant

### Our take

Good demo framing, not a separate benchmark. Show the output as a morning queue:

- **Cleared:** documents agree (with evidence links).
- **Waiting:** goods in transit.
- **Needs review:** real discrepancy, ranked by probability × dollar amount, with candidate POs or receipts attached.

If time allows, evaluate ranking with the share of total dollars at risk found in the top 10. This is optional.

## 7. Synthetic data plan

1. Generate canonical PO, invoice, and GR records in JSON with a fixed seed.
2. Inject labeled mutations: short receipt, price change, wrong PO, wrong warehouse, goods in transit.
3. Render each record to a simple PDF/image template (2 to 3 layouts per document type).
4. Add noise for the "messy" class: handwritten-style notes on the GR (TRDG, MIT license), stamps, and scan effects with [Augraphy](https://github.com/sparkfish/augraphy) (MIT license).
5. Hold out at least one layout and one supplier entirely for the test split.
6. Hand-check a sample of the test cases.

## 8. Suggested plan for the rest of the day

| Time (PT) | Step |
|---|---|
| Now to 12:30 | Freeze schema and case mix. Generate JSON cases. Live-test 2 vision models. |
| 12:30 to 1:30 | Render images and noise. Run frontier baseline on tracks A and B. Save raw outputs. |
| 1:30 to 2:45 | Build harness: field status, code checks, targeted re-read, supplier profiles, receipt search. |
| 2:45 to 3:15 | Run all arms on the same test cases. Generate results table from saved outputs. |
| 3:15 to 3:30 | README results, demo video (under 120 seconds), make repo public. |
| 3:30 | Start submitting. Must be fully processed by 4:30. |

## Open decisions for the team

1. Do we accept the 4-class case mix above?
2. Which frontier model is the baseline? Is it one we can actually call today?
3. Who owns synthetic data, who owns the harness, who owns evaluation and demo?
4. When do we make the repo public? The rules require it for scoring.
