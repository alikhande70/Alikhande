# Source Adoption

The current implementation uses the recovered Alikhande v1.1.0 source as its direct baseline. Ideas from external projects are used only as architecture references unless license-compatible code is explicitly documented.

Baseline behaviors retained include broker-tree symbol discovery, LiteFinance suffix handling, H4/H1/M15/M5 context, timer slicing, spread/ATR gates and alert-only safe defaults. Reliability modules introduced in v1.2 are independent Alikhande implementations and require their own compile/runtime evidence.
