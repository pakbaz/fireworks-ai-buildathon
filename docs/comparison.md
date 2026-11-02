# Kimi K3 vs our harness: inputs, outputs, and how we compare them

## The setup in one table

Both systems see **the same case**. The difference is what happens to it.

| | Frontier baseline: Kimi K3 alone | Our system: GLM 5.3 Flash + harness + company wiki |
|---|---|---|
| Model | `accounts/fireworks/models/kimi-k3` ($3 / $15 per M tokens) | `accounts/fireworks/models/glm-5p3-flash` ($0.15 / $0.50 per M tokens) |
| Documents | PO, shipping notice, goods receipt, invoice (text, or scanned images) | Same |
| Context | As-of date, company, billing history, policy, the supplier's and items' wiki pages, and a summary of the supplier's history (usual prices, usual remit-to and ship-from, largest past quantities, past problems, lead times), all pasted into one prompt | Same facts, used by code instead of pasted as text |
| How it decides | One call: read everything, decide, return JSON | 1. GLM reads every document into fields (with "unreadable" when unsure). 2. Code runs the checks: three-way match, chain of custody, duplicates, remaining quantity, and the history checks. 3. GLM re-reads only fields that failed or were unreadable. 4. A classifier in code gives a risk; the business dial gives the action |
| Calls per invoice | 1 | 1 to 2 (1.2 on average on dev) |
| Output | Same JSON schema (below) | Same JSON schema, plus the fields read, every failed check, and the dial's math |

The dial is applied to **both** rows the same way: escalate when risk × cost of a miss > (1 − risk) × $10 review cost, with the same company costs. Kimi's risk comes from the token probability of its own answer; the harness's from its checks.

## Output schema (both rows)

```json
{
  "action": "PAY | WAIT | ESCALATE",
  "reason_code": "none | short_shipped | lost_in_transit | qty_mismatch | price_mismatch | wrong_po | duplicate_invoice | near_duplicate_invoice | new_item_for_supplier | price_above_history | pack_size_changed | remit_to_changed | quantity_spike | ship_from_unusual | gr_missing_in_transit | unreadable_field",
  "next_step": "pay | wait | dispute_with_supplier | claim_from_carrier | investigate",
  "risk": 0.0,
  "at_risk_usd": 0.0,
  "evidence": "one sentence",
  "calls": 1, "cost_usd": 0.0, "latency_ms": 0
}
```

The harness adds `read` (what GLM read from each document), `issues` (every failed check), `features` (unreadable fields, values recovered from raw text), `anomalies` (informational history flags) and `dial` (review cost, cost of a miss, threshold, expected loss).

## A real case: the payment address changed

`DEVCTX-0019`, Caseworks buying 4,224 wireless chargers from VoltEdge. The PO, shipping notice, receipt and invoice all agree: 4,224 EA at $12.69 = $53,602.56. The invoice ends with:

```text
Remit payment to: Sofia, BG / Bank: Unity Commerce Bank, SWIFT UCBXXX ****2210
```

VoltEdge has always been paid in San Jose, CA. That fact was in **both** systems' inputs.

**Kimi K3 alone** (1 call, $0.0092):

```json
{"action": "PAY", "reason_code": "none", "risk": 0.048, "at_risk_usd": 0.0,
 "evidence": "PO, shipping notice, goods receipt, and invoice all agree on item CW-CHG-MAG15, quantity 4,224 EA, and unit price 12.69 (total 53,602.56) against PO-002255, with receipt booked 2026-09-05 and no prior billing on this PO."}
```

**Our harness** (1 call, $0.0009):

```json
{"action": "ESCALATE", "reason_code": "remit_to_changed", "next_step": "investigate", "risk": 0.98, "at_risk_usd": 53602.56,
 "evidence": "pay to 'Sofia, BG / Bank: Unity Commerce Bank, SWIFT UCBXXX ****2210' but this supplier is always paid at San Jose, CA",
 "dial": {"review_cost_usd": 10.0, "cost_of_miss_usd": 54460.2, "escalate_above_risk": 0.000184, "expected_loss_if_paid_usd": 53371.0}}
```

Kimi did the three-way match perfectly and paid $53,602 to a new bank in another country. A changed bank account on an otherwise perfect invoice is the most common invoice-fraud pattern. The harness caught it because code compares the payment address with the supplier's history every time, instead of hoping the model notices a fact buried in a long prompt.

## How we compare the two

1. **Same cases.** Every row runs on the same files: `data/test.jsonl` (1,000 cases, document problems) and `data/test_context.jsonl` (210 cases, history problems). Dev splits are used only for tuning.
2. **Same information.** Kimi's prompt includes everything the harness's code uses: wiki pages, policy, billing history, supplier history.
3. **Same output and dial.** One schema, one dial, one set of company costs.
4. **Metrics, in this order:**
   - Real problems caught (escalated), overall and by type. For the hospital company this must be every one.
   - Fine invoices sent to a person (false escalations), overall and on the benign look-alikes.
   - Reason code and next step correct (for example lost in transit vs shipped short).
   - Model calls, dollars and seconds per 100 invoices.
   - Paired McNemar test on the same cases, after vs Kimi and after vs the harness without the wiki.
5. **Two more rows isolate the parts:** GLM alone (the cheap model with no harness) and GLM + harness without the wiki (what the code buys before company knowledge).

## Results so far

**Document problems** (`test.jsonl`, 1,000 cases): Kimi K3 alone caught 374 of 375 real problems and sent 1 of 500 fine invoices to a person, for $9.20. GLM rows are running.

**Dev, 50 document cases:** our harness 15/15 caught, 0/28 fine invoices escalated, $0.22 per 100; Kimi 15/15, 0/28, $0.78 per 100.

**Dev, 42 context cases:**

| Type (4 cases each) | Kimi K3 alone | Our harness |
|---|---:|---:|
| Near-duplicate invoice number | 0 | 4 |
| New item for this supplier | 0 | 4 |
| Pack size changed | 3 | 4 |
| Price above this supplier's history | 0 | 4 |
| Quantity spike | 0 | 4 |
| Payment address changed | 0 | 4 |
| Unusual ship-from site | 0 | 4 |
| **All anomalies** | **3 / 28** | **28 / 28** |
| Benign look-alikes paid correctly | 14 / 14 | 14 / 14 |
| Cost for the 42 cases | $0.41 | $0.05 |

**Test, 210 history cases** (`data/test_context.jsonl`, frozen, never tuned on):

| Type (20 cases each) | Kimi K3 alone | Our harness |
|---|---:|---:|
| Near-duplicate invoice number | 6 | 20 |
| New item for this supplier | 0 | 20 |
| Pack size changed | 11 | 20 |
| Price above this supplier's history | 0 | 20 |
| Quantity spike | 0 | 20 |
| Payment address changed | 2 | 20 |
| Unusual ship-from site | 0 | 19 |
| **All anomalies** | **19 / 140** | **139 / 140** |
| Benign look-alikes paid correctly | 70 / 70 | 70 / 70 |
| Model cost per 100 invoices | $0.99 | $0.12 |
| Median seconds per invoice | 3.2 | 7.0 |

Live dashboard with every comparison: https://claude.ai/artifact/NyWmdZFGwhRAp6yQZBsFue
