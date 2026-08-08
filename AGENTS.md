# Agent instructions

This repository is governed by `.ai/PROJECT_DIRECTOR.md` and `docs/PROJECT_CONSTITUTION.md`.

When changing MQL5 code:
- keep trading submission isolated to `Execution/ExecutionEngine.mqh`;
- preserve demo-only hard guard;
- use closed-bar information for signals;
- persist identities/state before relying on in-memory caches;
- never label rule scores as probability;
- run `python tools/static_validate.py` before proposing a merge;
- report MetaEditor compilation as NOT VERIFIED unless a real compiler log exists.
