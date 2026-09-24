# CLOUD DATA BRIDGE SCALE 02

Purpose: scale the proven Data Bridge 01 transport from a small pilot to tens/hundreds of canonical symbols without splitting one symbol across multiple shards.

## Key change

Data Bridge 01 packed files in symbol/TF order and prevented splitting an individual file, but a symbol's H1/H4/M5 set could theoretically cross a shard boundary.

Scale 02 makes sharding **symbol-atomic**:

- all available H1/H4/M5 files for one symbol are assigned to exactly one shard;
- a symbol group larger than the nominal shard target remains intact and is marked `oversize_symbol_group=true`;
- the verifier rejects any manifest that assigns one symbol to multiple shards.

## Automatic canonical discovery

`data_bridge_pack02.py` supports `mode=discover`.

The scale pilot configuration:

`config/DATA_BRIDGE02.json`

selects:

- XAUUSD always;
- up to 50 READY canonical symbols discovered deterministically;
- up to 5 incomplete symbols so skip paths remain exercised;
- target shard size 400 MB.

The canonical source remains:

`D:\AHexaTrader\1DataFiles\raw`

No TEMP/AppData RAW mirror is created.

## Parallel cloud execution

`.github/workflows/data-bridge02.yml` uses three stages:

1. **prepare** — download/verify only manifests and build a dynamic shard matrix;
2. **factory-shard** — each shard is downloaded, verified and processed independently in parallel;
3. **aggregate** — all shard Factory results are combined into one dataset-level summary.

Each shard job independently validates release shard size/SHA256, archive members, member SHA256, XFBAR headers, symbol atomicity and Cloud Factory output.

If the shard contains XAUUSD, it also runs the frozen 2026-08-26 anchor and requires the frozen 509-signal SHA256.

## Aggregation contract

`cloud_factory_aggregate02.py` rejects duplicate symbols across shard results, requires every READY symbol to be processed, preserves declared skip status for incomplete symbols, requires all expected shard results, and aggregates decisions, signals and static outcomes.

## CI

`tests/data-bridge02-contract.ps1` deliberately sets a 1 MB target against the much larger XAUUSD symbol group.

Acceptance proves automatic discovery, symbol-atomic sharding, oversize-group marking, manifest validation, shard-only verification, Cloud Factory execution, aggregation and the frozen 509-signal anchor.

## Next real gate

After the Scale 02 contract is green, publish the 50-READY-symbol pilot from canonical RAW with:

`scripts/publish-data-bridge02.bat`

No MT4 test is required.
