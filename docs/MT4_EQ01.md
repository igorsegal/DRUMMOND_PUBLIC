# MT4 EQUIVALENCE 01

Purpose: prove that the production MT4 Watcher and the cloud Drummond replay implement the same decision logic on XAUUSD without changing Drummond rules.

## Fixed MT4 tester contract

- EA: DrummondWatcher_DEMO_02
- Symbol: XAUUSD
- Period: H1
- Model: Open prices only
- Date window: 2018-03-22 through 2026-08-27
- Spread: 20 points
- Inputs: config/MT4_EQ01_XAUUSD.set
- Decision TF: H1
- Higher TF: H4
- Direction: SHORT_ONLY
- RR: 0.75 <= RR < 1.75
- Protection buffer: 1 point
- Tester output is cleared on init

## Phase A — canonical data diagnostic

The first comparison used canonical XFBAR H1/H4 history against MT4 Strategy Tester output.

Result:
- canonical replay decisions: 49,810
- MT4 audit rows in comparator range: 48,824
- replay signals: 509
- MT4 signals: 501
- audit missing/extra: 1,121 / 135
- signal missing/extra: 90 / 82
- total mismatches: 10,927

This is preserved as a deterministic data diagnostic. It is not accepted as a logic-equivalence verdict because the two environments are not using identical history.

A direct common-signal example confirms different source prices:
XAUUSD_1522274400_S
- canonical replay entry/stop/target: 1325.76 / 1330.23 / 1318.87
- MT4 tester entry/stop/target: 1325.74 / 1330.15 / 1318.74

## Phase B — same-data logic proof

The HST bridge reads the exact local MT4 history files:
- XAUUSD60.hst
- XAUUSD240.hst

The Python replay then evaluates the same 12 Watcher gates against MT4's own H1/H4 history and the fixed 20-point spread.

Watcher audit is compared by DECISION_TIME:
STATUS, REASON, GATES_PASSED, GATES_TOTAL, SIDE, SIGNAL_ID, ENTRY_REFERENCE, STOP_PRICE, TARGET_PRICE, RR.

Signal queue is compared by SIGNAL_ID:
SYMBOL, DECISION_TIME, SIDE, ENTRY_REFERENCE, STOP_PRICE, TARGET_PRICE, RR, SIGNAL_NAME, DECISION_TF, HTP_TF.

SERVER_TIME and CREATED_AT are transport timestamps and are not equality fields.

## Acceptance

MT4 HST EQUIVALENCE 01 PASS requires zero same-data mismatches.
Any failure produces a deterministic mismatch CSV/JSON report. Comparison criteria are not weakened to manufacture a PASS.
