#!/usr/bin/env python3
from pathlib import Path
import re, sys

root=Path("ND01")
ea=(root/"ND01.mq4").read_text(encoding="utf-8")
core=(root/"ND01.mqh").read_text(encoding="utf-8")
readme=(root/"README_RU.txt").read_text(encoding="utf-8")

pairs=[
"AUDCAD","AUDCHF","AUDJPY","AUDNZD","AUDUSD",
"CADCHF","CADJPY","CHFJPY",
"EURAUD","EURCAD","EURCHF","EURGBP","EURJPY","EURNZD","EURUSD",
"GBPAUD","GBPCAD","GBPCHF","GBPJPY","GBPNZD","GBPUSD",
"NZDCAD","NZDCHF","NZDJPY","NZDUSD",
"USDCAD","USDCHF","USDJPY"
]
currencies=["AUD","CAD","CHF","EUR","GBP","JPY","NZD","USD"]

checks=[]
def ok(name,cond):
    checks.append((name,bool(cond)))
    print(("[OK]   " if cond else "[FAIL] ")+name)

ok("28 canonical pairs constant", "#define ND01_PAIR_COUNT 28" in core)
ok("8 currencies constant", "#define ND01_CUR_COUNT   8" in core)
ok("24h M5 volatility = 288", "#define ND01_VOL_BARS    288" in core)
ok("all 28 pair names present once", all(core.count(f'"{p}"')==1 for p in pairs))
ok("all 8 currencies present", all(f'"{c}"' in core for c in currencies))
ok("target dislocation uses six thirds", "if(n!=6)" in core)
ok("target excluded external construction", "third==base || third==quote" in core)
ok("30m move", "alignedEventServerTime+1800" in core)
ok("sqrt(6) normalization", "MathSqrt(6.0)" in core)
ok("default threshold 2 sigma", re.search(r"InpDislocationSigma\s*=\s*2\.0",ea))
ok("default decision delay 30m", re.search(r"InpDecisionDelayMinutes\s*=\s*30",ea))
ok("default signal only", "InpMode                  = ND_MODE_SIGNAL_ONLY" in ea)
ok("real account blocked by default", "InpAllowRealAccount      = false" in ea)
ok("demo gate checks IsDemo", "!IsDemo() && !InpAllowRealAccount" in ea)
ok("one position per symbol", "ND01_HasOpenPosition" in ea)
ok("timer-driven multi-symbol architecture", "EventSetTimer(10)" in ea and "void OnTimer()" in ea)
ok("common-files news input", "FILE_COMMON" in ea and "NEWS.csv" in ea)
ok("high-impact only", 'if(impact!="HIGH")' in ea)
ok("cluster de-duplication key", "NDT01_"+"" in ea and "GlobalVariableCheck(key)" in ea)
ok("30/90 research hold warning", "InpHoldMinutes!=30 && InpHoldMinutes!=90" in ea)
ok("manual smoke available", "InpManualSmoke" in ea and "MANUAL_SMOKE" in ea)
ok("actual forecast not required", "Actual / Forecast / Previous" in readme)

failed=[n for n,v in checks if not v]
print(f"Tests: {len(checks)}  Failed: {len(failed)}")
if failed:
    print("FAILED:",failed)
    sys.exit(1)
print("ND01 STATIC PASS")
