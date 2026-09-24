# DRUMMOND CLOUD — DATA CONTRACT
Canonical local RAW root:
D:\AHexaTrader\1DataFiles\raw
Canonical structure:
raw\<SYMBOL>\<SYMBOL>_<TF>.bin
Market files:
XFBAR001 binary format.
Rules:
1. Production/research market data must be read only from the canonical RAW source.
2. Do not create RAW mirrors in TEMP or AppData.
3. Small fixtures may exist under data\fixtures only for automated tests.
4. Cloud/local execution must select RAW_ROOT through configuration.
5. Source code must not depend on one hardcoded machine path.
