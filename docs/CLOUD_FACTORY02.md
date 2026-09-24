# CLOUD FACTORY 02

Purpose: promote the cloud factory from static first-touch outcomes to the validated production-like Executor lifecycle model.

## Input

Factory 02 consumes verified canonical XFBAR directories containing:

- <SYMBOL>_H1.bin
- <SYMBOL>_H4.bin
- <SYMBOL>_M5.bin

Signal generation remains Drummond Replay 01. No signal rule is changed.

## Lifecycle model

For each accepted signal:

1. entry occurs at signal CREATED_AT / M5 open;
2. the position becomes eligible for lifecycle processing from the following M5 bar, matching the validated MT4 capture;
3. the existing stop/target is checked for an open gap;
4. Executor-style structural trailing is recomputed at the M5 open from the current H1 state;
5. only a tighter and geometrically valid structural stop is adopted;
6. the remaining M5 bar range is checked for TP/SL;
7. range-trigger close time is the bar completion / next M5 timestamp (+300 seconds);
8. if TP and SL are both inside the same modeled M5 range, the result is AMBIGUOUS_SAME_M5 and is never guessed;
9. unresolved positions remain OPEN_AT_DATA_END.

## Broker boundary

The cloud model intentionally does not invent:

- broker stop level;
- freeze level;
- OrderModify rejection;
- slippage beyond the XFBAR spread model;
- broker margin/account state.

For research, a deterministic tighter structural stop is assumed accepted. Selected candidates are still validated in MT4.

## Research outputs

Per signal:

- close reason and time;
- close level;
- final stop;
- number of structural trail updates;
- M5 bars to outcome;
- level-based R multiple.

Per symbol:

- signals;
- TP / SL / ambiguous / open;
- trail update count;
- TP rate among resolved TP/SL outcomes;
- mean level-based R;
- reproducibility SHA256 for the lifecycle rows.

Factory-wide pooled statistics are emitted in FACTORY02_SUMMARY.json/txt and FACTORY02_SYMBOLS.csv.

## Relationship to Factory 01

Factory 01 remains useful as a static SL/TP first-touch diagnostic baseline.

Factory 02 is the production-like research outcome engine and should be used for candidate evaluation once its contracts pass.

## Real canonical pilot

Dataset: DRUMMOND_CANONICAL_649F9CB77BB7E0FE

Result:

- discovered: 8
- processed: 6
- skipped for other required timeframe: 2
- errors: 0
- signals: 2,544
- TP / SL / ambiguous / open: 740 / 1,798 / 6 / 0
- structural trail updates: 3,586
- TP rate resolved: 0.291568
- mean level-R resolved: -0.051916
- XAUUSD lifecycle SHA256 remained exactly equal to the frozen fixture baseline
- GitHub Actions run: 35902624278
- result: PASS

This result is intentionally descriptive rather than a parameter-selection verdict. The next research block slices the fixed rule by symbol and year before any optimization is allowed.
