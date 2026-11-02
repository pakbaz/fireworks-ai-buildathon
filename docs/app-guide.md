# Building an app on the harness

Everything here runs today on the preview cases in [examples/preview](../examples/preview). The full dataset will land in `data/` with the same format.

## Call it

```python
from harness.api import analyze
result = analyze(case, row="glm_harness_wiki")          # text documents
result = analyze(case, row="glm_harness_wiki", images=True)  # scanned images, if the case has them
```

```bash
python3 -m harness.api examples/preview/cases.jsonl PREVIEW-03 --row glm_harness_wiki
```

Needs a Fireworks key in a git-ignored `.env` (see `.env.example`). Without a key, design against the saved outputs in `examples/preview/predictions/`: one file per row, one JSON object per case.

Timing: the harness takes about 5 to 40 seconds per case on GLM 5.3 Flash (it always reasons first). Run it in the background and show a spinner, or precompute a queue. Results are cached on disk, so a second call for the same case is instant.

## What a result contains

| Field | Show it as |
|---|---|
| `action` | The decision: PAY, WAIT or ESCALATE (Ask a person) |
| `reason_code`, `next_step` | What is wrong and what to do: e.g. lost_in_transit, claim_from_carrier |
| `evidence` | One line, e.g. "TUB05: billed 50, received 40, shipped 50" |
| `issues` | Every failed check, each with code, next step and detail |
| `read` | What the reading expert extracted from each document, per line |
| `features.unreadable` | Values the model could not read and refused to guess |
| `risk`, `at_risk_usd` | Probability that paying would be wrong; dollars that would be lost |
| `dial` | Review cost, cost of a miss, the risk threshold, expected loss vs expected review cost |
| `calls`, `cost_usd`, `latency_ms` | Model calls and spend for this case |

## Screens that tell the story

1. **Maria's queue.** All invoices for the day, sorted by expected loss (`dial.expected_loss_if_paid_usd`). Three piles: Paid automatically, Waiting for delivery, Needs you.
2. **One invoice.** The four documents side by side (or the scanned images), the fields the model read with any unreadable ones highlighted, then the checks as a list of passes and fails.
3. **Where did it go wrong.** A strip: Ordered 50, Shipped 50, Received 40, Billed 50, with the break highlighted and the next step ("claim $124 from FastFreight").
4. **The dial.** The same doubtful invoice at Northside (infusion pumps) and Caseworks (phone cases), with a slider for review cost and strictness, showing the decision flip.
5. **What the company knows.** The wiki page that changed the answer (for PREVIEW-02, "TUB-05: 1 case = 50"), with and without it.
6. **Frontier vs us.** The same case through `kimi_alone` and `glm_harness_wiki`: decision, explanation, cost.

Which knowledge made the difference and how we differ from a frontier model: [how-we-differ.md](how-we-differ.md).
