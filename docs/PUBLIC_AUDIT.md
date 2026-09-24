# PRE-PUBLIC AUDIT — DRUMMOND_CLOUD

Date: 2026-09-24

## Status

**CODE: READY WITH NORMAL PUBLIC-REPOSITORY PRECAUTIONS**

**PUBLICATION BLOCKER: MARKET-DATA RELEASE ASSETS**

Do not switch repository visibility to public until the dataset-release decision below is resolved.

## Repository

- Repository: `igorsegal/DRUMMOND_CLOUD`
- Current visibility: private
- Default branch: `main`
- Commit history inspected at repository level: 339 commits from the initial baseline to current main
- No root license existed before this audit.
- GNU GPLv3 has now been added for original software code.
- `DATA_NOTICE.md` explicitly excludes third-party market data and release assets from the software license.

## Current-tree secret / credential checks

Current tree and representative configuration / execution evidence were inspected.

No obvious committed:
- GitHub PAT (`ghp_`, `github_pat_`)
- private key block
- API key field
- password / credentials file
- `.env`
- PEM / key file
- broker account password

`.gitignore` already excludes:
- `.env`
- `*.key`
- `*.pem`
- `secrets/`
- `credentials/`

The published MT4 `.set` files contain strategy/execution parameters and Magic Number, but no login/password credentials.

Baseline execution CSVs expose research/demo ticket identifiers, prices, lots and projected margin values. They do not expose a broker login or password. This is an information-disclosure choice, not a repository takeover risk.

## GitHub Actions

All current workflow files were inspected for public-fork execution risk.

Observed:
- no `pull_request:` trigger
- no `pull_request_target:` trigger
- no repository-secret references (`secrets.*`)
- no write-level workflow permissions detected
- no self-hosted runner target
- no `Invoke-Expression` / `iex`
- no direct `curl` / `wget` execution
- several research workflows use the ephemeral `GITHUB_TOKEN` only to read/download repository release data

Consequence:
An outsider can fork the repository, but cannot make this repository execute their PR code because current workflows do not trigger on pull requests.

## Branch protection

While the repository is private on the current account tier, the ruleset API reports that the feature requires GitHub Pro or a public repository.
After publication, enable a main-branch ruleset / branch protection:
- block force-push
- block branch deletion
- require pull request for non-owner contributors
- require status checks before merge where practical

## Releases — PUBLICATION BLOCKER

Three dataset releases are attached to this repository:

1. `dataset03-drummond_canonical_8e9a1d784e3893d9`
   - seven raw-market-data shard ZIPs, each roughly 0.65–0.78 GB
2. `dataset02-drummond_canonical_83e5cb949cf19896`
   - two shard ZIPs
3. `dataset-drummond_canonical_649f9cb77bb7e0fe`
   - one shard ZIP

Total release-asset footprint is approximately **6.20 GB decimal / 5.78 GiB**.

These assets are canonical historical market-data packages. Repository documentation describes them as originating from the local canonical RAW database but does not document redistribution rights from the underlying broker/vendor/exchange source.

When this repository becomes public, these release assets become publicly downloadable.

**Required decision before publication:**
- either confirm and document redistribution rights for the dataset, or
- remove/move the dataset releases to private storage before making the code repository public.

## License decision

Original software code: **GNU GPLv3**.

Why:
- public reading/use/modification is allowed;
- redistributed modified software must remain source-available under the same copyleft terms;
- warranty/liability disclaimers are included.

Important:
GPL does not prohibit commercial use. If the goal were to prohibit commercial use entirely, that would require a different source-available/non-open-source license.

Market data and third-party material are explicitly excluded by `DATA_NOTICE.md`.

## Tracked market-data blobs — SECOND PUBLICATION BLOCKER

The current Git tree itself contains broker/market-history binary material:

- `data/fixtures/XAUUSD/XAUUSD_H1.bin` — 2,993,286 bytes
- `data/fixtures/XAUUSD/XAUUSD_H4.bin` — 783,006 bytes
- `data/fixtures/XAUUSD/XAUUSD_M5.bin` — 33,961,146 bytes
- `data/mt4_equivalence01/hst/XAUUSD240.hst` — 2,034,688 bytes
- `data/mt4_equivalence01/hst/XAUUSD60.hst` — 7,727,788 bytes
- `data/mt4_lifecycle02/hst/XAUUSD5.hst` — 89,184,148 bytes

Total currently tracked market-data binaries: approximately **136.7 MB**.

Deleting these files in a new commit is not enough before changing the current repository to public: the old Git blobs remain reachable through repository history unless history is rewritten.

## Recommended publication architecture

**Do not directly switch the existing DRUMMOND_CLOUD repository to public.**

Preferred architecture:

1. Keep `DRUMMOND_CLOUD` private as the canonical research/data repository.
2. Create a new public code repository from a sanitized current snapshot with:
   - source code
   - workflows
   - documentation
   - GPLv3 license
   - synthetic/minimal test fixtures only
   - no broker/vendor market-history blobs
   - no dataset Releases
   - no private Git history
3. Public Actions run in the public code repository.
4. If public cloud workflows need the private canonical dataset, access it with a narrowly scoped read-only credential stored as a GitHub Actions secret; do not expose that secret to fork/PR workflows.

This avoids publishing both historical market-data Releases and market-data blobs already present in Git history.

## Verdict

**CODE SECURITY: PASS WITH NORMAL PUBLIC-REPOSITORY PRECAUTIONS.**

**DIRECT PRIVATE -> PUBLIC CONVERSION OF THIS REPOSITORY: NOT RECOMMENDED.**

Material blockers:
- approximately 6.20 GB of historical market-data Release assets;
- approximately 136.7 MB of tracked BIN/HST market-history files, including historical Git blobs;
- redistribution rights for those market-data materials are not documented.

The safest route is a fresh public code-only mirror while keeping this canonical repository private.
