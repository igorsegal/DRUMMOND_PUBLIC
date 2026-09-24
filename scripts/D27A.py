#!/usr/bin/env python3
import argparse,bisect,csv,json,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

SCHEMES=[
 ("1M_2W",2,1),("2M_1M",4,2),("3M_1.5M",6,3),
 ("4M_2M",8,4),("5M_2.5M",10,5),("6M_3M",12,6)
]
FIELDS=[
 "MODE","FLOW_N","N","MEAN_R","MEDIAN_R","POS_RATE",
 "SYMBOLS","POS_SYMBOLS","POS_SYMBOL_RATE",
 "YEARS","POS_YEARS","POS_YEAR_RATE","EQ_SYMBOL_MEAN_R","MEAN_WAIT_H1"
]
WF_FIELDS=[
 "MODE","FLOW_N","SCHEME","FOLDS","OOS_N","OOS_MEAN_R",
 "POS_OOS_FOLDS","POS_OOS_RATE","MIN_FOLD_R","MAX_FOLD_R"
]

def read_csv(p):
    with Path(p).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(p,fields,rows):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";");w.writeheader();w.writerows(rows)

def next_half(dt):
    if dt.day==1:return datetime(dt.year,dt.month,16,tzinfo=timezone.utc)
    if dt.month==12:return datetime(dt.year+1,1,1,tzinfo=timezone.utc)
    return datetime(dt.year,dt.month+1,1,tzinfo=timezone.utc)

def metric(rr):
    if not rr:return 0,None
    v=[float(x["R"]) for x in rr]
    return len(v),sum(v)/len(v)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    csvs=sorted(a.root.rglob("D27.csv"))
    sums=sorted(a.root.rglob("D27.json"))
    if len(csvs)!=7 or len(sums)!=7:
        raise SystemExit(f"D27A expected 7 shards, got csv={len(csvs)} json={len(sums)}")

    symbols=0;rows=[];seen=set()
    for p in sums:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s.get("status")!="PASS" or int(s.get("errors",0))!=0:raise SystemExit(f"bad D27 shard {p}")
        c=s.get("contract",{})
        if c.get("ca_setup_opens_trade") or c.get("future_refresh_filter_used") or c.get("lookahead"):
            raise SystemExit("D27 causality violation")
        if c.get("selection_or_optimization") or c.get("factory02_lifecycle_used"):
            raise SystemExit("D27 contamination")
        symbols+=int(s["symbols"])
    for p in csvs:
        for r in read_csv(p):
            k=(r["SYMBOL"],r["MODE"],r["FLOW_N"],r["ENTRY_TIME"],r["CA_SETUP_TIME"],r["SIDE"])
            if k in seen:raise SystemExit(f"duplicate D27 trade {k}")
            seen.add(k);rows.append(r)
    rows.sort(key=lambda r:(int(r["ENTRY_TIME"]),r["SYMBOL"],r["MODE"],int(r["FLOW_N"])))

    stats=[];wf=[]
    for mode in ("STRICT","PROXY"):
      for fn in (1,2,3):
        rr=[x for x in rows if x["MODE"]==mode and int(x["FLOW_N"])==fn]
        vals=[float(x["R"]) for x in rr]
        bysym=defaultdict(list);byyear=defaultdict(list)
        for x in rr:
            bysym[x["SYMBOL"]].append(float(x["R"]))
            y=datetime.fromtimestamp(int(x["ENTRY_TIME"]),tz=timezone.utc).year
            byyear[y].append(float(x["R"]))
        sm=[sum(v)/len(v) for v in bysym.values()]
        ym=[sum(v)/len(v) for v in byyear.values()]
        stats.append({
          "MODE":mode,"FLOW_N":fn,"N":len(rr),
          "MEAN_R":f"{sum(vals)/len(vals):.10f}" if vals else "",
          "MEDIAN_R":f"{statistics.median(vals):.10f}" if vals else "",
          "POS_RATE":f"{sum(v>0 for v in vals)/len(vals):.10f}" if vals else "",
          "SYMBOLS":len(sm),"POS_SYMBOLS":sum(v>0 for v in sm),
          "POS_SYMBOL_RATE":f"{sum(v>0 for v in sm)/len(sm):.10f}" if sm else "",
          "YEARS":len(ym),"POS_YEARS":sum(v>0 for v in ym),
          "POS_YEAR_RATE":f"{sum(v>0 for v in ym)/len(ym):.10f}" if ym else "",
          "EQ_SYMBOL_MEAN_R":f"{sum(sm)/len(sm):.10f}" if sm else "",
          "MEAN_WAIT_H1":f"{sum(int(x['WAIT_H1']) for x in rr)/len(rr):.6f}" if rr else ""
        })

        if rr:
            mn=min(int(x["ENTRY_TIME"]) for x in rr);mx=max(int(x["ENTRY_TIME"]) for x in rr)
            anchor=datetime(datetime.fromtimestamp(mn,tz=timezone.utc).year,1,1,tzinfo=timezone.utc)
            bounds=[anchor]
            while int(bounds[-1].timestamp())<=mx:bounds.append(next_half(bounds[-1]))
            bt=[int(x.timestamp()) for x in bounds];periods=len(bt)-1
            byp=defaultdict(list)
            for x in rr:
                k=bisect.bisect_right(bt,int(x["ENTRY_TIME"]))-1
                if 0<=k<periods:byp[k].append(x)

            for name,isu,ou in SCHEMES:
                start=0;foldmeans=[];all_oos=[]
                while start+isu+ou<=periods:
                    ie=start+isu;oe=ie+ou;o=[]
                    for k in range(ie,oe):o.extend(byp.get(k,[]))
                    if o:
                        _,m=metric(o);foldmeans.append(m);all_oos.extend(o)
                    start+=ou
                n,m=metric(all_oos)
                wf.append({
                  "MODE":mode,"FLOW_N":fn,"SCHEME":name,"FOLDS":len(foldmeans),
                  "OOS_N":n,"OOS_MEAN_R":"" if m is None else f"{m:.10f}",
                  "POS_OOS_FOLDS":sum(x>0 for x in foldmeans),
                  "POS_OOS_RATE":f"{sum(x>0 for x in foldmeans)/len(foldmeans):.10f}" if foldmeans else "",
                  "MIN_FOLD_R":f"{min(foldmeans):.10f}" if foldmeans else "",
                  "MAX_FOLD_R":f"{max(foldmeans):.10f}" if foldmeans else ""
                })

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D27A.csv",FIELDS,stats)
    write_csv(a.out/"D27W.csv",WF_FIELDS,wf)

    summary={
      "block":"D27","status":"PASS","symbols":symbols,"trades":len(rows),
      "stats":stats,"walkforward":wf,
      "contract":{
        "rule_frozen_before_test":True,
        "rule_source":"D26 diagnostic hypothesis",
        "ca_setup_opens_trade":False,
        "first_entry_is_observed_live_pldot_refresh_after_same-direction_trend_confirmation":True,
        "future_event_filter":False,"lookahead":False,
        "selection_or_optimization":False,"pyramiding":"OFF"
      },
      "interpretation_limit":"D27 uses the same historical universe that generated the D26 hypothesis; temporal robustness is measured, but this is not a genuinely unseen future sample."
    }
    (a.out/"D27.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=["D27 CAUSAL REFRESH ENTRY","STATUS: PASS",f"SYMBOLS: {symbols}",f"TRADES: {len(rows)}",
           "LOOKAHEAD: NO","SELECTION/OPTIMIZATION: NO","PYRAMIDING: OFF"]
    for x in stats:
        lines.append(
          f"{x['MODE']}:F{x['FLOW_N']}: N={x['N']} MEAN_R={x['MEAN_R']} "
          f"YEARS+={x['POS_YEARS']}/{x['YEARS']} SYMBOLS+={x['POS_SYMBOLS']}/{x['SYMBOLS']} "
          f"EQSYM={x['EQ_SYMBOL_MEAN_R']} WAIT_H1={x['MEAN_WAIT_H1']}"
        )
    for x in wf:
        lines.append(
          f"{x['MODE']}:F{x['FLOW_N']} {x['SCHEME']}: OOS_N={x['OOS_N']} "
          f"MEAN_R={x['OOS_MEAN_R']} FOLDS+={x['POS_OOS_FOLDS']}/{x['FOLDS']}"
        )
    (a.out/"D27.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
