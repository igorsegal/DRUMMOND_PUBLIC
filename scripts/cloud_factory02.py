#!/usr/bin/env python3
import argparse,bisect,csv,hashlib,json,math,subprocess,sys
from collections import Counter
from pathlib import Path

from drummond_replay01 import read_xfbar,S,stop,SIDE_LONG,SIDE_SHORT

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(path,fields,rows):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";")
        w.writeheader();w.writerows(rows)

def side_int(text):
    return SIDE_LONG if text=="LONG" else SIDE_SHORT if text=="SHORT" else 0

def bar_prices(bar,side,point):
    t,o,h,l,c,tv,sp,rv=bar
    spread=max(0,sp)*point
    if side==SIDE_LONG:
        return t,o,h,l,c,spread
    return t,o+spread,h+spread,l+spread,c+spread,spread

def gap_hit(side,o,sl,tp):
    if side==SIDE_LONG:
        if sl>0 and o<=sl:return "SL",sl
        if tp>0 and o>=tp:return "TP",tp
    else:
        if sl>0 and o>=sl:return "SL",sl
        if tp>0 and o<=tp:return "TP",tp
    return None

def range_hit(side,h,l,sl,tp):
    if side==SIDE_LONG:
        hs=sl>0 and l<=sl
        ht=tp>0 and h>=tp
    else:
        hs=sl>0 and h>=sl
        ht=tp>0 and l<=tp
    if hs and ht:return "AMBIGUOUS",0.0
    if hs:return "SL",sl
    if ht:return "TP",tp
    return None

def simulate_signal(signal,m5,h1,point,digits,buffer_points):
    side=side_int(signal["SIDE"])
    if side==0: raise ValueError(f'bad side {signal["SIDE"]}')
    entry_time=int(signal["CREATED_AT"])
    entry=float(signal["ENTRY_REFERENCE"])
    sl=float(signal["STOP_PRICE"])
    tp=float(signal["TARGET_PRICE"])
    initial_sl=sl
    initial_risk=abs(entry-initial_sl)
    if initial_risk<=0: raise ValueError(f'non-positive initial risk {signal["SIGNAL_ID"]}')

    m5t=[b[0] for b in m5]
    h1t=[b[0] for b in h1]
    start=bisect.bisect_right(m5t,entry_time)
    if start>=len(m5):
        return {"outcome":"OPEN_AT_DATA_END","close_time":m5[-1][0] if m5 else 0,
                "close_level":0.0,"final_sl":sl,"trail_updates":0,
                "bars":0,"level_r":None,"future_guard_violations":0}

    trails=0;future=0;bars_seen=0
    for i in range(start,len(m5)):
        b=m5[i];bars_seen+=1
        t,o,h,l,c,spread=bar_prices(b,side,point)

        # Existing broker-side stop/target may gap at the next modeled M5 open.
        hit=gap_hit(side,o,sl,tp)
        if hit:
            reason,level=hit
            r=(level-entry)/initial_risk if side==SIDE_LONG else (entry-level)/initial_risk
            return {"outcome":reason,"close_time":t,"close_level":level,"final_sl":sl,
                    "trail_updates":trails,"bars":bars_seen,"level_r":r,
                    "future_guard_violations":future}

        # Executor OnTick trails existing positions before reading the signal queue.
        hc=bisect.bisect_right(h1t,t)-1
        if hc>=0:
            state=S(h1,hc,point,digits)
            reference=o
            candidate=stop(state,side,reference,buffer_points)
            if state.n()>=2 and state.bar(1)[0]>=t:
                future+=1
            if candidate is not None:
                tighter=False
                if side==SIDE_LONG:
                    tighter=(candidate<reference and (sl<=0 or candidate>sl+point))
                else:
                    tighter=(candidate>reference and (sl<=0 or candidate<sl-point))
                if tighter:
                    sl=candidate;trails+=1

        # MT4 Open-prices-only: EA logic is bar-open driven, while tester-managed
        # SL/TP can still be reached by the modeled M5 bar range afterwards.
        hit=range_hit(side,h,l,sl,tp)
        if hit:
            reason,level=hit
            if reason=="AMBIGUOUS":
                return {"outcome":"AMBIGUOUS_SAME_M5","close_time":t+300,"close_level":0.0,
                        "final_sl":sl,"trail_updates":trails,"bars":bars_seen,
                        "level_r":None,"future_guard_violations":future}
            r=(level-entry)/initial_risk if side==SIDE_LONG else (entry-level)/initial_risk
            return {"outcome":reason,"close_time":t+300,"close_level":level,"final_sl":sl,
                    "trail_updates":trails,"bars":bars_seen,"level_r":r,
                    "future_guard_violations":future}

    return {"outcome":"OPEN_AT_DATA_END","close_time":m5[-1][0],"close_level":0.0,
            "final_sl":sl,"trail_updates":trails,"bars":bars_seen,
            "level_r":None,"future_guard_violations":future}

def process_symbol(sym,folder,out,params):
    replay_out=out/"symbols"/sym/"replay01"
    lifecycle_out=out/"symbols"/sym
    cmd=[sys.executable,str(Path(__file__).with_name("drummond_replay01.py")),
         "--fixture",str(folder),"--symbol",sym,"--out",str(replay_out),
         "--direction",params["direction"],"--rr-min",str(params["rr_min"]),
         "--rr-max",str(params["rr_max"]),"--buffer-points",str(params["buffer_points"])]
    p=subprocess.run(cmd,capture_output=True,text=True)
    summary_path=replay_out/f"{sym}_REPLAY_SUMMARY.json"
    if p.returncode!=0 or not summary_path.exists():
        raise RuntimeError((p.stderr or p.stdout or "Replay01 failed").strip())

    replay_summary=json.loads(summary_path.read_text(encoding="utf-8"))
    signals=read_csv(replay_out/f"{sym}_REPLAY_SIGNALS.csv")
    h1h,h1=read_xfbar(folder/f"{sym}_H1.bin")
    m5h,m5=read_xfbar(folder/f"{sym}_M5.bin")
    point=h1h["point"];digits=h1h["digits"]

    rows=[];oc=Counter();rvals=[];future=0;total_trails=0
    hh=hashlib.sha256()
    for sig in signals:
        x=simulate_signal(sig,m5,h1,point,digits,params["buffer_points"])
        oc[x["outcome"]]+=1
        future+=x["future_guard_violations"];total_trails+=x["trail_updates"]
        if x["level_r"] is not None and math.isfinite(x["level_r"]):rvals.append(x["level_r"])
        row={"SIGNAL_ID":sig["SIGNAL_ID"],"SIDE":sig["SIDE"],"ENTRY_TIME":sig["CREATED_AT"],
             "ENTRY_REFERENCE":sig["ENTRY_REFERENCE"],"INITIAL_SL":sig["STOP_PRICE"],
             "TARGET_PRICE":sig["TARGET_PRICE"],"OUTCOME":x["outcome"],
             "CLOSE_TIME":x["close_time"],"CLOSE_LEVEL":f'{x["close_level"]:.{digits}f}' if x["close_level"] else "",
             "FINAL_SL":f'{x["final_sl"]:.{digits}f}',"TRAIL_UPDATES":x["trail_updates"],
             "M5_BARS":x["bars"],"LEVEL_R":f'{x["level_r"]:.8f}' if x["level_r"] is not None else ""}
        rows.append(row)
        hh.update(("|".join(str(row[k]) for k in
            ("SIGNAL_ID","SIDE","ENTRY_TIME","ENTRY_REFERENCE","INITIAL_SL","TARGET_PRICE",
             "OUTCOME","CLOSE_TIME","CLOSE_LEVEL","FINAL_SL","TRAIL_UPDATES","M5_BARS","LEVEL_R"))+"\n").encode())

    fields=["SIGNAL_ID","SIDE","ENTRY_TIME","ENTRY_REFERENCE","INITIAL_SL","TARGET_PRICE","OUTCOME",
            "CLOSE_TIME","CLOSE_LEVEL","FINAL_SL","TRAIL_UPDATES","M5_BARS","LEVEL_R"]
    write_csv(lifecycle_out/f"{sym}_FACTORY02_LIFECYCLE.csv",fields,rows)
    resolved=oc["TP"]+oc["SL"]
    profitable=sum(1 for r in rvals if r>0)
    mean_r=(sum(rvals)/len(rvals)) if rvals else None
    s={"symbol":sym,"status":"PASS" if future==0 else "FAIL",
       "signals":len(signals),"outcomes":dict(sorted(oc.items())),
       "resolved":resolved,"tp_rate_resolved":oc["TP"]/resolved if resolved else None,
       "profitable_level_r":profitable,"mean_level_r":mean_r,
       "trail_updates":total_trails,"future_guard_violations":future,
       "lifecycle_sha256":hh.hexdigest(),"replay01_signal_sha256":replay_summary["signal_sha256"]}
    (lifecycle_out/f"{sym}_FACTORY02_SUMMARY.json").write_text(json.dumps(s,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return s

def discover(root,symbols):
    if symbols:return [(s,root/s) for s in symbols]
    return sorted((p.name,p) for p in root.iterdir() if p.is_dir())

def selftest():
    # Synthetic SHORT: open 100, initial SL 110, TP 90. On the next bar, a
    # structural candidate is unavailable; the modeled low reaches TP.
    m5=[
      (1000,100.0,100.2,99.8,100.0,1,0,0),
      (1300,100.0,100.5,89.0,90.0,1,0,0)]
    h1=[]
    sig={"SIGNAL_ID":"T","SIDE":"SHORT","CREATED_AT":"1000","ENTRY_REFERENCE":"100.0",
         "STOP_PRICE":"110.0","TARGET_PRICE":"90.0"}
    x=simulate_signal(sig,m5,h1,0.01,2,1)
    assert x["outcome"]=="TP" and x["close_time"]==1600 and abs(x["level_r"]-1.0)<1e-12

    # Same-bar stop+target must remain ambiguous rather than selecting a winner.
    m5b=[m5[0],(1300,100.0,111.0,89.0,100.0,1,0,0)]
    y=simulate_signal(sig,m5b,h1,0.01,2,1)
    assert y["outcome"]=="AMBIGUOUS_SAME_M5"
    print("CLOUD FACTORY 02 SELFTEST PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("cmd",nargs="?",default="run",choices=("run","selftest"))
    ap.add_argument("--data-root",type=Path)
    ap.add_argument("--out",type=Path)
    ap.add_argument("--symbols",default="")
    ap.add_argument("--direction",choices=("BOTH","SHORT_ONLY","LONG_ONLY"),default="SHORT_ONLY")
    ap.add_argument("--rr-min",type=float,default=.75)
    ap.add_argument("--rr-max",type=float,default=1.75)
    ap.add_argument("--buffer-points",type=int,default=1)
    a=ap.parse_args()
    if a.cmd=="selftest":
        selftest();return
    if a.data_root is None or a.out is None: raise SystemExit("--data-root and --out are required")

    selected=[x.strip() for x in a.symbols.split(",") if x.strip()]
    items=discover(a.data_root,selected)
    rows=[];processed=skip_m5=skip_other=errors=0
    totals=Counter();r_sum=0.0;r_n=0
    params={"direction":a.direction,"rr_min":a.rr_min,"rr_max":a.rr_max,"buffer_points":a.buffer_points}
    for sym,folder in items:
        h1=folder/f"{sym}_H1.bin";h4=folder/f"{sym}_H4.bin";m5=folder/f"{sym}_M5.bin"
        base={"SYMBOL":sym,"STATUS":"","SIGNALS":"","TP":"","SL":"","AMBIGUOUS":"","OPEN":"",
              "TRAIL_UPDATES":"","TP_RATE_RESOLVED":"","MEAN_LEVEL_R":"","LIFECYCLE_SHA256":"","ERROR":""}
        if not h1.exists():
            base["STATUS"]="SKIP_NO_H1";skip_other+=1;rows.append(base);continue
        if not h4.exists():
            base["STATUS"]="SKIP_NO_H4";skip_other+=1;rows.append(base);continue
        if not m5.exists():
            base["STATUS"]="SKIP_NO_M5";skip_m5+=1;rows.append(base);continue
        try:
            s=process_symbol(sym,folder,a.out,params)
            if s["status"]!="PASS": raise RuntimeError("future guard violation")
            o=s["outcomes"]
            base.update(STATUS="PROCESSED",SIGNALS=s["signals"],TP=o.get("TP",0),SL=o.get("SL",0),
                        AMBIGUOUS=o.get("AMBIGUOUS_SAME_M5",0),OPEN=o.get("OPEN_AT_DATA_END",0),
                        TRAIL_UPDATES=s["trail_updates"],
                        TP_RATE_RESOLVED=f'{s["tp_rate_resolved"]:.8f}' if s["tp_rate_resolved"] is not None else "",
                        MEAN_LEVEL_R=f'{s["mean_level_r"]:.8f}' if s["mean_level_r"] is not None else "",
                        LIFECYCLE_SHA256=s["lifecycle_sha256"])
            processed+=1;totals["signals"]+=s["signals"];totals["TP"]+=o.get("TP",0);totals["SL"]+=o.get("SL",0)
            totals["AMBIGUOUS_SAME_M5"]+=o.get("AMBIGUOUS_SAME_M5",0);totals["OPEN_AT_DATA_END"]+=o.get("OPEN_AT_DATA_END",0)
            totals["trail_updates"]+=s["trail_updates"]
            if s["mean_level_r"] is not None and s["resolved"]>0:
                r_sum+=s["mean_level_r"]*s["resolved"];r_n+=s["resolved"]
        except Exception as e:
            base["STATUS"]="ERROR";base["ERROR"]=str(e)[:1000];errors+=1
        rows.append(base)

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"FACTORY02_SYMBOLS.csv",
      ["SYMBOL","STATUS","SIGNALS","TP","SL","AMBIGUOUS","OPEN","TRAIL_UPDATES","TP_RATE_RESOLVED",
       "MEAN_LEVEL_R","LIFECYCLE_SHA256","ERROR"],rows)
    resolved=totals["TP"]+totals["SL"]
    summary={"block":"CLOUD FACTORY 02","status":"PASS" if processed>0 and errors==0 else "FAIL",
      "scope":"Canonical multi-symbol Drummond signals with production-like structural trailing and MT4 Open-prices-only lifecycle semantics. Broker stop/freeze/order-modify rejection is not synthesized.",
      "parameters":params,
      "counts":{"discovered":len(items),"processed":processed,"skip_no_m5":skip_m5,
                "skip_other_required_tf":skip_other,"errors":errors,
                "signals":totals["signals"],"TP":totals["TP"],"SL":totals["SL"],
                "AMBIGUOUS_SAME_M5":totals["AMBIGUOUS_SAME_M5"],"OPEN_AT_DATA_END":totals["OPEN_AT_DATA_END"],
                "trail_updates":totals["trail_updates"]},
      "tp_rate_resolved":totals["TP"]/resolved if resolved else None,
      "mean_level_r_resolved":r_sum/r_n if r_n else None,
      "policy":{"missing_m5":"SKIP_NO_M5, never fail the run",
                "ambiguous_same_bar":"never guess winner",
                "broker_specific":"stop/freeze levels and OrderModify acceptance stay for MT4 final validation"}}
    (a.out/"FACTORY02_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["CLOUD FACTORY 02",f"STATUS: {summary['status']}",f"DISCOVERED: {len(items)}",
           f"PROCESSED: {processed}",f"SKIP_NO_M5: {skip_m5}",f"SKIP_OTHER_TF: {skip_other}",
           f"ERRORS: {errors}",f"SIGNALS: {totals['signals']}",
           f"TP/SL/AMBIGUOUS/OPEN: {totals['TP']}/{totals['SL']}/{totals['AMBIGUOUS_SAME_M5']}/{totals['OPEN_AT_DATA_END']}",
           f"TRAIL UPDATES: {totals['trail_updates']}",
           f"TP RATE RESOLVED: {summary['tp_rate_resolved']:.6f}" if summary["tp_rate_resolved"] is not None else "TP RATE RESOLVED: N/A",
           f"MEAN LEVEL R RESOLVED: {summary['mean_level_r_resolved']:.6f}" if summary["mean_level_r_resolved"] is not None else "MEAN LEVEL R RESOLVED: N/A"]
    (a.out/"FACTORY02_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
    raise SystemExit(0 if summary["status"]=="PASS" else 2)

if __name__=="__main__":
    main()
