# Phase 2 Evidence — Zone & Signal Semantics

Status: **PASS_STATIC**

Implemented:
- typed supply/demand zone domain (`AS_TypedZone`)
- explicit BELOW / INSIDE / ABOVE / UNAVAILABLE price-to-zone relation
- structural candidate object independent from live quote state
- per-pass live validator that derives current entry, structural stop and minimum 2R target from the current quote
- explicit vetoes for stale quote, invalid anchor, unavailable zone, price outside anchor and invalid structural stop
- self-tests covering lower boundary, inside, upper boundary, above/below, broken zones and quote movement with unchanged candidate identity

The original `NearestZones()` defect is no longer part of the v1.3 semantics: an inside-zone price is a first-class direct interaction rather than an accidental edge case.

MetaEditor compile/runtime proof remains pending Phase 8.
