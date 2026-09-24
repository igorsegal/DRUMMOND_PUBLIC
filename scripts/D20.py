#!/usr/bin/env python3
import json
from pathlib import Path

P=Path("config/D20.json")
s=json.loads(P.read_text(encoding="utf-8"))

def need(c,m):
    if not c: raise SystemExit("D20 FAIL: "+m)

need(s["schema"]=="D20_NATIVE_DRUMMOND_LIFECYCLE","schema")
need(s["state"]=="FROZEN_RESEARCH_CONTRACT","state")
need(s["timeframe_contract"]=={
    "ltp":"H1","htp":"H4","intrabar":"M5",
    "note":"Fixed hierarchy for this experiment; no opportunistic timeframe switching."
},"timeframes")
ids=[x["id"] for x in s["setup_families"]]
need(ids==["TR","CA","EX","CX","WB"],"setup families")
for x in s["setup_families"]:
    need(x["source_status"]=="SOURCE_RECOVERED",f"{x['id']} source status")
    need(x["trigger"] and x["initial_stop"],f"{x['id']} incomplete")
m=s["management"]
need(m["stop"]["rule"].startswith("Stop beyond current-period Further Out"),"stop")
need("Nearby HTP" in m["target"]["rule"] and "Further Out HTP" in m["target"]["rule"],"target")
need(m["flow_exit"]["operationalizations_to_test_without_selection"]==["FLOW_1BAR","FLOW_2BAR","FLOW_3BAR"],"flow variants")
need(m["pyramiding"]["fixed_research_caps"]==[0,1,2],"pyramid caps")
p=s["operationalization_policy"]
need(p["no_oos_selection"] and p["no_parameter_optimization"],"anti-fit")
need(p["source_gap_excluded_from_entry_exit"],"source-gap exclusion")
need(len(s["source_gaps"])>=5,"source gaps")
for token in ["Factory02 signal IDs as entry triggers","Factory02 initial stop","Factory02 target","Factory02 structural trailing"]:
    need(token in s["forbidden"],"missing forbidden "+token)
need(not s["promotion_allowed"],"promotion must remain false")

print("D20 PASS")
print("SETUPS:",",".join(ids))
print("LIFECYCLE: NATIVE_DRUMMOND_ONLY")
print("FLOW VARIANTS: 1/2/3 BAR")
print("PYRAMID CAPS: 0/1/2")
print("OOS SELECTION: FORBIDDEN")
print("SOURCE GAP AS GATE: FORBIDDEN")
print("FACTORY02 LIFECYCLE: FORBIDDEN")
