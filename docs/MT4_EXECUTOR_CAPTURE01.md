# MT4 EXECUTOR CAPTURE 01

Purpose: validate the production Executor queue-processing architecture on a frozen XAUUSD signal set before porting broker-dependent execution into the cloud replay.

## Frozen MT4 tester contract

- EA: DrummondExecutor_DEMO_02
- Symbol: XAUUSD
- Period: M5
- Model: Open prices only
- Use Date: 2026-01-01 through 2026-08-27
- Spread: 20 points
- Inputs: config/MT4_EXEC_EQ01_XAUUSD.set

The preparation script filters the already validated MT4 Watcher queue to this date window and copies it into the exact local tester\files directory selected by the HST equivalence step.

## What is proved in this block

The analyzer checks Executor architecture independently of broker economics:

- every frozen queue signal is processed exactly once to a terminal state;
- terminal state is exactly one of BLOCKED, ORDER_OPENED, ORDER_REJECTED;
- ORDER_OPENED and ORDER_REJECTED must have exactly one prior CLAIMED row;
- BLOCKED signals must not be CLAIMED;
- symbol, decision time, side, SL and TP must remain identical to the Watcher queue;
- ORDER_OPENED must contain a positive ticket and zero error;
- no unknown signal IDs are allowed;
- trailing rows must have an empty SIGNAL_ID and a trailing action;
- non-expired processing must occur within the configured 15-minute signal age.

Broker-dependent values such as lot size, projected margin level, stop/freeze restrictions, OrderSend acceptance and trailing success are recorded, not guessed.

## Local workflow

1. Run scripts/prepare-mt4-executor-eq01.bat.
2. Run the MT4 Strategy Tester once with the frozen contract above.
3. Run scripts/collect-mt4-executor-eq01.bat.

The collector copies the real execution CSV, produces a deterministic PASS/FAIL report, rebuilds the repository inventory, commits the evidence and pushes it to GitHub.

## Acceptance

MT4 EXECUTOR CAPTURE 01 PASS requires zero architecture violations. This is not yet a cloud broker-equivalence proof; it is the evidence package used to build that next layer.
