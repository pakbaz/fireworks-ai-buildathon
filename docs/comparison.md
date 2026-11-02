# Kimi K3 vs our harness: inputs, outputs, and how we compare them

**Latest low-reasoning results and full 1,000-case comparison:** see [../results.md](../results.md) and the [updated demo charts](results/demo/README.md). This page preserves earlier/default-reasoning experimental details; its older tables are not the final selected system's results.

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

## A real case: 82 infusion pumps

`TESTCTX-0149`, from the frozen test set. Northside Hospital Supply is invoiced for 82 dual-channel infusion pumps at $4,835.44 each, $396,506.08. The PO, shipping notice, goods receipt and invoice all agree. In 300 past invoices from this supplier, Northside has never ordered more than 11 of this pump.

Both systems had that history. Kimi K3 was explicitly told to escalate any quantity more than 3 times the largest past order.

**Kimi K3 alone** (1 call, $0.0099):

```json
{
 "action": "PAY",
 "reason_code": "none",
 "risk": 0.2016,
 "evidence": "PO, shipping notice, goods receipt and invoice all agree on NS-INF-2200 at 82 EA and 4,835.44/EA (396,506.08), the price is within 10% of the supplier's historical mean (4,842.17), quantity is below the 3x spike threshold, and remit-to (Hamburg, DE) and ship-from (Hamburg, DE) match supplier history; the prior paid invoice on this PO was for a different SKU (NS-VEN-0450) and amount, so it is not a duplicate."
}
```

**Our harness** (GLM 5.3 Flash reads, code checks; 1 call, $0.0010):

```json
{
 "action": "ESCALATE",
 "reason_code": "quantity_spike",
 "next_step": "investigate",
 "at_risk_usd": 343316.24,
 "evidence": "NS-INF-2200: 82 EA vs at most 11 ever ordered"
}
```

Kimi did the three-way match perfectly and recommended paying. The harness compared the quantity with the company's own order history, as code does on every invoice, and sent it to a person. This is the general pattern on the test set: told what to check, Kimi still misses 19 of 140 history problems, mostly quantity spikes (10 of 20 caught) and items a supplier never sold before (15 of 20). The amount is synthetic exposure, not a prevented loss.

An earlier example in this file, `DEVCTX-0019` (a changed payment address), came from the run before Kimi was told to check history; once told, Kimi catches all 20 payment-address changes on test, so it is no longer a fair illustration.

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

**Document problems** (`test.jsonl`, first 300 of the 1,000 cases, same mix; both systems on the same invoices):

| System | Real problems caught | Fine invoices sent to a person | In-transit waited | Model cost per 100 | Median time |
|---|---:|---:|---:|---:|---:|
| Kimi K3 alone | 117 / 117 | 0 / 148 | 35 / 35 | $0.93 | 3.5 s |
| GLM 5.3 Flash + our checks | 117 / 117 | 20 / 148 | 34 / 35 | $0.29 | 22 s |

Here the frontier model is better: our harness raised 20 false alarms, 15 from GLM misreading a quantity on messy invoices and 4 from the new history checks firing on noisy text. Its advantage on these cases is cost, not accuracy. Kimi K3 on all 1,000: 374 of 375 caught, $9.20.


**Dev, 50 document cases (latest run):** our harness 15/15 caught, 2/28 fine invoices escalated (two GLM misreads), $0.22 per 100; Kimi 15/15, 0/28, $0.78 per 100.

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

**Test, 210 history cases** (`data/test_context.jsonl`, frozen, never tuned on). After reviewer feedback, Kimi K3 alone is explicitly asked to check supplier history and has the seven history reason codes; an earlier run without that instruction caught only 19 of 140 and is superseded.

| Type (20 cases each) | Kimi K3 alone | Kimi K3 + our checks | GLM 5.3 Flash + our checks |
|---|---:|---:|---:|
| Near-duplicate invoice number | 19 | 20 | 20 |
| New item for this supplier | 15 | 20 | 20 |
| Pack size changed | 19 | 20 | 20 |
| Price above this supplier's history | 18 | 20 | 20 |
| Quantity spike | 10 | 20 | 20 |
| Payment address changed | 20 | 20 | 20 |
| Unusual ship-from site | 20 | 20 | 19 |
| **All anomalies** | **121 / 140** | **140 / 140** | **139 / 140** |
| Benign look-alikes paid correctly | 64 / 70 | 70 / 70 | 70 / 70 |
| Right reason code | 100 | 140 | 139 |
| Model cost for the 210 | $2.27 | $2.92 | $0.25 |

What this shows: the deterministic checks drive the result; the reader model is close to interchangeable once they are in place, so the cheap model is the right choice. Limits: the test uses new examples of the same seven anomaly types the checks were written for; GLM's one miss was a letterhead city read as the ship-from (prompt since tightened, rerun pending); GLM's p95 latency on this set was 30 s against Kimi's 5 s.

Live dashboard with every comparison: https://claude.ai/artifact/NyWmdZFGwhRAp6yQZBsFue
