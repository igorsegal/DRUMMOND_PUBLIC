#!/usr/bin/env python3
from pathlib import Path
import re,sys

root=Path("ND02")
ea=(root/"ND02.mq4").read_text(encoding="utf-8")
core=(root/"ND02.mqh").read_text(encoding="utf-8")
rd=(root/"README.txt").read_text(encoding="utf-8")

checks=[]
def ck(name,cond):
    checks.append((name,bool(cond)))
    print(("[OK]   " if cond else "[FAIL] ")+name)

ck("28-pair core", "#define ND02_PAIR_COUNT 28" in core)
ck("M5 24h volatility 288", "#define ND02_VOL_BARS    288" in core)
ck("tester-only gate", "IsTesting()" in ea and "InpAllowOutsideTester=false" in ea)
ck("real OrderSend present", "OrderSend(" in ea)
ck("real OrderClose present", "OrderClose(" in ea)
ck("orders enabled default", "InpTrade=true" in ea)
ck("NEWS26 default", 'InpNewsFile="NEWS26.csv"' in ea)
ck("frozen sigma 2", "InpDislocationSigma=2.0" in ea)
ck("frozen delay 30", "InpDecisionDelayMinutes=30" in ea)
ck("hold default 90", "InpHoldMinutes=90" in ea)
ck("OnTick tester path", "void OnTick()" in ea and "ND02_ProcessNews();" in ea)
ck("target pair only trading", "Symbol(),type" in ea)
ck("all 28 required", "found<ND02_PAIR_COUNT" in ea)
ck("target excluded via six thirds", "if(n!=6)" in core)
ck("server-time core", "ND02_BuildZVectorServer" in core)
ck("EU DST translation", "ND02_LastSunday0100Utc" in ea)
ck("winter offset 2", "InpUtcWinterOffsetHours=2" in ea)
ck("summer offset 3", "InpUtcSummerOffsetHours=3" in ea)
ck("one position gate", "ND02_HasPosition()" in ea)
ck("no SL TP", "OrderSend(Symbol(),type,ND02_Lots(),px,InpSlippagePoints,0,0" in ea)
ck("MT4 single-symbol limitation documented", "односивольным" in rd)

fail=[n for n,v in checks if not v]
print("Tests:",len(checks),"Failed:",len(fail))
if fail:
    print(fail)
    sys.exit(1)
print("ND02 STATIC PASS")
