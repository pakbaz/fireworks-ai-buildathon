# Results

**Presentation graphics and presenter deck:** [docs/results/demo/README.md](docs/results/demo/README.md) · [docs/results/demo/index.html](docs/results/demo/index.html) (open the HTML locally after cloning).

The numbers for the video and the presentation. Every figure comes from a saved prediction file listed at the bottom, scored against the frozen test answer keys. All data is synthetic.

**Our system:** GLM 5.3 Flash on Fireworks reads the documents; code checks them against the company's knowledge (purchase history, item pages, supplier pages); a business dial decides. GLM runs with low reasoning.
**Frontier baseline:** Kimi K3 on Fireworks, given the same documents and the same company knowledge, and told what to check.

## 1. The headline: problems only company knowledge can see

210 invoices where the purchase order, shipping notice, receipt and invoice all agree, but something is wrong compared with the company's history (a changed payment address, a quantity far above anything ever ordered, an item this supplier never sold, a price above what it always charges, a near-duplicate invoice, a smaller pack, an unusual ship-from site), plus 70 look-alikes that are fine.

| System | Problems caught | False alarms | Model cost per 100 invoices |
|---|---:|---:|---:|
| Kimi K3 alone, told to check history | 121 / 140 | 6 / 70 | $1.08 |
| **Our system: GLM 5.3 Flash + checks + company knowledge** | **139 / 140** | **0 / 70** | **$0.06** |

- Our system catches 18 more problems, raises no false alarms, and costs about 19x less.
- Where Kimi slips most: quantity spikes (10 of 20 caught) and items a supplier never sold before (15 of 20). Ours: 20 of 20 on both.

**What makes the difference:**

| Same checks, different setup | Problems caught |
|---|---:|
| Kimi K3 reading + our checks + company knowledge | 140 / 140 |
| GLM 5.3 Flash reading + our checks + company knowledge (ours) | 139 / 140 |
| GLM 5.3 Flash + our checks, **without** company knowledge | 40 / 140 |

Company knowledge and deterministic checks drive most of the improvement on this synthetic test. The Kimi harness still catches one more context anomaly than the low-reasoning GLM harness; the cheaper reader offers a favorable model-cost tradeoff rather than identical behavior.

## 2. Ordinary document problems: near-equal recall, 12x cheaper, more false reviews

1,000 invoices with problems visible in the documents themselves (short shipments, goods lost in transit, price above the PO, wrong PO, duplicates), plus correct, messy and in-transit invoices.

| System | Real problems caught | Fine invoices sent to a person | Model cost, 1,000 invoices |
|---|---:|---:|---:|
| Kimi K3 alone | 374 / 375 | 1 / 500 | $9.20 |
| **Our system** | **373 / 375** | 27 / 500 | **$0.76** |

Nearly the same recall (373/375 vs 374/375) at roughly one-twelfth the model-inference cost. Kimi is better at not raising false alarms: our system sends about 5 in 100 fine invoices to a person, mostly messy ones. Model-token savings do not necessarily translate into lower human-review cost.

## 3. Low reasoning: faster and cheaper, with a measured tradeoff

GLM 5.3 Flash always reasons before answering. Setting its reasoning to low, on the same invoices:

| | Default reasoning | Low reasoning | Change |
|---|---:|---:|---:|
| Document problems (300): cost per 100 invoices | $0.29 | $0.08 | **73% cheaper** |
| Document problems: median time per invoice | 22.2 s | 5.1 s | **4.4x faster** |
| Document problems: caught / false alarms | 117/117, 20/148 | 117/117, 9/148 | fewer false alarms |
| History problems (210): cost per 100 invoices | $0.13 | $0.06 | **56% cheaper** |
| History problems: median time per invoice | 7.7 s | 3.1 s | **2.5x faster** |
| History problems: caught / false alarms | 140/140, 0/70 | 139/140, 0/70 | one fewer catch |
| All 1,000 document invoices, wall-clock time | about 90 min (estimated) | **9 min** | |

The account's limit is generated tokens per minute; low reasoning cuts GLM's output from about 5,000 to about 900 tokens per invoice, which is why throughput rises about 4x.

## 4. One case for the demo

`TESTCTX-0149` (file: [examples/demo/TESTCTX-0149.json](examples/demo/TESTCTX-0149.json)). Northside Hospital Supply is billed for 82 infusion pumps at $4,835.44 each, $396,506.08. All four documents agree. The hospital has never ordered more than 11.

- **Kimi K3 alone**, told to check quantities against history: recommends **PAY**. "PO, shipping notice, goods receipt and invoice all agree on NS-INF-2200 at 82 EA and 4,835.44/EA."
- **Our system:** **ESCALATE**, quantity spike. "NS-INF-2200: 82 EA vs at most 11 ever ordered."

Say "recommends", not "pays": no system here makes payments. The $396,506 is exposure on a synthetic invoice, not a prevented loss.

## 5. Say these plainly

- All cases are synthetic. The history test covers the seven anomaly types the checks were written for (new examples, unseen seed), not new kinds of fraud.
- On plain document problems, Kimi alone raises fewer false alarms, and GLM 5.3 Flash alone does too (117/117, 0/148 on the 300). The next step is to route ordinary invoices around the history checks.
- On scanned images (100 invoices), Kimi K3 reads better: both catch nearly every problem (25/25 vs 24/25), but ours sends 18 of 50 fine invoices to a person against 2 for Kimi, because GLM misreads scans. Ours costs $0.13 per 100 against $1.90. Use the text results for claims; the reader for scans is the next thing to improve.
- Our system is slower per invoice (median about 4.6 s against 3.4 s for Kimi on the 1,000) but runs many invoices in parallel.

## Where each number comes from

| Result | File |
|---|---|
| Our system, history problems | `runs/glm_harness_wiki_low/test_context.jsonl` |
| Our system, all 1,000 document problems | `runs/glm_harness_wiki_low/test.jsonl` |
| Kimi K3 alone, history problems (told to check) | `runs/kimi_alone/test_context.jsonl` |
| Kimi K3 alone, all 1,000 document problems | `runs/kimi_alone/test.jsonl` |
| Kimi K3 + our checks, history problems | `runs/kimi_harness_wiki/test_context.jsonl` |
| Our checks without company knowledge, history problems | `runs/glm_harness_low/test_context.jsonl` |
| Default-reasoning comparison, document problems (300) | `runs/glm_harness_wiki/test.jsonl` |
| Default-reasoning comparison, history problems | `runs/glm_harness_wiki_v2/test_context.jsonl` |
| GLM 5.3 Flash alone (for the next-step note) | `runs/glm_alone_low/test.jsonl` |
| Scanned images (limits note) | `runs/glm_harness_wiki_low/test_images.jsonl`, `runs/kimi_alone_v2/test_images.jsonl` |
| Answer keys | `data/test.jsonl`, `data/test_context.jsonl` |
| Demo case | `examples/demo/TESTCTX-0149.json` |

Each line of a run file is one invoice: `action`, `reason_code`, `evidence`, `cost_usd`, `latency_ms`. Rebuild the dashboard numbers with `python3 eval/dashboard_data.py`. Live dashboard: https://claude.ai/artifact/NyWmdZFGwhRAp6yQZBsFue. Video: see the link at the top of the README.
