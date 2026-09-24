# DRUMMOND REPLAY 01

## Purpose

DRUMMOND REPLAY 01 is the first causal historical replay engine for the current DRUMMOND_TRADER_DEMO_02_FIX2 signal logic. It runs in GitHub Actions against the checked-in XAUUSD XFBAR fixtures:

- XAUUSD_H4.bin — higher-timeframe context
- XAUUSD_H1.bin — decision timeframe
- XAUUSD_M5.bin — causal quote/execution clock

## XFBAR contract

Replay 01 decodes the supplied XFBAR format as:

- fixed header: magic[8], version(int32), record_size(int32), period_seconds(int32), digits(int32), point(double), bar_count(int64), first_time(int64), last_time(int64), symbol_len(int32)
- symbol bytes immediately after the fixed header
- packed 60-byte bars: time, open, high, low, close, tick_volume, spread, real_volume

The fixed header fields sum to 60 bytes. For XAUUSD the 6-byte symbol places the first bar at byte 66.

Replay fails closed on malformed magic/version/record size/file size/time ordering/OHLC/header timestamps/symbol/timeframe/digits/point.

## Causal clock

On each H1 open, Replay 01 evaluates the previously closed H1 bar as shift=1. H4 values are also restricted to closed bars. The M5 bar at the H1 open supplies only the quote open and recorded spread to the signal decision. Future M5 high/low/close are not available to signal generation.

The future_guard_violations counter must remain zero.

## Drummond gates

Replay 01 ports the 12 Watcher gates from DT02_Common.mqh:

- 3-bar PLdot trend on H1
- 3-bar PLdot trend on H4
- H1/H4 direction agreement
- closed-bar PLdot refresh
- 5-1, 5-2 and 5-9 structural lines
- H4 target
- H1 structural protection with one-point buffer
- direction gate
- RR gate

Defaults match the current Watcher: H1 decision, H4 higher timeframe, SHORT_ONLY, RR 0.75 to 1.75 exclusive, one-point protection buffer.

## M5 outcome

For every queued signal, Replay 01 records a static first-touch SL/TP outcome on M5. If both SL and TP lie inside one M5 candle, the result is AMBIGUOUS_SAME_M5 rather than inventing an intrabar order.

For short positions the M5 bid range is shifted by the recorded spread when testing exits because shorts close on Ask.

## Deliberate boundary

Replay 01 reproduces the Watcher signal engine and a static market outcome. It does not yet emulate broker account state, minimum lot, margin, stop/freeze levels, OrderSend rejection, slippage, or the Executor trailing-stop loop.

The next phase is MT4 equivalence over the same XAUUSD interval.

## Outputs

GitHub Actions generates and uploads:

- XAUUSD_REPLAY_AUDIT.csv
- XAUUSD_REPLAY_SIGNALS.csv
- XAUUSD_REPLAY_OUTCOMES.csv
- XAUUSD_REPLAY_SUMMARY.json
- XAUUSD_REPLAY_SUMMARY.txt

Acceptance requires tests/replay01-contract.ps1 PASS.
