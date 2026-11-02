# Claude implementation handoff — invoice-reconciliation harness

**Status:** Independent review and proposed work, **not** an approved specification or a command to implement everything.
**Prepared:** 2026-11-02, against \`main\` at \`8bac29f6db2e28084132b6d8201330668fab0d24\`.
**Audience:** Claude (code/build agent), ML engineers, evaluation lead, demo/UI owner, and submission owner.
**Scope:** \`pakbaz/fireworks-ai-buildathon\`. The repository may change quickly; **inspect HEAD and re-verify every finding before making changes**.

## Start here: decision authority

You (Claude) are expected to exercise engineering judgment, **not blindly execute this document**.

1. Inspect current source and existing work before touching files. A problem may have been fixed since this snapshot.
2. For each proposal choose **ACCEPT / MODIFY / DEFER / DROP**, with one-sentence reasoning (benefit, evidence, risk, cost, deadline). Do not implement an idea merely because it is listed.
3. Prioritize **a trustworthy, reproducible, visually convincing hackathon demonstration** over scope growth. Respect any actual submission deadline; if time is short, do the smallest defensible change.
4. Prefer narrow patches, regression tests, and reuse of existing architecture. No unnecessary multi-agent framework, vector DB, fine-tuning, or real ERP/payment integration.
5. Preserve original benchmark predictions, seed/label files, and prompts for scientific reproducibility. For changed prompts, policies, or models, create **new named experimental arms and new output paths** rather than silently overwriting frozen baselines. Do not tune on held-out test labels.
6. Never make an autonomous payment. \`PAY\` is a recommendation, not proof of payment. No real bank credentials, customer invoices, or secrets in the repo.
7. Do **not** change repository visibility, submit forms, spend substantial API credits, or upload anything externally without the owner's approval. GitHub visibility is currently private and may require an owner action.
8. If a change is risky or infeasible, **drop/defer it explicitly**; do not obscure the limitation. Where feasible, deliver a small, honest demo rather than an unproven claim.

**Requested agent output:** a short triage table (proposal, decision, reason), the minimal changes actually made, test/evaluation outputs, any remaining blockers, and the exact commit SHA. Keep this document as the handoff; put an execution report in a separate file or commit summary if useful.

## What is actually implemented (baseline to preserve)

The core already exists: \`harness/rows.py\` orchestrates the Fireworks GLM 5.3 Flash reader, code-based checks in \`harness/domain.py\`, optional supplier/item history in \`harness/supplier_history.py\`, selective re-reads, and the policy dial in \`harness/dial.py\`. The standalone reference is Kimi K3 via \`harness/config.py\`; runs are saved under \`runs/<row>/<split>.jsonl\`. Reproducible synthetic data and a context-anomaly generator live under \`generator/\`; an analyst-dashboard *design* lives in \`dashboard/\`.

Current saved context-test result in \`docs/results/dashboard/summary.json\`: on 210 synthetic cases (140 constructed anomalies, 70 benign look-alikes), \`kimi_alone\` escalated 19/140 anomalies, \`glm_harness_wiki\` escalated 139/140, and both escalated 0/70 benign cases. Reported **model inference** cost/100 cases: $0.991 vs $0.1181; median latency: 3.19 s vs 7.02 s, and p95 latency: 5.2 s vs 30.22 s. The 1,000-case general document test has a saved Kimi run, but full harness test predictions were not in this snapshot.

**Limits:** These are synthetic cases generated from modeled rules, not proof of real-world fraud detection. The strongest demonstrated distinction is *the engineered checking workflow*, not an inherent inability of a frontier model to reason about supplier history. The current dashboard description explicitly says some UI data comes from the answer key or Kimi predictions rather than the live harness.

## Priority and work packages

Treat P0 as blockers to evaluate first. P1 is high-value if the event schedule allows. P2 is optional.

| ID | Priority | Proposed work | Why it matters | Default recommendation |
|---|---|---|---|---|
| SAFE-1 | P0 | Validate model outputs; unsafe fallback must never authorize PAY | Actual payment-decision safety | ACCEPT unless already fixed |
| SAFE-2 | P0 | Payment destination as trusted identity, not city-only match | Very strong business/security demo | ACCEPT/MODIFY for a small synthetic case |
| DEMO-1 | P0 | Ground one demo case in actual harness prediction/evidence | Avoid answer-key leakage into the UI | ACCEPT, narrowly |
| SUB-1 | P0 | Correct stale README/results claims; assess public access and submission pack | Credibility and eligibility | ACCEPT; visibility action remains with owner |
| EVAL-1 | P1 | Strengthen frontier baseline and matched ablations | Defensible ML contribution | ACCEPT if time/API budget |
| EVAL-2 | P1 | Count errors/coverage and show honest cost/latency | Avoid overstated results | ACCEPT, lightweight |
| SAFE-3 | P1 | Review low-value bypass and mandatory checks | Unsafe pay-without-check loophole | MODIFY or disable for demo |
| STORY-1 | P1 | Tell one evidence-first AP analyst story | Human/business comprehensibility | ACCEPT |
| SAFE-4 | P2 | Duplicate-SKU/arithmetical edge-case tests | Robustness beyond synthetic distributions | DEFER if time short |
| EXTRA-1 | P2 | Injection tests, reviewer audit events, live upload, model routing | Future defensibility/flash | Implement only if clear incremental value |

### SAFE-1 — Strict output validation and fail-safe decisions

**Observed:** \`harness/client.py::parse_json\` extracts JSON without validating the complete expected schema. In \`harness/rows.py::alone\`, invalid or empty JSON becomes \`{}\`; absent action may yield fallback risk \`0.02\` and exposure \`0\`, which can lead to a \`PAY\` recommendation. The extraction path also uses \`parse_json(...) or {}\`. In the latest scan, \`harness/run.py\` catches Python exceptions and returns \`action="ERROR"\`; that is an improvement but **does not correct paths that silently return PAY without raising an exception**.

**Proposal:** Validate the allowed action enum, required fields and types, finite/ranged numeric values, required document presence, line quantities and critical references, and truncation/finish status before decisions. Retry only where safe and bounded. On invalid output, return a clearly nonpayable error/review-required state; align any \`ERROR\` state with UI and evaluator handling. Define unknown exposure as unknown, not $0. Prefer centralized validation in a small helper with tests; do not destabilize all result contracts without a migration plan.

**Acceptance:** malformed JSON, empty JSON, missing action, \`NaN\`/out-of-range risk, and unresolved missing invoice/PO cannot produce \`PAY\`. Genuine clean data retains correct behavior. Failures are counted separately from ordinary business discrepancies.

### SAFE-2 — Explicit payee/account verification

**Observed:** \`harness/supplier_history.py::_place_known\` uses geographical tokens for known locations; the \`remit_to_changed\` path can accept changed payment identifiers when the city still matches. The current context benchmark contains changed-destination cases, but it does not prove robust bank-account matching. Supplier history comes from synthetic \`train\` gold and must not be represented as independently verified ERP data.

**Proposal:** Split \`remit_to\` into location and payment identity where possible. Add a small **synthetic approved-payee registry** with company/supplier scope, account fingerprint or opaque ID, status, effective date, and approval provenance. Compare normalized, trusted identifiers rather than location alone. A changed/unrecognized account should require verification; an independently approved account change should pass that identity check. Do not use an invoice's own assertion as proof of approval. Avoid placing full sensitive bank details in logs.

**Acceptance:** four distinct synthetic regression cases: same city + different unapproved account => hold; changed city + preapproved account => no payment-identity hold; unchanged account + address-format variant => no hold; missing/ambiguous account identity => not silently PAY. If real account parsing is too costly, demonstrate with structured synthetic IDs and clearly label the scope. Preserve frozen benchmark results; run new safety cases as a new regression set.

### SAFE-3 — Low-value skip gate and manual risk policy

**Observed:** \`harness/rows.py\` invokes \`dial.skip_check\` before reading documents in text mode, and can emit \`PAY\` with zero model calls. \`harness/README.md\` itself documents that raising a Caseworks skip limit would skip some real problems. \`dial.raw_risk\` also uses heuristic values (for example \`0.03\`, \`0.98\`) rather than demonstrated calibrated probabilities.

**Proposal:** Treat mandatory duplicate/payee/authorization checks as non-skippable, or disable the gate in the demo pending careful design. Do not advertise a raw heuristic as calibrated financial risk. Expose separate \`risk_signal\`/severity and \`estimated_probability\` only when empirically calibrated. If changing the dial or gate, report a *new policy version* and rerun affected tests.

**Acceptance:** altered payment identity or duplicate cannot be auto-PAY via a low-value bypass; tests state which checks are performed before any shortcut. If postponed, explicitly disclose the existing gate and its limits.

### SAFE-4 — Additional reconciliation edge cases (do only after P0)

**Observed:** \`harness/domain.py::by_sku\` overwrites earlier entries when a document contains repeated lines for the same SKU. \`arith_off\` detects some arithmetic mismatches as a feature rather than always creating a blocking issue; interaction with \`at_risk_usd=0\` deserves a test. Other possible edge cases: zero/negative amounts, unit conversions, partial receipts, near-duplicate invoices on another PO.

**Proposal:** Add targeted unit tests and either aggregate repeated lines with clear price/UOM semantics or fail to manual review on ambiguous duplicates. Check that material invoice arithmetic errors cannot accidentally become \`PAY\`. If tests fail, fix the narrowest defect.

**Acceptance:** documented tests for repeated SKU lines, material arithmetic mismatch, and correctly handled harmless variants; no regression on existing preview cases.

### EVAL-1 — Stronger and more causal ML comparison

**Observed:** \`harness/prompts.py::ALONE\` emphasizes comparing documents; it mentions wiki/history but does not explicitly instruct the model to check all seven contextual anomaly types, and its enumerated \`reason_code\` choices omit the newer history-specific codes. Thus current 139/140 versus 19/140 is an important *system-level comparison*, but not proof that a well-instructed Kimi model cannot identify these patterns. Current committed \`runs/\` lacks full context predictions for \`glm_alone\` and \`glm_harness\`.

**Proposal, in order:**
1. Preserve the existing \`kimi_alone\` results **unchanged** and create a separate, versioned \`kimi_history_explicit\` prompt/arm. Give that baseline the same records and explicitly require the seven context checks, with matching allowed output reason codes. Do not leak labels, truth, or harness outputs into the prompt.
2. Run \`glm_alone\` and \`glm_harness\` on the **same** \`test_context\` cases to isolate standalone cheap-model behavior, deterministic verification, and history-aware checks.
3. Add or reuse a **rules-only** baseline if genuinely useful. Distinguish model reading from deterministic reasoning; do not imply the system needs an LLM to compare already-structured truth.
4. Predeclare metrics and report counts/denominators for anomaly recall, benign false escalation, reason/next-step correctness, unresolved errors, model calls, cost, and p50/p95 latency. Report paired comparisons on the same cases. A brief paired McNemar analysis with limitations is useful if a scorer exists.
5. Clearly disclose the synthetic-rule advantage and test benign, independently authored "hard negative" cases.

**Acceptance:** one reproducible table with frozen prompts, same test IDs, explicit errors, per-type results, and both accuracy *and* higher latency of the harness. If budget/time does not allow reruns, keep the original headline labeled "original baseline" and defer the stronger claim.

**Example commands (cost API credits; run only when approved):**

~~~bash
python3 -m harness.run --row glm_alone --split test_context --workers 4
python3 -m harness.run --row glm_harness --split test_context --workers 4
python3 eval/dashboard_data.py
~~~

A new \`kimi_history_explicit\` arm requires configuration and a distinct output path. Reuse the current caching scheme responsibly; do not overwrite the old benchmark.

### EVAL-2 — Honest accounting and failure visibility

**Observed:** \`eval/dashboard_data.py\` filters predictions with \`reason_code == "error"\`, then compares only cases in the common completed subset. That is okay if explicitly described as *conditional on successful execution*, but not as the complete operational reliability rate. \`harness/client.py\` caches API outputs and attaches original latency; model-cost fields are tariff-based token estimates, not labor or loss savings.

**Proposal:** Make total attempted N, completed N, error count, invalid-output count, sample-selection method, and dropped-case IDs visible. Keep paired comparison on the same IDs; also report end-to-end operational success. Distinguish billed-model estimate, effective cached replay, overall runtime, and human-review cost. Never equate "dollars at risk" with verified fraud or realized avoided loss.

**Acceptance:** no silent omission of errors, clear denominator labels, and results rebuilt from committed prediction artifacts. If there are zero failures, explicitly show 0/N rather than hiding the metric.

### DEMO-1 — Ground the analyst dashboard in harness evidence, not answer keys

**Observed:** \`dashboard/README.md\` states that queue/risk numbers are from \`runs/kimi_alone/test.jsonl\`, highlighted disputed values and labels come from \`case["label"]\`/gold, upload is simulated, and its dial differs from \`harness/dial.py\`. \`dashboard/Main.dc.html\` is a design-canvas page, not a standalone deployed analyst app. The backend already returns \`action\`, \`reason_code\`, \`read\`, \`issues\`, \`evidence\`, \`at_risk_usd\`, \`dial\`, and cost/latency.

**Proposal:** Deliver **one real, fully traceable case** first. Connect its displayed action, extracted invoice value, trusted supplier history, issue code, and dial math to a saved \`glm_harness_wiki\` prediction (or \`harness.api.analyze\`). Never use gold labels as the source of an inference claim. Gold can be used for offline evaluation, not to populate a supposedly detected exception. Display source text/document name and SKU; for scan highlights either implement/verify an extraction-to-image alignment, or honestly show a text evidence panel without a fake coordinate. Prefer a dependable replay of actual saved outputs over an unreliable "live upload" claim.

**Best demo case:** \`DEVCTX-0019\` from \`docs/comparison.md\` — all four documents match, the invoice's payment destination differs from company history, original Kimi predicts \`PAY\`, the harness predicts \`ESCALATE\`. Show the distinct evidence sources side by side and the precise rule fired. The workflow ends at **human verification**, not automatic transfer.

**Acceptance:** each UI field used to explain the decision can be traced to a prediction or trusted reference record; no \`label.gold\`-derived disputed values shown as if model-detected; if using a dial control, recompute from actual \`harness/dial.py\` policy rather than a UI-only approximation. Clearly label mock interactions.

### STORY-1 — Business/user narrative and claim discipline

**Audience:** AP analyst (needs evidence and next action), AP manager (review workload), finance controller (payment integrity), procurement (legitimate supplier changes), security (bank-account authorization), technical judge (causal comparison), product judge (clarity).

**Suggested 110-second script:**
1. **Problem:** Humans manually investigate invoice exceptions; a perfect three-way match is not always enough.
2. **Counterexample:** One $53,602.56 synthetic invoice matches PO, shipment and receipt, but specifies a different payment destination.
3. **Contrast:** Show original Kimi's saved \`PAY\` recommendation; then harness \`ESCALATE\`, historical supplier fact, triggered rule, and next-step \`investigate\`.
4. **Measured result:** 139/140 versus 19/140 on *designed synthetic context anomalies*, 0/70 benign escalations for both, ~$0.12 versus ~$0.99 model inference cost/100; disclose that the harness is slower (~7.0 versus ~3.2 seconds median; p95 ~30 versus ~5 seconds).
5. **Human outcome:** The analyst reviews evidence and verifies payment details through an independent trusted process. The system does not autonomously pay.

**Claim rules:** Do not say Kimi "paid" an invoice; it **recommended** PAY. Do not call a changed account proof of fraud. Do not claim the harness "prevented $53,602 in losses": that is a synthetic amount potentially exposed. Do not claim frontier models are categorically incapable of history checks; the engineering improvement is **explicit, repeatable, auditable verification**. Avoid implying model-only inference cost equals total operating cost; review work and missed-risk costs matter.

**Acceptance:** a viewer unfamiliar with ML understands (a) what changed, (b) why it was flagged, (c) which saved evidence supports it, and (d) what Maria does next.

### SUB-1 — README, reproducibility, accessibility, submission

**Observed:** The top of \`README.md\` now reports context-test results, but subsequent "Status" and "Results" sections still say the benchmark and application are not built/results not run; these are stale and contradictory. \`docs/comparison.md\` has more up-to-date results. \`dashboard/README.md\` correctly discloses mock elements. The repo's GitHub metadata reports **private**. \`README.md\` quotes an event rule requiring public access during judging.

**Proposal:**
- Update stale status claims **without overstating**: data generator/harness/context prediction results implemented; full general harness test, rigorous calibration, and production ERP workflow incomplete; dashboard is a design with simulated aspects.
- Provide exact run commands, data provenance/seeds, test IDs, model versions/pricing assumptions, frozen prompt/policy hashes or commit, known failures, comparison script, and results paths. A no-API path (\`python3 eval/dashboard_data.py\`) should recompute reported metrics from saved predictions. A fresh run requires \`FIREWORKS_API_KEY\` and incurs possible cost.
- Confirm video duration below event limit and accessibility, and cite the **judged commit SHA**, not just the latest branch.
- Check for credentials and confidential information before any public release. The owner must decide/review any repository visibility change; do not silently change it.
- If event submission has closed, preserve this as a post-event reproducibility and hardening backlog instead of pretending to submit retroactively.

**Acceptance:** README and comparison are consistent with files at the judged commit; an outsider can reproduce reported metrics from committed data; repo/video access and publication rights are explicitly reviewed by the owner; all missing/partial components are labeled.

## Suggested execution path (adapt to remaining time)

**First, five-minute triage:** Recheck HEAD, confirm which items are already fixed, check event clock/budget and submission constraints, choose at most 2–3 changes. Prefer actual blocking correctness bugs and demo truthfulness over additional feature breadth.

**If only a short window remains:** (1) SAFE-1 regression guard; (2) SUB-1 truthful status + owner accessibility checklist; (3) DEMO-1 one evidence-grounded case. Keep existing results as originally run; note limitations.

**If more time remains:** SAFE-2 synthetic payee identity regression; EVAL-2 error accounting; then EVAL-1 matched ablations/stronger Kimi. Do not let a long full-test API run block submission.

**After the event:** SAFE-4 domain edge cases, calibration, real document layouts, historical effective-date/versioning, adversarial prompt-injection testing, controlled approvals and audit log, integration with real supplier master/ERP. Only pursue cross-model dynamic routing if experiments show an actual accuracy/cost benefit.

## Verification checklist (run only the relevant parts)

- \`python3 -I generator/context_check.py\` — validates generated context labels; keep inputs frozen.
- \`python3 eval/dashboard_data.py\` — rebuilds current comparison data from saved predictions without inference API calls.
- \`python3 -m harness.api examples/preview/cases.jsonl PREVIEW-03 --row glm_harness_wiki\` — single-case inference, requires Fireworks key.
- Run targeted unit/regression tests for each changed safety rule; if none exist, create small \`unittest\` tests rather than relying solely on a large API benchmark.
- Before merging, confirm no gold-label data enters inference/demo explanation, no secrets are committed, and metrics are clearly marked synthetic.
- Capture exact commit SHA, commands and outcome, plus any items deliberately dropped.

## Final agent decision record (fill in after review)

| ID | ACCEPT / MODIFY / DEFER / DROP | Justification and evidence | Changed files / tests |
|---|---|---|---|
| SAFE-1 | | | |
| SAFE-2 | | | |
| SAFE-3 | | | |
| SAFE-4 | | | |
| EVAL-1 | | | |
| EVAL-2 | | | |
| DEMO-1 | | | |
| STORY-1 | | | |
| SUB-1 | | | |
| EXTRA-1 | | | |

**Bottom line:** Aim to demonstrate a smaller model supported by *independent business evidence and deterministic checks*, with an honest baseline and evidence-grounded analyst interface. Do not trade safety, benchmark integrity, or truthful representation for flashy features.
