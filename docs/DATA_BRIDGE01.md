# CLOUD DATA BRIDGE 01

Purpose: move immutable canonical XFBAR research datasets from the local canonical RAW database into cloud storage without putting large market files into normal Git history.

## Source of truth

Canonical local source:

D:\AHexaTrader\1DataFiles\raw

Data Bridge 01 never creates or reads a TEMP/AppData RAW mirror.

## Storage model

Source code, contracts, manifests and research results stay in GitHub.

Large market-data packages are published as GitHub Release assets under immutable dataset tags:

dataset-<dataset_id in lowercase>

The pilot uses GitHub Releases because they are outside normal Git object history and can be downloaded directly by GitHub Actions. The storage provider can be replaced later without changing the dataset manifest or verifier contract.

## Dataset identity

Dataset identity is content-based.

For every selected symbol and required timeframe the packer records:

- symbol
- timeframe
- byte size
- SHA256
- XFBAR period
- digits and point
- bar count
- first timestamp
- last timestamp

The sorted content records and symbol status rows are hashed into:

DRUMMOND_CANONICAL_<16 hex chars>

Changing any included market file changes the dataset ID.

## Required research timeframes

Factory 01 requires:

- H1
- H4
- M5

Missing files are never fabricated.

The packer records per-symbol status such as READY, SKIP_NO_M5, SKIP_NO_H1 or SKIP_NO_H4.

## Shards

Files are grouped deterministically into ZIP_STORED shards. A BIN file is never split.

Default pilot shard target:

400 MB

Each shard has its own SHA256 and byte count in DATASET_MANIFEST.json.

ZIP_STORED is deliberate: the canonical BIN bytes remain directly verifiable and packaging does not spend CPU trying to compress already compact binary time-series data.

## Local producer

scripts/data_bridge_pack01.py

Reads only the canonical RAW root and writes runtime packages under:

bridge_out/<DATASET_ID>/

bridge_out is ignored by Git.

Generated assets:

- DATASET_MANIFEST.json
- DATASET_MANIFEST.csv
- DATASET_SYMBOLS.csv
- shard_001.zip
- shard_002.zip
- ...

scripts/publish-data-bridge01.ps1 and publish-data-bridge01.bat:

1. build the canonical package;
2. create or reuse the immutable GitHub Release tag;
3. upload only missing assets without overwriting existing assets;
4. trigger the cloud data-bridge01.yml workflow.

## Cloud consumer

.github/workflows/data-bridge01.yml

The workflow:

1. downloads release assets;
2. recomputes and verifies dataset identity;
3. verifies every shard SHA256 and size;
4. verifies every archive member SHA256;
5. validates each XFBAR header and timeframe contract;
6. extracts only verified members into a cloud workspace;
7. runs Cloud Factory 01;
8. runs a separate frozen XAUUSD anchor replay through 2026-08-26T08:00:00Z whenever XAUUSD is present;
9. requires that frozen slice to remain at 509 signals and SHA256 8411a05a1ca5a4a771c74e3e87d37d2562b370681258ec4b246fa3818f29cd40;
10. publishes full-current Factory results plus the frozen anchor result as Actions artifacts.

This separation is intentional. Canonical RAW can gain new bars after the validated historical horizon. The full-current Factory run may therefore gain new decisions/signals without constituting historical logic drift.

## Pilot configuration

config/DATA_BRIDGE01.json currently selects:

- XAUUSD
- EURUSD
- USDCHF
- BTCUSDT
- DOGEUSDT
- AAPL
- A
- ADAUSDT

The list intentionally spans metals, FX, crypto and equities. Missing required timeframes are reported rather than synthesized.

## CI contract

tests/data-bridge01-contract.ps1 performs a complete fixture-only cycle:

XAUUSD fixture -> pack -> shard -> hash verification -> extraction -> Cloud Factory 01

Acceptance requires:

- valid immutable dataset ID;
- all 3 XAUUSD files verified;
- Factory 01 PASS;
- full verified Factory PASS;
- frozen XAUUSD slice ending at 2026-08-26T08:00:00Z contains 509 signals;
- frozen slice signal SHA256 unchanged.

## Boundary

Data Bridge 01 is data transport and integrity infrastructure. It does not modify trading rules, optimize parameters or substitute broker data for canonical research data.

After the pilot release passes in GitHub Actions, the same architecture can scale to larger symbol sets and later to shard-parallel execution if the complete dataset no longer fits comfortably on one hosted runner.

## Real pilot result

First real canonical pilot dataset:

- DATASET_ID: DRUMMOND_CANONICAL_649F9CB77BB7E0FE
- Release tag: dataset-drummond_canonical_649f9cb77bb7e0fe
- Verified files: 22
- Shards: 1
- Shard bytes: 264,605,531
- Selected symbols: 8
- READY / processed: 6
- SKIP_NO_M5: 0
- SKIP_NO_H1: BTCUSDT, ADAUSDT
- Errors: 0
- Factory decisions: 232,737
- Factory signals: 2,544
- Static outcomes TP/SL/AMBIGUOUS/OPEN: 1,142/1,394/8/0
- Frozen XAUUSD historical anchor: PASS
- GitHub Actions run: 35901098813
- Result: DATA BRIDGE 01 PILOT PASS

The pilot proves the transport/integrity architecture on real canonical multi-symbol data. The next block upgrades Factory outcomes from static first-touch to the validated Executor structural-trailing lifecycle model.
