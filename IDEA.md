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
