ND30 — DEMO multi-symbol trader

Purpose
-------
One mode only: if ND30 signal exists, the EA attempts a real DEMO order.

Frozen signal family
--------------------
High Impact news
Decision = event + 30 minutes
Threshold = |D| >= 2.0
Hold = 30 minutes
One open ND30 position per symbol
New-entry margin-level gate = 5000%

44 broker symbols are embedded directly in ND30.mq4.
There is no MAP.csv.

FX pairs
--------
28 canonical FX crosses use the full two-currency external dislocation.

One-sided instruments
---------------------
USD driver:
XAUUSD XAGUSD BTCUSD ETHUSD SOLUSD DOGEUSD ADAUSD XRPUSD
.US500Cash .USTECHCash .US30Cash BRENT WTI

EUR driver:
XAUEUR .DE40Cash

JPY driver:
.JP225Cash

Safety
------
Hard DEMO-only initialization. ND30 refuses to start on a real account.
No SL/TP in this research-forward build; exit is time-based after 30 minutes.

Files
-----
ND30.mq4 -> MQL4\Experts\ND30\
NEWS.csv -> Terminal\Common\Files\NEWS.csv

NEWS.csv format
---------------
UTC_TIME;CURRENCY;IMPACT;EVENT
2026-09-28T12:30:00Z;USD;HIGH;Example

The file must contain UTC scheduled time only. Actual/Forecast/Previous are not used.

First launch
------------
Attach ND30 to ONE liquid chart, M5 recommended.
AutoTrading ON.
Check Experts log:
ND30 DEMO START
instruments=44
NEWS clusters=...
