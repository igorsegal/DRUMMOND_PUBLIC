# EXECUTOR LIFECYCLE 02

Purpose: extend the proven Executor entry/trailing equivalence to ticket-level trade closure.

## EQ02 evidence

DrummondExecutor_EQ02.mq4 keeps the EQ01 trading functions unchanged and adds lifecycle-only instrumentation:

- OPEN lifecycle event immediately after successful OrderSend;
- CLOSE lifecycle event when the ticket appears in MT4 account history;
- open/close time and price;
- final SL and TP;
- lots, profit, swap and commission;
- close reason classified as TP, SL or OTHER.

The source contract verifies that EnvironmentOK, ValidateFreshSignal, ReadQueueAndExecute and TrailAllOurPositions remain byte-for-byte identical to EQ01.

## Exact data contract

The run used the same broker MT4 installation selected by the earlier HST equivalence work and captured its exact XAUUSD5.hst. Canonical XFBAR M5 was not substituted.

Frozen tester contract:

- Expert: DrummondExecutor_EQ02
- Symbol: XAUUSD
- Period: M5
- Model: Open prices only
- Use Date: 2026-01-01 through 2026-08-27
- Spread: 20 points
- Run mode: hard-fixed TESTER
- Queue: the same 29 signals already validated in EXECUTOR CAPTURE 01

## Important MT4 timing discovery

The initial lifecycle replay assumed that Open prices only also meant SL/TP could be tested only at M5 opens. The real evidence disproved that assumption.

Observed MT4 semantics for this run:

1. the EA is called on M5 opens;
2. tester-managed SL/TP may be reached by the M5 bar high/low range;
3. for a range-triggered stop/target, MT4 records the close at the completion of that modeled M5 bar / next M5 timestamp, exactly 300 seconds after the HST bar-open stamp;
4. 28 normal closes were filled exactly at their SL/TP trigger level;
5. the final OTHER close occurred at the end of the test; EQ02 has no OrderClose path, so it is classified as Strategy Tester forced end-of-test liquidation.

The corrected cloud replay applies proven trail updates at bar open, evaluates the remaining M5 range, and timestamps a range-triggered close at bar completion. It never consumes a full bar range beyond the actual test horizon.

## Result

- opened tickets: 29
- lifecycle OPEN events: 29
- lifecycle CLOSE events: 29
- matched closes: 29/29
- SL: 13
- TP: 15
- forced test-end close: 1
- ambiguous SL/TP-in-same-bar cases: 0
- normal fills at trigger level: 28/28
- mismatches: 0

Result: EXECUTOR LIFECYCLE 02 PASS.

## Meaning

The equivalence chain now covers Drummond decision generation, deterministic Executor entry validation, structural trailing and ticket-level TP/SL lifecycle. Routine research can move to the cloud replay; MT4 remains the final external validation environment rather than the engine for every experiment.
