# Evidence Integrity & Recovery Closure — 2026-08-08

Status: **STATIC PASS / METAEDITOR+MT5 REQUIRED**

This closure follows the second independent Claude review and a further GPT-side audit of recovery/evidence semantics.

## Claude findings verified

- Claude's original UNKNOWN/terminal P0 was real in its branch and its redesign now keeps UNKNOWN non-terminal.
- Claude's re-check of the GPT production integration was materially correct: the earlier dead-module critique no longer applies.
- One documentation statement in the Claude response is stale/misleading: current `ARCHITECTURE_V1.3.md` explicitly documents the real `Data/` and `News/` directories and mentions `Market/` / `Calendar/` only as names used by earlier conceptual drafts.

## Additional GPT-side findings closed

### 1. Outcome evidence was present but insufficiently scoped
The GPT branch already had a reachable `OutcomeEngine` and a real `SaveOutcome` caller, unlike the gap Claude found in its own branch. However, statistics could mix incompatible evidence.

Closed by:
- explicit `SHADOW` vs `DEMO` outcome source
- provenance columns for rule version, scoring version, parameter hash, broker-spec hash and execution id
- statistics filtered by evidence source + rule + scoring + parameter identity
- signal evidence identity additionally scoped by parameter hash and broker spec

### 2. Demo outcome must come from broker execution, not quote observation
Closed by splitting outcome paths:
- Shadow outcomes are labelled `SHADOW_OBSERVED_QUOTE`
- Demo outcomes are reconstructed only from broker deals correlated by `DEAL_POSITION_ID`
- TP/SL classification comes from broker `DEAL_REASON_TP` / `DEAL_REASON_SL`
- other closes are not silently counted as TP or SL

### 3. Terminal execution / outcome crash window
A terminal execution could be persisted and the process could fail before the outcome row was written.

Closed by:
- `LoadLatestExecutionWithoutOutcome`
- startup recovery inside `OutcomeEngine.Attach()`
- immutable outcome insert semantics

### 4. Long-lived execution history window
Recovery previously anchored history on `updated_at`. A trade open longer than the small recovery window could lose its entry deal from the selected history range.

Closed by:
- immutable `AS_ExecutionRecord.created_at`
- schema v7 migration adding `executions.created_at`
- Reconciler and Demo outcome reconstruction anchored on execution creation time

### 5. Same-symbol historical deal misattribution
Magic+symbol alone can attribute an older trade on the same symbol to the current unresolved execution.

Closed by:
- derive broker `position_id` from exact `order_ticket` using `ORDER_POSITION_ID`
- fallback discovery from an entry deal whose `DEAL_ORDER` equals the exact submitted order
- aggregate history only after position identity is proven
- no arbitrary same-symbol deal fallback

## Migration discipline

- v6 remains the scoped-outcome migration.
- execution creation timestamp is a separate v7 migration.
- this avoids silently changing the meaning of an already committed schema version.

## Tests / gates added

- `EvidenceIntegritySelfTests.mq5`
- MetaEditor compile gate includes the new evidence test
- static gate enforces:
  - production reachability
  - live signal wiring
  - indicator caching
  - UNKNOWN blocking
  - four-source reconciliation
  - order-to-position correlation
  - execution creation timestamp
  - terminal-without-outcome recovery
  - Shadow/Demo outcome separation
  - scoped statistics
  - schema v7 migrations

## Latest GitHub static evidence

Latest successful run on current closure:
- files: **60**
- lines: **2640**
- reachable production modules: **45 / 45**
- result: **PASS**

## Deliberate non-adoption: manual UNKNOWN acknowledgement

Claude added an in-system `AcknowledgeUnresolved()` escape path. GPT has not copied it. UNKNOWN remains blocking.

Reason: an operator acknowledgement is itself an authority override and can re-open the submit gate while an invisible broker order still exists. A safe operator-recovery design should be decided only after real MT5 restart/reconciliation tests establish which unknown states actually occur and what broker evidence is available. Until then, wedging safely is preferable to silently permitting duplicate exposure.

## Blocking next step

No compile/runtime claim is made. Run Windows MetaEditor and MT5 qualification:
1. compile every configured target: 0 errors / 0 warnings
2. run all self-tests including `EvidenceIntegritySelfTests.mq5`
3. restart matrix
4. duplicate transaction replay
5. Alert Only smoke
6. Shadow smoke
7. controlled Demo Confirm only after all above pass
