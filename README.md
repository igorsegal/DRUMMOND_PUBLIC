# DRUMMOND_PUBLIC

Public research and engineering repository for the Drummond trading-system reconstruction and validation project.

## What is public here

- research engines and diagnostics;
- MT4/MQL4 Author Engine source;
- causal / walk-forward research code;
- reproducibility and data-integrity tooling;
- documentation of hypotheses, failures and results.

## What is deliberately NOT public

This repository does **not** contain broker/vendor historical market databases, XFBAR BIN files, HST files, or the private dataset Release assets used by the canonical research environment.

The canonical data repository remains private. Public cloud workflows can consume it only through an explicitly configured read-only repository secret.

See `DATA_NOTICE.md` and `docs/PUBLIC_AUDIT.md`.

## Current research state

The integrated Full Drummond state machine (D25) was negative across all 18 predeclared variants. D26 attribution identified a causal hypothesis: a Congestion Action setup should not open a position immediately; the first entry should wait for an actually observed same-direction Trend confirmation and Live PLDot Refresh.

D27 tests that hypothesis without look-ahead, future-event filtering, parameter fitting, or pyramiding.

## License

Original software code is licensed under GNU GPLv3. Third-party market data and other third-party material are not relicensed by this repository.

## Research warning

Historical/simulated results are research evidence, not a promise of future performance and not financial advice.
