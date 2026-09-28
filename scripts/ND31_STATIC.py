#!/usr/bin/env python3
from pathlib import Path
import re

p=Path("ND31/ND31.mq4")
s=p.read_text(encoding="utf-8")

checks={
 "strict": "#property strict" in s,
 "demo_only": "if(!IsDemo())" in s,
 "inst_n_44": "#define INST_N 44" in s,
 "sigma_2": "input double InpSigma=2.0;" in s,
 "delay_30": "input int    InpDelayMin=30;" in s,
 "hold_30": "input int    InpHoldMin=30;" in s,
 "margin_5000": "input double InpMinMarginLevelPct=5000.0;" in s,
 "magic_nd31": "InpMagic=26092831" in s,
 "telemetry_common_file": 'InpTelemetryFile="ND31_EXECUTION.csv"' in s,
 "order_opened_log": '"ORDER_OPENED"' in s,
 "order_closed_log": '"ORDER_CLOSED"' in s,
 "order_failed_log": '"ORDER_FAILED"' in s,
 "margin_block_log": '"MARGIN_BLOCKED"' in s,
 "free_margin_block_log": '"FREE_MARGIN_BLOCKED"' in s,
 "position_block_log": '"POSITION_BLOCKED"' in s,
 "symbol_ready_log": '"SYMBOL_READY"' in s,
 "symbol_missing_log": '"SYMBOL_MISSING"' in s,
 "no_signal_log": '"NO_SIGNAL"' in s,
 "file_common": "FILE_COMMON" in s,
 "flush": "FileFlush(h);" in s,
 "balanced_braces": s.count("{")==s.count("}"),
}

m=re.search(r'string INST\[INST_N\]=\{(.*?)\};',s,re.S)
if not m:
    checks["instrument_array_found"]=False
else:
    vals=re.findall(r'"([^"]+)"',m.group(1))
    checks["instrument_array_found"]=True
    checks["instrument_count_44"]=len(vals)==44 and len(set(vals))==44

for k,v in checks.items():
    print(("[PASS] " if v else "[FAIL] ")+k)
if not all(checks.values()):
    raise SystemExit("ND31 STATIC FAIL")
print("ND31 STATIC PASS")
