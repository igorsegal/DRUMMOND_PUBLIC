#!/usr/bin/env python3
import json
from pathlib import Path

CFG=Path("config/C01_FORWARD14.json")
SRC=Path("DRUMMOND_TRADER_DEMO_02_FIX2/DrummondWatcher_C01_FORWARD_14.mq4")
SHA="a9a00478647d73e147ee0c7e7a063adc5b0fe96b97d403b81af49b3937a57b3e"

def need(cond,msg):
    if not cond:
        raise SystemExit("C01 FORWARD 14 CONTRACT FAIL: "+msg)

def main():
    need(CFG.exists(),"missing config")
    need(SRC.exists(),"missing watcher source")
    cfg=json.loads(CFG.read_text(encoding="utf-8"))
    src=SRC.read_text(encoding="utf-8")

    need(cfg.get("schema")=="DRUMMOND_C01_FORWARD_14","bad schema")
    need(cfg.get("state")=="FROZEN_FORWARD_SHADOW","bad state")
    need(cfg.get("frozen_candidate_sha256")==SHA,"frozen SHA mismatch")
    need(cfg["rule"]["id"]=="C01","bad rule id")
    need(cfg["rule"]["side"]=="LONG","C01 must remain LONG")
    need(cfg["rule"]["feature"]=="ENTRY_PLDOT_R","bad feature")
    need(cfg["rule"]["condition"]=="ENTRY_PLDOT_R < 0","bad frozen condition")
    need(cfg["rule"]["equivalent_live_condition"]=="entry_reference < decision_pldot","bad live equivalence")
    need(cfg["policy"]["forward_capture_only"] is True,"forward capture must be true")
    need(cfg["policy"]["trading_enabled"] is False,"trading must remain disabled")
    need(cfg["policy"]["historical_replay_on_attach"] is False,"historical replay must remain disabled")
    need(cfg["policy"]["production_promotion"] is False,"production promotion must remain false")

    need(SHA in src,"source frozen SHA missing")
    need("#include <DT02_Common.mqh>" in src,"standard MQL4 Include path missing")
    need('#include "DT02_Common.mqh"' not in src,"local quoted include is forbidden")
    need("D2_DIR_LONG_ONLY" in src,"source must force LONG_ONLY")
    need("entryPLdotR<0.0" in src,"exact C01 condition missing")
    need("plan.entry_reference-plan.decision_pldot" in src,"live C01 feature formula missing")
    need("STRATEGY_TESTER_FORBIDDEN" in src and "IsTesting()" in src,"tester must be blocked")
    need("ACCOUNT_NOT_DEMO" in src and "IsDemo()" in src,"demo account gate missing")
    need("Trading       = DISABLED BY DESIGN" in src,"explicit no-trading declaration missing")
    need("History replay= DISABLED BY DESIGN" in src,"explicit no-replay declaration missing")
    need("g_c01_lastClosedDecision[k]=iTime(sym,InpDecisionTF,1)" in src,"attach must skip current closed H1")
    need("DRUMMOND_C01_FORWARD14.csv" in src,"capture filename missing")
    need("DRUMMOND_C01_FORWARD14_AUDIT.csv" in src,"audit filename missing")

    forbidden=["OrderSend(","OrderModify(","OrderClose(","OrderDelete(","DRUMMOND_DEMO02_SIGNALS.csv"]
    for token in forbidden:
        need(token not in src,f"forbidden trading/queue token present: {token}")

    print("DRUMMOND C01 FORWARD SHADOW 14 CONTRACT PASS")
    print("FROZEN_SHA256:",SHA)
    print("RULE: LONG && entry_reference < decision_pldot")
    print("STRATEGY_TESTER: FORBIDDEN")
    print("TRADING: DISABLED")
    print("HISTORICAL_REPLAY_ON_ATTACH: DISABLED")

if __name__=="__main__":
    main()
