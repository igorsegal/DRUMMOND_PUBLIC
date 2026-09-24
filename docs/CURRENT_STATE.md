# DRUMMOND CLOUD — CURRENT STATE

PROJECT:
DRUMMOND CLOUD

STATUS:
BASELINE PASS
DRUMMOND REPLAY 01 PASS
MT4 WATCHER SAME-DATA EQUIVALENCE 01 PASS
MT4 EXECUTOR CAPTURE 01 PASS
DRUMMOND EXECUTOR REPLAY 01 PASS
EXECUTOR LIFECYCLE 02 PASS
CLOUD FACTORY 01 PASS
CLOUD DATA BRIDGE 01 REAL PILOT PASS
CLOUD DATA BRIDGE SCALE 02 CONTRACT PASS

LOCAL ROOT:
D:\AHexaTrader\2026.09.21 DRUMMOND_CLOUD

GITHUB:
igorsegal/DRUMMOND_CLOUD

BRANCH:
main

CANONICAL RAW:
D:\AHexaTrader\1DataFiles\raw

SOURCE:
DRUMMOND_TRADER_DEMO_02_FIX2

SOURCE FILES:
- DrummondExecutor_DEMO_02.mq4
- DrummondWatcher_DEMO_02.mq4
- DT02_Common.mqh

BASELINE FILES:
- DRUMMOND_DEMO02_EXECUTION.csv
- DRUMMOND_DEMO02_SIGNALS.csv
- DRUMMOND_DEMO02_WATCHER.csv

AUTOMATED TESTS:
- .github/workflows/baseline-check.yml
- tests/source-contract.ps1
- tests/state-contract.ps1
- tests/inventory-contract.ps1
- tests/replay01-contract.ps1
- tests/cloud-factory01-contract.ps1
- tests/data-bridge01-contract.ps1
- tests/data-bridge02-contract.ps1

REAL DATA BRIDGE 01 PILOT:
- dataset ID: DRUMMOND_CANONICAL_649F9CB77BB7E0FE
- release tag: dataset-drummond_canonical_649f9cb77bb7e0fe
- release shard: 1
- shard bytes: 264,605,531
- selected symbols: 8
- READY / processed: 6
- skipped for missing required TF: 2
- errors: 0
- verified files: 22
- decisions: 232,737
- signals: 2,544
- static outcomes TP/SL/AMBIGUOUS/OPEN: 1,142 / 1,394 / 8 / 0
- XAUUSD frozen anchor: 49,801 decisions / 509 signals
- XAUUSD frozen SHA256: 8411a05a1ca5a4a771c74e3e87d37d2562b370681258ec4b246fa3818f29cd40
- workflow run: 35901098813
- RESULT: PASS

REAL PILOT SYMBOL STATUS:
- XAUUSD: PROCESSED, 49,801 decisions, 509 signals
- EURUSD: PROCESSED, 54,962 decisions, 595 signals
- USDCHF: PROCESSED, 54,978 decisions, 667 signals
- DOGEUSDT: PROCESSED, 53,773 decisions, 615 signals
- AAPL: PROCESSED, 18,733 decisions, 155 signals
- A: PROCESSED, 490 decisions, 3 signals
- BTCUSDT: SKIP_NO_H1
- ADAUSDT: SKIP_NO_H1

CURRENT ARCHITECTURE:
Watcher -> SIGNALS queue -> Executor -> EXECUTION audit

PROVEN CLOUD CHAIN:
canonical XFBAR -> content-addressed dataset -> immutable Release assets -> byte/header verification -> verified cloud workspace -> Cloud Factory -> frozen historical anchor

IMPORTANT DATA RULE:
Canonical XFBAR remains D:\AHexaTrader\1DataFiles\raw.
Never create or use TEMP/AppData RAW mirrors.
Large market-data packages live outside normal Git history.
Missing required timeframes are reported, never fabricated.

MT4 STATUS:
Routine MT4 equivalence work is complete for the validated Watcher/Executor/lifecycle chain.
MT4 remains a final external validation gate for selected research candidates.

CLOUD DATA BRIDGE SCALE 02:
- automatic canonical symbol discovery: PASS
- symbol-atomic H1/H4/M5 sharding: PASS
- oversize single-symbol groups remain intact: PASS
- manifest-only verification: PASS
- shard-only verification/extraction: PASS
- per-shard Factory execution: PASS
- dataset-level aggregation: PASS
- frozen XAUUSD anchor: PASS
- contract dataset: DRUMMOND_CANONICAL_3A5C5E341395F1BE
- contract shard coverage: 1/1
- contract signals: 509
- workflow run: 35909340132
- RESULT: PASS

NEXT:
DATA BRIDGE SCALE 02 REAL RELEASE — publish the auto-discovered 50 READY symbol pilot from canonical RAW and let data-bridge02.yml verify/process shards in parallel. No MT4 test is required.

RULE FOR FUTURE WORK:
Before modifying production source, preserve the current passing baseline.
After every meaningful change:
1. run tests
2. commit
3. push
4. require GitHub Actions PASS
5. update CURRENT_STATE.md
