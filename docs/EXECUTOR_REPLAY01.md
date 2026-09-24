# DRUMMOND EXECUTOR REPLAY 01

Purpose: replay the deterministic part of the production MT4 Executor in GitHub against the frozen MT4 runtime evidence.

## Frozen evidence

- XAUUSD
- 29 Watcher queue signals
- 107 Executor audit rows
- 29 CLAIMED
- 29 ORDER_OPENED
- 0 ORDER_REJECTED
- 0 BLOCKED
- 49 TRAIL_UPDATED
- 0 architecture violations

## Cloud replay scope

The replay independently recomputes:

- signal timing and age;
- H1-open execution price with the fixed 20-point tester spread;
- spread/risk gate;
- entry-drift/risk gate;
- long/short geometry;
- current RR gate;
- exact structural trailing candidate from MT4 H1 HST;
- trail geometry and tighter-than-old-stop rule.

Broker-specific mechanics are intentionally not invented. Stop/freeze-level acceptance, projected margin mechanics and actual OrderSend/OrderModify acceptance remain captured MT4 evidence.

## Result

- deterministic entry gates: 29/29 PASS
- exact entry price: 29/29
- runtime opened/rejected/blocked: 29/0/0
- exact structural trail candidate: 49/49
- trail geometry: 49/49
- tighter-than-old-stop: 49/49
- mismatches: 0

Result: DRUMMOND EXECUTOR REPLAY 01 PASS.
