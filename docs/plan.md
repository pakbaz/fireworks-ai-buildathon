# Invoice Reconciliation: Two-Hour Build Plan

Fireworks: Deploy with Microsoft and NVIDIA. November 2, 2026. Five people, two hours of build, submission open 3:30 PM, closed 4:30 PM Pacific.

This page is the single source of truth for what we build today. It replaces earlier plans where they conflict. Background and sources: [IDEA.md](../IDEA.md), [ideas-review.md](ideas-review.md), [research.md](research.md).

---

## 1. The problem

An accounts-payable analyst gets about 100 invoices a day. For each one, three documents must agree: the purchase order (PO), the supplier's invoice, and the goods receipt (GR) recorded when the shipment arrived. If they agree, the invoice is paid. If they do not, a person investigates.

Today's tools escalate far too often. Industry average is roughly one invoice in five raising an exception (Ardent Partners 2025: 18.4%), and each manual review costs about $9.84. The escalations split into two kinds:

| Kind | What happened | Who should handle it |
|---|---|---|
| **Real discrepancy** | Goods received differ from what the invoice bills: short shipment, price change, wrong PO, wrong warehouse, duplicate invoice. | A human. No model can fix this. Out of scope for automation. |
| **Document-only escalation** | The three documents actually agree, but scans, handwriting, moved fields, odd formats or notes confuse the system. | Should be cleared automatically. **This is our target.** |

**Hypothesis:** a large share of today's escalations are document-only, and a harness built on open models on Fireworks can clear them without missing any real discrepancy, at lower cost than a frontier model.

**User:** the AP analyst. **Value:** fewer invoices on their desk each morning, with no increase in missed problems.

---

## 1a. Existing solutions, and where we differ

What ships today, from vendor documentation read on November 2, 2026. Numbers are vendor-claimed unless noted.

| Product | How it matches | How it escalates | What it leaves to humans |
|---|---|---|---|
| [Microsoft Dynamics 365](https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/accounts-payable-invoice-matching) | Rule-based two- and three-way match on net unit price and received quantity. Pass or Fail per field. | Fixed price and charge tolerances per vendor, item or legal entity. Anything outside tolerance is held until approved. | Every held invoice. No reading of messy documents. |
| [Basware Matching Agent](https://customer.basware.com/en/features/matching-agent-ai-powered-guidance-for-invoice-matching-discrepancies) | Rules do the match. An AI agent explains a discrepancy on request. | Human opens the exception and clicks "Analyse Discrepancy". | Everything. "The Matching Agent provides recommendations only." |
| [Stampli](https://www.stampli.com/resources/how-ai-invoice-processing-works/) | AI extraction with per-field confidence, then tolerance tests against PO and receipt lines. | Low-confidence fields and out-of-tolerance variances are flagged for review. | Any case with a low-confidence field, even if the documents agree. |
| [Vic.ai](https://www.vic.ai/accounts-payable/po-matching) | AI two-, three- and four-way match, works without a PO number. | Tolerance thresholds; mismatched lines flagged with the rule violated. Claims 85% no-touch by month 6. | Flagged lines. The claim does not say what counts as no-touch. |
| [Coupa](https://www.bluecopa.com/blog/3-way-matching-software), [Tipalti](https://chatfin.ai/blog/vic-ai-alternatives-2026/) | Configurable tolerance matching, Rossum-style capture. | Workflow and approval routing. Tipalti is described as triage that suggests fixes. | Exceptions go to an approval queue. |
| Open source ([three-way-match agents](https://github.com/swastikgavhane789/invoice-three-way-match-agents), [invoicematch-ai](https://github.com/herrerogusano/invoicematch-ai)) | Synthetic data, deterministic matching, LLM for explanation. | Rules. | Benchmarks saturate at 100% because the data is clean. |

Two patterns hold across all of them:

1. **Matching is deterministic and the AI explains or triages.** No product we found lets a model clear an invoice that rules could not read. Stampli comes closest, and it escalates on low confidence.
2. **Nobody publishes a benchmark.** Claimed no-touch rates have no stated denominator, case mix or safety constraint. Industry research (Ardent) reports exception rates, not what caused them.

**Where we differ.** We keep the deterministic core and the fixed tolerances. We put the open model in the one place the products do not: reading a messy document well enough that the deterministic checks can run at all, with an explicit `unreadable` status so it never guesses. And we publish the benchmark: case mix, safety gate, counts, per-stratum results, raw outputs. The claim is narrow and testable: fewer document-only escalations at zero missed real discrepancies, versus a frontier model on identical cases.

---

## 2. The task

Input: one case packet = PO text + invoice text + GR text (may be absent) + shipping notice text (may be absent) + list of invoice numbers already paid on that PO + supplier profile + as-of date. **Every arm receives the whole packet.** Arms 2 and 3 get it in one shared prompt. Arm 4 uses its own prompts but no extra information.

Output: one JSON object.

```json
{
  "action": "CLEAR | ESCALATE | WAIT",
  "reason_code": "none | qty_mismatch | price_mismatch | wrong_po | wrong_warehouse | duplicate_invoice | gr_missing_in_transit | unreadable_field",
  "confidence": 0.0,
  "evidence": "one sentence citing the fields compared"
}
```

| Action | Meaning |
|---|---|
| CLEAR | Documents agree. Pay the invoice. No human. |
| ESCALATE | A real discrepancy exists, or a decision-critical field could not be read. A human must act. |
| WAIT | GR is missing and goods are in transit. Re-check later. Not a human escalation. |

---

## 3. The data

Synthetic, generated by us, committed to the repo with its seed. No public dataset links PO, invoice and GR with labels, so we build one.

### 3.1 Documents are OCR-style text, not images

Each document is rendered to plain text the way an OCR engine would return it, using one of three layout templates per document type. This is a deliberate call for the two-hour window: it keeps the "messy document" thesis without image rendering or vision-model risk. Real images are a stretch goal (see section 9).

### 3.2 Case mix (held-out test set, 150 cases)

| Stratum | Share | Count | Correct action | How it is made |
|---|---:|---:|---|---|
| Clean | 30% | 45 | CLEAR | Canonical records, clean template, no noise |
| Clean but messy | 40% | 60 | CLEAR | Same agreeing records, 2 to 4 noise types applied |
| Real discrepancy | 25% | 38 | ESCALATE | One labeled mutation applied, plus 0 to 2 noise types |
| Goods in transit | 5% | 7 | WAIT | GR absent, shipping notice present with ship date within 10 days of the as-of date |

Real-discrepancy cases also carry noise. Otherwise a model learns "noise means clear," which is the wrong lesson.

Three layout templates per document type are shared across splits and strata. One extra template and one extra supplier appear only in the test set. Clean cases are spread evenly across the shared templates.

### 3.3 Noise types (for "messy")

field_reorder, line_split, line_merge, date_format (03/11/26 vs 2026-11-03 vs 3 Nov 2026), number_format (1,200.00 vs 1200 vs 1.200,00), uom_pack ("1 CS (12 EA)" vs "12 EA"), po_ref_format ("PO-00123" vs "#123" vs "P.O. 123"), vendor_alias ("ACME Corp." vs "Acme Corporation, Dallas"), handwritten_note ("recvd 10 ✓ JM" transcribed onto the GR, agreeing with the printed quantity), ocr_char_noise (0/O, 1/l/I, 5/S swaps), extra_notes_block (shipping instructions, marketing text), currency_symbol.

Rules for noise:

- Noise never changes the true value of a field. "1,200.00", "1200" and "12OO.OO" all mean 1200. A human could always recover the value.
- Noise may touch decision-critical fields (quantity, unit price, PO number, invoice number, warehouse). That is the point: a weak reader marks the field unreadable and escalates; a strong reader recovers it and clears.
- A handwritten quantity on the GR, when present, is the authoritative received quantity. On CLEAR cases it equals the printed quantity and the invoice. On a qty_mismatch case it may differ from the printed quantity, which is the hardest case in the set.
- Price on CLEAR cases never drifts. Rounding noise is presentation only.

### 3.4 Discrepancy mutations (for "real discrepancy")

| reason_code | Mutation |
|---|---|
| qty_mismatch | GR quantity differs from invoice quantity on one line |
| price_mismatch | Invoice unit price differs from PO unit price by at least 3%. Policy tolerance is 1%, so no mutation sits near the line. |
| wrong_po | Invoice references PO B; goods were received against PO A at a different price |
| wrong_warehouse | PO ships to warehouse A; GR posted at warehouse B; no transfer record |
| duplicate_invoice | Invoice number already appears in the paid-invoices list for that PO |

### 3.5 Case record format

```json
{
  "case_id": "T-0042",
  "split": "test",
  "stratum": "messy",
  "as_of_date": "2026-11-02",
  "documents": { "po": "<text>", "invoice": "<text>", "gr": "<text or null>", "shipping_notice": "<text or null>" },
  "paid_invoices": ["INV-8812"],
  "supplier_profile": { "supplier_id": "SUP-ACME", "notes": ["Writes received qty by hand at top of GR"] },
  "label": {
    "action": "CLEAR",
    "reason_code": "none",
    "noise_types": ["date_format", "handwritten_note"],
    "gold": { "po": {}, "invoice": {}, "gr": {} }
  }
}
```

`label` is never shown to any system. The `gold` block holds the canonical structured records for debugging and for the optional fine-tune.

Training split: 300 cases, same generator, different seed, shared templates and suppliers only. Generated only if the fine-tune stretch is attempted.

---

## 4. The metric

**Primary (headline):**

> False escalation rate on cases with no real discrepancy, reported only while recall on real discrepancies is 100%.

Denominator: the 105 Clean plus Clean-but-messy cases. Numerator: those the system marked ESCALATE.

**Safety gate:** every Real-discrepancy case must be ESCALATE. Report the count, for example `38/38`. Zero misses on 38 cases only proves a miss rate below about 8% at 95% confidence, so say that.

**Secondary:**

| Metric | Definition |
|---|---|
| Automation rate | CLEAR + WAIT predictions / all cases |
| Escalation rate per stratum | ESCALATE predictions / cases, reported for each of the four strata |
| Reason-code accuracy | exact match on reason_code, over Real-discrepancy cases |
| WAIT accuracy | correct WAIT / in-transit cases |
| Tokens and cost per case | input + output tokens, times list price, including every retry |
| Latency | p50 and p95 per case, end to end |

Scoring rules: a WAIT prediction on a non-WAIT case counts as ESCALATE for the metrics (it is not a human escalation, but it is not a clear either, so it is scored conservatively). `confidence` is logged, not scored. An arm that fails the safety gate still gets its false escalation rate reported, with the gate result shown next to it in red.

Accuracy and F1 are not headline numbers. They hide missed discrepancies.

**The claim we want to make:** "On the same 150 held-out cases, our Fireworks harness escalated X% of agreeing invoices versus Y% for the frontier baseline, both with 38/38 real discrepancies caught, at Z% of the cost."

---

## 5. Systems compared

All four run on identical cases, identical prompt where a model is involved, identical output schema, identical scorer.

| Arm | What it is | Why it is there |
|---|---|---|
| 1. Rules only | Regex parsers for the three shared templates, exact comparison of PO number, quantities and received quantities, price within 1% tolerance, invoice number not in paid list. Parse failure, the held-out template, or any mismatch means ESCALATE. | The industry status quo: a matching engine configured for known layouts. Shows how much messiness alone drives escalation. |
| 2. Frontier baseline | One closed frontier model, name and version pinned once a key is confirmed. One prompt, temperature 0, JSON output. | **The judged baseline.** Required by the rules. |
| 3. Open model, simple | One open model on Fireworks, same prompt as arm 2, no harness. | Shows the harness adds value beyond the model swap. |
| 4. Fireworks harness | Below. | **Our system.** |

### The harness (arm 4)

1. **Normalize.** Code strips currency symbols, unifies dates and number formats, expands known unit packs.
2. **Extract.** Small open model on Fireworks (candidate: `qwen3-vl-8b-instruct` or `glm-5p3-flash`, whichever passes the live test) turns each document into structured JSON. Every field carries `status: ok | unreadable | absent`. The model may not guess a value it cannot read.
3. **Check in code.** Line quantities times prices equal line totals. Lines sum to subtotal. PO number matches across documents. Invoice unit price within 1% of PO price. Invoice quantity equals received quantity (handwritten value wins if present). Invoice number not in paid list. GR present, or shipping notice dated within 10 days of the as-of date.
4. **Re-read only failures.** Fields that fail a check or are marked unreadable go to the larger open model (candidate: `qwen3-vl-235b-a22b-instruct` or Kimi K2.5), with the supplier profile note as a hint. Three reads, majority vote.
5. **Decide in code, fail closed.** All checks pass on readable fields means CLEAR. Any check fails on clearly read fields means ESCALATE with the matching reason code. A decision-critical field still unreadable after the re-read means ESCALATE with `unreadable_field`. That escalation counts against us in the primary metric, which is exactly right: it is the document-only escalation we are trying to eliminate by reading better, and it never risks the safety gate. GR absent with a shipping notice inside the window means WAIT. GR absent with no notice or a stale notice means ESCALATE.

Supplier profile notes are reading hints only. They never widen a tolerance or approve anything.

---

## 6. Owners and timeline

| Person | Owns | First deliverable |
|---|---|---|
| 1 | Generator: canonical records, three templates per doc type, noise injector, mutations, case mix, train/test split | Case schema agreed at 0:15; 50 sample cases at 0:30; full 150 at 0:50 |
| 2 | Runner interface, scorer, rules-only arm, results table built only from saved outputs | Scorer on the 50 samples at 0:45 |
| 3 | Frontier baseline: confirm key, pin model, write the shared prompt, run and save raw outputs | Baseline on 50 samples at 1:00; full run at 1:20 |
| 4 | Fireworks harness, arms 3 and 4 | Live-test two Fireworks models by 0:15; harness on 50 samples at 1:15; full run at 1:45 |
| 5 | Stretch (section 9), then README results, limitations, and the demo video | Video script at 1:30; video recorded at 2:00 |

| Clock | Checkpoint |
|---|---|
| 0:15 | Schema frozen. Two Fireworks models verified live. Frontier key confirmed. |
| 0:30 | 50 sample cases in the repo. Everyone tests against them. |
| 1:00 | Full test set frozen. Baseline run started. |
| 1:45 | All four arms run. Results table generated. |
| 2:00 | README updated. Video recorded. Repo made public. Submit. |

The runner interface, agreed at 0:15, is one function per arm: `run(case) -> {output, tokens_in, tokens_out, latency_ms, raw}`. The scorer never looks at anything else.

---

## 7. How this maps to the judging criteria

| Criterion | Weight | What we show |
|---|---:|---|
| Benchmark evaluation | 40% | Same 150 held-out cases, four arms, frozen scorer, headline metric with a safety gate, counts and intervals, per-stratum table, raw outputs committed. |
| Business value | 25% | AP analyst as user. Ardent: 18.4% exception rate, $9.84 per review. Our claim is expressed as reviews avoided per 100 invoices at zero missed discrepancies. |
| Technical execution | 20% | Deterministic checks around open models, extraction with unreadable status, targeted re-read, ablation of arm 3 versus arm 4. |
| Presentation | 10% | Video under 120 seconds: one messy invoice, the frontier model escalates, our harness clears it with evidence, then the results table. |
| Documentation | 5% | README with setup, one command to regenerate data, one command to run each arm, one command to score. |

Fireworks is required for every prize. Arms 3 and 4 run on Fireworks. Fine-tuning is optional and is a stretch here.

---

## 8. Decisions already made

- Real discrepancies always escalate. No auto-adjust or partial payment today.
- Documents are OCR-style noisy text, not images. (Claude's call, for time.)
- Latency is measured but not optimized. The team ranked accuracy first, cost second.
- Supplier knowledge is a JSON note per supplier, not a graph or RAG.
- No agent emails suppliers.
- Nothing extracted from a document is ever written back into a supplier note.
- Unreadable decision-critical field means ESCALATE, never CLEAR. The system fails closed.
- Every arm gets the identical case packet, including the paid-invoices list and supplier profile. Without the paid list, duplicate_invoice is undetectable and the 38/38 gate is unreachable by construction.
- Price tolerance is 1%, applied in code by arms 1 and 4 and stated in the prompt for arms 2 and 3. Mutations sit at 3% or more.
- The rules arm knows the three shared templates. It fails on the held-out template and on noise, like a real matching engine configured for known suppliers.

---

## 9. Stretch goals, in order

1. **Supplier-profile ablation.** Run arm 4 with and without profiles. Cheap, one extra run.
2. **Fine-tune.** Supervised fine-tune of the small model on the 300 training cases (document text to gold JSON). Needs a dedicated Fireworks deployment. Launch by 0:45 or skip.
3. **Real images.** Render 20 test cases to PNG with PIL and scan-style noise. Run arms 2 and 4 with vision input. Report as a separate small table.

---

## 10. Open decisions for the team, now

1. **Which frontier model is the baseline?** Must be one somebody has a working key for in the next 15 minutes.
2. **Who is person 1 through 5?**
3. **When does the repo go public?** The rules say an inaccessible repo is unscored. The owner must flip it before submitting and test the URL signed out.

---

## 11. What we will not claim

Synthetic results show controlled task performance. They do not show real-enterprise generalization, fraud detection, or payment safety. The share of real-world escalations that are document-only is our hypothesis, not a measured fact.
