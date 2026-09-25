#!/usr/bin/env python3
"""
D30 — Drummond Predictive Value Audit.

Purpose:
  Test whether the recovered Drummond geometry/state contains information about
  future H1 price movement before any entry/SL/TP logic is introduced.

No trading rule is created here. No parameter fitting, selection, or promotion.
All diagnostic features are computed from information available at the H1 event
time. Forward outcomes are measured only after that time.
"""
import argparse,bisect,csv,json,math
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

from drummond_replay01 import read_xfbar
import D25 as F
from D17 import dot_dir,distance_mode,dot_in_prev_range,env_pos,line_features

HORIZONS=(1,4,12,24,72)
MIN_SCALE_BARS=24

FIELDS=[
 "HORIZON","DIM","KEY","N","SUM_RET","SUM_RET2","MEAN_RET",
 "UP_N","UP_RATE","SUM_ABS","MEAN_ABS","MIN_RET","MAX_RET"
]
ROB_FIELDS=[
 "HORIZON","DIM","KEY","SYMBOLS",
 "POS_DELTA_SYMBOLS","NEG_DELTA_SYMBOLS","ZERO_DELTA_SYMBOLS",
 "ABS_UP_SYMBOLS","ABS_DOWN_SYMBOLS","ABS_ZERO_SYMBOLS"
]
YEAR_FIELDS=[
 "HORIZON","DIM","KEY","YEAR","N","SUM_RET","SUM_RET2",
 "UP_N","SUM_ABS","MIN_RET","MAX_RET"
]

def newagg():
    return {"n":0,"sum":0.0,"sum2":0.0,"up":0,"abs":0.0,"min":None,"max":None}

def add(a,r):
    a["n"]+=1
    a["sum"]+=r
    a["sum2"]+=r*r
    if r>0:a["up"]+=1
    a["abs"]+=abs(r)
    a["min"]=r if a["min"] is None else min(a["min"],r)
    a["max"]=r if a["max"] is None else max(a["max"],r)

def mean(a):
    return a["sum"]/a["n"] if a["n"] else None

def mean_abs(a):
    return a["abs"]/a["n"] if a["n"] else None

def txtdir(d):
    return "UP" if d>0 else "DOWN" if d<0 else "NONE"

def yn(x):
    return "Y" if x else "N"

def pair(up,dn):
    if up and dn:return "BOTH"
    if up:return "UP"
    if dn:return "DOWN"
    return "NONE"

def cluster(n):
    return "0" if n==0 else "1" if n==1 else "2+"

def feature_keys(prev,sm,obs,h1,idx,point):
    lf,vals,sup,res=line_features(h1,idx,point)
    htp=txtdir(int(obs["htp_dir"]))
    return [
      ("STATE",sm),
      ("RAW",obs["raw"]),
      ("HTP_RAW",obs["htp_raw"]),
      ("HTP_DIR",htp),
      ("TRANSITION",prev+"->"+sm),
      ("REASON",obs["reason"] or "NONE"),
      ("STATE_HTP",sm+"|"+htp),
      ("PL_PUSH",pair(bool(obs["pl_up"]),bool(obs["pl_dn"]))),
      ("LOSING_PUSH",yn(bool(obs["lose"]))),
      ("MATURE",pair(bool(obs["mup"]),bool(obs["mdn"]))),
      ("BLOCK_STRONG",yn(bool(obs["strong"]))),
      ("EXIT_SIGNAL",pair(bool(obs["exit_up"]),bool(obs["exit_dn"]))),
      ("DOT_DIR",txtdir(dot_dir(h1,idx,point))),
      ("DOT_DISTANCE_MODE",distance_mode(h1,idx,point)),
      ("DOT_IN_PREV_RANGE",yn(dot_in_prev_range(h1,idx))),
      ("ENV_POS",env_pos(h1,idx)),
      ("SUPPORT_CLUSTER",cluster(sup)),
      ("RESIST_CLUSTER",cluster(res)),
      ("SUP_RES_CLUSTER",cluster(sup)+"|"+cluster(res)),
    ]

def write_csv(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";")
        w.writeheader();w.writerows(rows)

def agg_rows(agg):
    out=[]
    for (h,dim,key),a in sorted(agg.items()):
        out.append({
          "HORIZON":h,"DIM":dim,"KEY":key,"N":a["n"],
          "SUM_RET":f"{a['sum']:.12f}",
          "SUM_RET2":f"{a['sum2']:.12f}",
          "MEAN_RET":f"{mean(a):.12f}" if a["n"] else "",
          "UP_N":a["up"],
          "UP_RATE":f"{a['up']/a['n']:.12f}" if a["n"] else "",
          "SUM_ABS":f"{a['abs']:.12f}",
          "MEAN_ABS":f"{mean_abs(a):.12f}" if a["n"] else "",
          "MIN_RET":"" if a["min"] is None else f"{a['min']:.12f}",
          "MAX_RET":"" if a["max"] is None else f"{a['max']:.12f}",
        })
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    agg=defaultdict(newagg)
    years=defaultdict(newagg)
    robust=defaultdict(lambda:{
      "symbols":0,"pos":0,"neg":0,"zero":0,
      "abs_up":0,"abs_down":0,"abs_zero":0
    })
    syms=0;events=0;outcomes=0;errs=[];skips=Counter()

    for h1p in sorted(a.data_root.rglob("*_H1.bin")):
        sym=h1p.name[:-7]
        try:
            h4s=list(a.data_root.rglob(f"{sym}_H4.bin"))
            m5s=list(a.data_root.rglob(f"{sym}_M5.bin"))
            if not h4s:skips["SKIP_NO_H4"]+=1;continue
            if not m5s:skips["SKIP_NO_M5"]+=1;continue
            if len(h4s)!=1 or len(m5s)!=1:raise RuntimeError("duplicate required TF")

            h1h,h1=read_xfbar(h1p)
            h4h,h4=read_xfbar(h4s[0])
            m5h,m5=read_xfbar(m5s[0])
            if h1h["period_seconds"]!=3600 or h4h["period_seconds"]!=14400 or m5h["period_seconds"]!=300:
                raise RuntimeError("TF contract")
            point=float(h1h["point"])
            if point<=0:raise RuntimeError("invalid point")

            ctx,_=F.build_contexts(sym,h1,h4,m5,point)
            syms+=1

            # Causal volatility scale: mean H1 high-low range of the 24
            # completed H1 bars immediately before the event.
            rp=[0.0]
            for b in h1:
                rp.append(rp[-1]+max(0.0,float(b[2])-float(b[3])))

            local=defaultdict(newagg)
            local_all=defaultdict(newagg)

            for idx,t,hi,ma,mb,prev,sm,obs in ctx:
                if idx<MIN_SCALE_BARS:continue
                scale=(rp[idx]-rp[idx-MIN_SCALE_BARS])/MIN_SCALE_BARS
                if not math.isfinite(scale) or scale<=point*0.5:
                    skips["SKIP_BAD_LAG24_SCALE"]+=1
                    continue

                feats=feature_keys(prev,sm,obs,h1,idx,point)
                event_year=str(datetime.fromtimestamp(int(t),tz=timezone.utc).year)
                event_open=float(h1[idx][1])
                events+=1

                for h in HORIZONS:
                    end_idx=idx+h-1
                    if end_idx>=len(h1):continue
                    r=(float(h1[end_idx][4])-event_open)/scale
                    if not math.isfinite(r):
                        skips["SKIP_NONFINITE_FORWARD"]+=1
                        continue
                    outcomes+=1

                    base=(h,"ALL","ALL")
                    add(agg[base],r);add(local[base],r);add(local_all[h],r)
                    add(years[base+(event_year,)],r)

                    for dim,key in feats:
                        base=(h,dim,key)
                        add(agg[base],r);add(local[base],r)
                        add(years[base+(event_year,)],r)

            # Per-symbol robustness is measured as effect versus that symbol's
            # own unconditional baseline at the same horizon.
            for (h,dim,key),x in local.items():
                if dim=="ALL" or not x["n"]:continue
                b=local_all.get(h)
                if not b or not b["n"]:continue
                delta=mean(x)-mean(b)
                adelta=mean_abs(x)-mean_abs(b)
                z=robust[(h,dim,key)];z["symbols"]+=1
                eps=1e-15
                if delta>eps:z["pos"]+=1
                elif delta<-eps:z["neg"]+=1
                else:z["zero"]+=1
                if adelta>eps:z["abs_up"]+=1
                elif adelta<-eps:z["abs_down"]+=1
                else:z["abs_zero"]+=1

        except Exception as e:
            errs.append({"symbol":sym,"error":str(e)})

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D30.csv",FIELDS,agg_rows(agg))

    rrows=[]
    for (h,dim,key),z in sorted(robust.items()):
        rrows.append({
          "HORIZON":h,"DIM":dim,"KEY":key,"SYMBOLS":z["symbols"],
          "POS_DELTA_SYMBOLS":z["pos"],"NEG_DELTA_SYMBOLS":z["neg"],
          "ZERO_DELTA_SYMBOLS":z["zero"],
          "ABS_UP_SYMBOLS":z["abs_up"],"ABS_DOWN_SYMBOLS":z["abs_down"],
          "ABS_ZERO_SYMBOLS":z["abs_zero"],
        })
    write_csv(a.out/"D30R.csv",ROB_FIELDS,rrows)

    yrows=[]
    for (h,dim,key,year),x in sorted(years.items()):
        yrows.append({
          "HORIZON":h,"DIM":dim,"KEY":key,"YEAR":year,"N":x["n"],
          "SUM_RET":f"{x['sum']:.12f}","SUM_RET2":f"{x['sum2']:.12f}",
          "UP_N":x["up"],"SUM_ABS":f"{x['abs']:.12f}",
          "MIN_RET":"" if x["min"] is None else f"{x['min']:.12f}",
          "MAX_RET":"" if x["max"] is None else f"{x['max']:.12f}",
        })
    write_csv(a.out/"D30Y.csv",YEAR_FIELDS,yrows)

    summary={
      "block":"D30",
      "status":"PASS" if syms>0 and outcomes>0 and not errs else "FAIL",
      "symbols":syms,"events":events,"forward_outcomes":outcomes,
      "errors":len(errs),"skips":dict(skips),
      "horizons_h1_bars":list(HORIZONS),
      "scale":"mean H1 high-low range of prior 24 completed H1 bars",
      "features":[
        "STATE","RAW","HTP_RAW","HTP_DIR","TRANSITION","REASON","STATE_HTP",
        "PL_PUSH","LOSING_PUSH","MATURE","BLOCK_STRONG","EXIT_SIGNAL",
        "DOT_DIR","DOT_DISTANCE_MODE","DOT_IN_PREV_RANGE","ENV_POS",
        "SUPPORT_CLUSTER","RESIST_CLUSTER","SUP_RES_CLUSTER"
      ],
      "contract":{
        "source_engine":"D25 recovered continuous state machine",
        "trading_entries_used":False,
        "stops_targets_used":False,
        "pnl_used":False,
        "all_features_known_at_event_time":True,
        "forward_outcomes_only_after_event":True,
        "future_filter_used":False,
        "selection_or_optimization":False,
        "promotion_allowed":False,
        "lookahead":False,
        "env_pos_status":"RECOVERED_PROXY"
      },
      "interpretation":"Predictive information is assessed as conditional future normalized return and absolute movement versus unconditional same-horizon baselines; no cell is a trading rule."
    }
    (a.out/"D30.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.out/"D30_ERR.json").write_text(json.dumps(errs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    print("D30",summary["status"],"symbols",syms,"events",events,
          "forward_outcomes",outcomes,"errors",len(errs),"cells",len(agg))
    if summary["status"]!="PASS":raise SystemExit(2)

if __name__=="__main__":
    main()
