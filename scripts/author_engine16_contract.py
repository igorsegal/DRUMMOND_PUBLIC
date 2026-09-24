#!/usr/bin/env python3
from pathlib import Path

ROOT=Path("DRUMMOND_TRADER_DEMO_02_FIX2")
AE=ROOT/"AuthorEngine"
WATCHER=ROOT/"DrummondAuthorShadow_16.mq4"

REQUIRED=[
 "AE_Utils.mqh","AE_Dots.mqh","AE_Lines.mqh","AE_State.mqh",
 "AE_Envelope.mqh","AE_Energy.mqh","AE_Congestion.mqh",
 "AE_Filters.mqh","AE_Signals.mqh","AE_TradeManager.mqh","AE_All.mqh"
]

def need(c,m):
    if not c: raise SystemExit("AUTHOR ENGINE 16 CONTRACT FAIL: "+m)

def main():
    for f in REQUIRED: need((AE/f).exists(),"missing "+f)
    need(WATCHER.exists(),"missing DrummondAuthorShadow_16.mq4")

    alltext="\n".join((AE/f).read_text(encoding="utf-8") for f in REQUIRED)
    w=WATCHER.read_text(encoding="utf-8")

    # Dots.
    d=(AE/"AE_Dots.mqh").read_text(encoding="utf-8")
    need("AE_StaticPLDot" in d and "shift+1" in d and "shift+2" in d and "shift+3" in d,
         "static PLDot contract missing")
    need("AE_LivePLDot" in d and "h0+l0+px" in d and "AE_Typical(sym,tf,1)" in d and "AE_Typical(sym,tf,2)" in d,
         "Live PLDot contract missing")
    need("AE_RefreshHigh" in d and "AE_RefreshLow" in d and "AE_IsLiveRefresh" in d,
         "Live/static refresh zone missing")
    need("AE_MCLineNow" in d and "AE_DotsBack23Zone" in d and "AE_DotsForward23Zone" in d,
         "dot signal geometry missing")

    # Lines.
    l=(AE/"AE_Lines.mqh").read_text(encoding="utf-8")
    for token in ["5/1_UP","5/1_DOWN","5/2_UP","5/2_DOWN","5/3_UP","5/3_DOWN",
                  "5/9_UP","5/9_DOWN","1-1_FROM_LOW","1-1_FROM_HIGH",
                  "6/1_UP","6/5_DOWN","6/1_DOWN","6/5_UP","6/7_UP","6/7_DOWN","6/6_UP","6/6_DOWN"]:
        need(token in l,"line missing: "+token)
    need("AE_Project12To0" in l,"5/x projection contract missing")
    need("AE_ProjectBarToHalfDot" in l,"between-bar dot geometry missing")
    need("3.0*l1-2.0*pl1" in l and "3.0*h1-2.0*pl1" in l,"6/6 geometry missing")

    # Higher modules.
    for token in ["AE_CurrentTradeState","AE_Envelope","AE_GetEnergyZones","AE_GetBlockArea",
                  "AE_DottedSetupEvidence","AE_HTPAligned","AE_ExhaustionEvidence",
                  "AE_PrimaryResearchSignal"]:
        need(token in alltext,"higher module API missing: "+token)

    # Source gaps are explicit rather than invented.
    a=(AE/"AE_All.mqh").read_text(encoding="utf-8")
    need('AE_SOURCE_GAP_CLOSED_51 "SOURCE_GAP"' in a,"Closed 5/1 source-gap guard missing")
    need('AE_SOURCE_GAP_CLOSED_59 "SOURCE_GAP"' in a,"Closed 5/9 source-gap guard missing")
    need('AE_SOURCE_GAP_JAWS_59 "SOURCE_GAP"' in a,"Jaws 5/9 source-gap guard missing")

    # Shadow-only.
    for token in ["OrderSend(","OrderModify(","OrderClose(","OrderDelete("]:
        need(token not in w and token not in alltext,"trading token present: "+token)
    need("AE_TradingEnabled(){ return(false); }" in alltext,"trade manager is not fail-closed")
    need("STRATEGY_TESTER_FORBIDDEN" in w and "ACCOUNT_NOT_DEMO" in w,"VPS safety gates missing")
    need("DRUMMOND_AUTHOR16_H1.csv" in w and "DRUMMOND_AUTHOR16_LIVE.csv" in w,"snapshot outputs missing")
    need("InpLiveSnapshotSeconds=300" in w,"5-minute live cadence missing")
    need("AE_SOURCE_GAP_CLOSED_51" in w and "AE_SOURCE_GAP_JAWS_59" in w,"source-gap audit output missing")

    print("DRUMMOND AUTHOR ENGINE 16 CONTRACT PASS")
    print("MODULES:",len(REQUIRED))
    print("STATIC_PLDOT: ENABLED")
    print("LIVE_PLDOT: ENABLED")
    print("BETWEEN_BAR_GEOMETRY: ENABLED")
    print("5X_6X_1_1: ENABLED")
    print("HTP_LTP_STATE_ENERGY_CONGESTION: ENABLED")
    print("LIVE_CADENCE_SECONDS: 300")
    print("CLOSED_5_1/CLOSED_5_9/JAWS_5_9: SOURCE_GAP")
    print("TRADING: DISABLED")

if __name__=="__main__":
    main()
