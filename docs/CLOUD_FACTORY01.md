# CLOUD FACTORY 01

Purpose: convert the proven single-symbol Drummond replay into a repeatable multi-symbol research runner.

## Scope

CLOUD FACTORY 01 is the orchestration layer. It does not change Drummond trading rules.

For each symbol directory it requires:

- <SYMBOL>_H1.bin
- <SYMBOL>_H4.bin
- <SYMBOL>_M5.bin

It invokes the already validated Replay 01 logic with the requested direction/RR/buffer parameters and aggregates per-symbol plus pooled counts.

## Missing-data policy

Missing M5 is explicitly non-fatal:

- status = SKIP_NO_M5
- the symbol is counted as skipped
- the factory run continues

Missing H1/H4 is also reported separately. Malformed market data or replay contract violations are errors.

The runner creates no TEMP/AppData RAW mirror. The caller supplies the data root. Canonical production research remains rooted at:

D:\AHexaTrader\1DataFiles\raw

## Outputs

- FACTORY01_SYMBOLS.csv
- FACTORY01_SUMMARY.json
- FACTORY01_SUMMARY.txt
- per-symbol Replay 01 artifacts under symbols/<SYMBOL>/

The summary reports discovered, processed, SKIP_NO_M5, other skipped timeframes, errors, decisions, signals and static M5 first-touch outcomes.

## CI acceptance

The committed test creates a fixture-only two-symbol input:

- XAUUSD with H1/H4/M5 — must be processed
- NO_M5 with only H1/H4 — must be SKIP_NO_M5 without failing the run

For XAUUSD the factory must preserve the frozen Replay 01 signal count and SHA256.

## Boundary

Factory 01 proves multi-symbol orchestration of the validated signal replay. Its outcome column is the existing static M5 SL/TP first-touch baseline; the fully validated structural trailing/lifecycle model will be folded into the factory in the next execution-model block.

MT4 is no longer part of every factory iteration. It remains the external final validation environment for selected research candidates.
