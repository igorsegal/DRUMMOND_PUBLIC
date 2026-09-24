# DRUMMOND CLOUD — NEXT BLOCK

CURRENT:
- DS16 live shadow on MT4 demo VPS
- D20 native lifecycle contract: PASS
- D22 cross-timeframe data integrity: PASS, 522/522
- D23 corrected Further Out = recovered 5/2 + 5/9 family: PASS
- D24 corrected independent native replay: PASS
- D25 Full Drummond continuous state machine: PASS
- D26 X-ray attribution: 7/7 shard calculations PASS; diagnostic aggregate recovered from those successful shard artifacts
- Dataset: DRUMMOND_CANONICAL_8E9A1D784E3893D9

D25:
- 522 symbols
- 18,656,442 trade-variant records
- 6,764,431 state rows
- all 18 predeclared STRICT/PROXY x flow x pyramid variants negative
- positive shard means: 0/7 in all 18 variants
- best pooled variant: PROXY:F3:P0 = -0.18172824 R
- no production promotion

D26 XRAY:
- trading logic changed: NO
- optimization/selection: NO
- all 7 ENTRY_STATE classes are negative in all 18 variants
- all 4 ENTRY_KIND classes are negative in all 18 variants
- LONG and SHORT are negative in all 18 variants
- in best variant PROXY:F3:P0:
  - LONG = -0.135711 R
  - SHORT = -0.226153 R

KEY DIAGNOSTIC:
The strongest separation is not an entry-state label. It is whether a trade subsequently reaches a valid Live PLDot Refresh while the position is still alive.

STRICT P1, Congestion Action trades that later reached the Live-PLDot refresh/pyramid event:
- F1: N=13,663, mean R about +0.08624, positive years 19/20
- F2: N=15,650, mean R about +0.12536, positive years 19/20
- F3: N=15,804, mean R about +0.13215, positive years 19/20

STRICT F3 P1, Congestion Action trades that did NOT reach that later refresh:
- N=512,201
- mean R about -0.22568
- positive years 1/20

CRITICAL CAUSALITY RULE:
PYRAMIDED=Y is an ex-post diagnostic label. It MUST NOT be used as a historical entry filter because the later refresh is unknown at the original entry time.

NEXT:
D27 — CAUSAL REFRESH ENTRY.
Do not enter the Congestion Action trade at the earlier boundary signal.
Keep observing causally.
If and only if a valid Live PLDot Refresh actually appears while the Drummond state/HTP context remains valid, open the first position at that refresh event.
Compare this delayed first-entry lifecycle against the frozen D25 baseline.
No look-ahead, no OOS selection, no threshold fitting, no future-event filtering.
