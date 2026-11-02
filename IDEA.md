# Idea: Invoice Reconciliation

## Problem

Shipments often change after the order. For example, a package had a set number of items, but one item was pulled just before it shipped. The invoice still lists that item.

When the shipment and invoice arrive, the company must:

- Match the invoice to the purchase order (PO).
- Check that the prices are correct.
- Check what was actually delivered and what we should finally pay.

Today, most checks use deterministic tools. Some teams use AI, but people still step in often. This is a very high-volume task, so each human review costs a lot.

## Goal

Make reconciliation more efficient in **token usage** and more **accurate**, so the system asks a human far less often, without missing real problems.

## The task to evaluate

For each case (PO + invoice + shipping or receiving record), decide:

- **Auto-approve**: documents match, or differences are within tolerance.
- **Escalate to a human**: a real discrepancy (missing item, wrong quantity, wrong price, extra charge).

Optional: also output the discrepancy type and the corrected amount to pay.

## Benchmark plan

1. **Dataset.** Build PO / invoice / receipt sets with known labels. Inject real-world problems: removed items, short shipments, price changes, duplicate lines, unit mismatches, rounding noise. Keep a held-out test split.
2. **Frontier baseline.** Run a frontier model as a yes/no escalation classifier. Save its scores.
3. **Our system.** Open models on Fireworks AI. Ideas:
   - Deterministic pre-checks (line matching, math) before any LLM call.
   - Small open model for extraction and line matching, larger model only for hard cases.
   - Structured output (JSON) to cut tokens.
   - Optional fine-tune on the training split.
4. **Rerun** the same held-out cases with the same scoring.
5. **Report** before and after.

## Metrics

- **Escalation rate** (lower is better, at equal or better recall).
- **Discrepancy recall** (missed problems are the costliest error).
- **Precision / F1** on the escalate decision.
- **Amount-to-pay accuracy** (optional).
- **Tokens and cost per invoice.**
- **Latency per invoice.**

---

# Brainstorm notes, session 2 (team discussion)

## More discrepancy scenarios

- **Multiple supplier locations, multiple buyer POs.** One supplier ships the same item from several locations to several buyer locations. The buyer may have a different PO, with a different price, for each location. The invoice references one PO, but the goods ship against another PO. Result: invoice-to-PO mismatch on price and PO reference.
- **Goods receipt (GR) vs invoice quantity.** The supplier ships against a PO, sends an invoice, and the buyer posts a goods receipt on the PO. If the received quantity differs from the invoiced quantity, a person must check what happened.
- **Wrong warehouse.** The PO points to warehouse A. The goods ship to, and are received at, warehouse B. The invoice still says warehouse A, where there is no matching receipt. The system should ask: "Was this rerouted? Did another location receive this part around the same time?"

## What is the target outcome?

The team discussed which output matters most: accuracy, latency, cost, or fewer human escalations.

- **Primary: accuracy.** Better accuracy leads to fewer human escalations.
- **Latency:** not important for this use case.
- **Cost (tokens):** secondary, still worth measuring.

## Current process and pain points

- Invoices arrive in many formats. Fields sit in different places on each document.
- Scanned or unreadable invoices go straight to a human.
- The GR document is another input. Depending on company size, it can be a scanned paper sheet or a system record.
- Someone enters invoice quantities and descriptions into the system, then cross-checks against what was received.
- Main pain point: too many cases are escalated to a human. Two causes:
  1. **Image to text:** scanned and varied formats are not read reliably.
  2. **Reasoning:** current models are not good enough at this specific cross-check. A smarter model might find many of these cases trivial.

## Proposed phases

1. **First cut:** a good image-to-text (OCR / vision) step plus a good reasoning step.
2. **Second stage:** fine-tune for this task. Use synthetic forms (including handwritten ones) and teach the model what to look for on each item type.

## Debate: is the hard part reading or reasoning?

- One view: image recognition is a general, mostly solved problem. If the backend already links PO, receipt, and inventory, much of the check is a simple data join.
- Counter view: the hard cases are not simple joins. Examples are rerouted warehouses, multi-location suppliers, and company-specific ordering habits. These need reasoning with company context.

## Company and supplier knowledge

- Each company has its own habits. Example: a company orders a part with no fixed quantity ("send however many you have"). Not every company does this.
- The model needs domain context: how this company places orders, what it orders regularly, its jargon, and how it works with each supplier.
- **Supplier wiki / memory:** keep a knowledge base per supplier (merchant). When a person flags a known pattern for a supplier ("they ship without a quantity cap"), every reviewer and the agent can use it next time.
- **RAG vs knowledge graph:** RAG was suggested. An alternative is a graph with entities (people, suppliers, POs, invoices, warehouses, items) and relationships between them. The system can traverse the graph to decide whether a case needs escalation.
- The model is "the brain." The graph and data around it give it the context it needs.

## Open questions

- Do we include OCR on scanned documents in the hackathon scope, or start from structured data?
- Which scenarios go into the benchmark first: GR vs invoice quantity, wrong PO, wrong warehouse?
- Supplier knowledge: simple per-supplier notes (fast to build) or a full graph (more work)?

---

# Brainstorm notes, session 3 (problem framing)

## Reframe: a harness, not just a model

- The value is the **harness** on top of the LLM. It knows the company, its suppliers, and how they interact.
- Picture a **daily assistant for the person who handles POs**. Each morning there are about 100 POs with their invoices and GRs. The assistant sorts them, resolves what it safely can, and puts the rest in priority order.
- **Goal:** minimize the number of human escalations. The harness should learn which cases truly need a human and resolve the rest from past interactions and what it knows about the vendor.

## Two kinds of escalation

1. **Real discrepancy.** The goods received differ from what the invoice says. No model can fix this. A person must contact the supplier and act. These always stay with a human and are **out of scope** for automation.
2. **Document-only escalation.** All three documents (PO, invoice, GR) actually agree, but the system escalates anyway. Causes: odd formatting, scanned pages, handwriting, notes on the GR, fields in unusual places. A better reasoning harness should resolve these. **This is the target.**

Notes:
- The GR (goods receipt) confirms what arrived and feeds inventory. Carriers handle it, so it can contain mistakes or handwritten notes.
- "Shipped but not yet arrived" is another source of escalation. It needs extra data sources (shipping status), so it is hard. Possibly out of scope.
- An agent that emails the supplier to ask for clarification was discussed. The team leaned against it for now. Escalation means a human takes action; we are not building the follow-up agent.

## Baseline and metric

- Today, a basic agent might escalate 60% of invoices because it cannot decide. The question is how far we can lower that.
- **Baseline:** a plain frontier LLM gets the three documents (PO, invoice, GR) and answers "Is there a discrepancy? Does a human need to look?"
- **Synthetic dataset:** build cases with known labels:
  - **Clean but messy:** no real discrepancy, only formatting noise (scans, handwriting, moved fields, notes). The correct answer is "no escalation."
  - **Real discrepancy:** quantity or price really differs. The correct answer is "escalate."
- **Main metric: false-positive escalations.** How often does the system escalate a case that only had formatting noise? Also track missed real discrepancies, which must stay near zero.
- Leave other databases out for now. Test whether the model can read the documents correctly and reason about them.

## Why fine-tuning still helps

- Example from tax forms: each form has key data in fixed places. Sometimes it is handwritten or hard to read. If the model knows that a field is critical, it puts in more effort to read it, as a human does.
- We cannot train for every form in the world. That is why we use an LLM, but company-specific tuning still adds value.

## Company "tribal knowledge"

- Every company works differently: its own handlers, suppliers, and habits.
- Example: one supplier always writes numbers on top of the form in a certain way. Only people in that company know this.
- If the company provides this context (supplier notes, past decisions), the harness can use it.
- There is no single solution for everyone. The harness adapts per company, through context (supplier notes or a knowledge graph) and optionally fine-tuning.

## Proposed hackathon scope (from this session)

- **Input:** PO + invoice + GR, with some documents as scanned or messy images.
- **Task:** decide "escalate" or "no escalation."
- **Dataset:** synthetic, with formatting-only noise cases and real-discrepancy cases.
- **Baseline:** frontier LLM, same inputs and prompt.
- **Our system:** open-model harness on Fireworks (better reading + reasoning + supplier context, optional fine-tune).
- **Win condition:** fewer false-positive escalations than the baseline, with no increase in missed real discrepancies.
