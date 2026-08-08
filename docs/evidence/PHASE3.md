# Phase 3 Evidence — Explainable Scoring & Lifecycle

Status: **PASS_STATIC**

Implemented:
- score component model with explicit contributions
- explicit penalty ledger
- hard-veto ledger independent from numeric score
- lifecycle state machine with guarded transitions
- terminal states cannot reopen
- candidate cannot skip confirmation/live validation and become active directly
- self-tests for score arithmetic, veto semantics and transition rules

Rule score remains a rule score; this phase introduces no mapping from score to success probability.

MetaEditor/runtime proof remains pending Phase 8.
