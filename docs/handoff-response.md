# Response to the implementation handoff (docs/claude-implementation-handoff-2026-11-02.md)

Reviewed against `main` at `4d6d95c`; changes landed in `ade4224`. Also folds in the reviewer notes on branch `feedback/aparna-review`.

| ID | Decision | Reason | Changes |
|---|---|---|---|
| SAFE-1 | ACCEPT | Real bug: malformed output in the Kimi-alone row fell back to risk 0.02 and could recommend PAY | `harness/rows.py`: invalid or missing action, or an empty reader output, returns ESCALATE with `invalid_model_output`; API failures are `action: ERROR`. Regression checked with a stubbed malformed response in both rows |
| SAFE-2 | DEFER | An approved-payee registry needs new data; not doable safely before submission | Stated as a limit in the README: payment checks compare locations, not verified bank identities |
| SAFE-3 | MODIFY | The gate never fired on our data, but a pay-without-check path should not exist by default | `harness/dial.py`: skip limit defaults to 0 (off); a company must opt in |
| SAFE-4 | DEFER | Edge-case tests after the event | None |
| EVAL-1 | ACCEPT (done) | Kimi K3 now has an explicit history instruction and the seven codes (121/140); new row Kimi K3 + our checks (140/140) separates checks from model | Original runs kept as `runs/kimi_alone_v1_no_history_instruction/` and `runs/glm_harness_wiki_v1/`; GLM alone and no-wiki test rows still pending |
| EVAL-2 | MODIFY | Errors are recorded and excluded explicitly | Run summaries print error counts; README states the rule. Dashboard denominators show completed cases |
| DEMO-1 | DEFER to dashboard owner | The review design reads Kimi predictions and the answer key | Harness predictions with `read`, `issues`, `evidence` and `dial` are in `runs/glm_harness_wiki/`; best case `DEVCTX-0019` |
| STORY-1 | ACCEPT | Claim discipline | Docs say Kimi recommended PAY, dollars are exposure not prevented loss, results are synthetic |
| SUB-1 | ACCEPT | README contradicted itself | Status and Results rewritten. Repository visibility is the owner's decision |
| EXTRA-1 | DROP for now | No time to do injection or routing work properly | None |
