#!/usr/bin/env python3
"""
D33 — Price vs Drummond Incremental Predictive Value.

Question:
  Does recovered Drummond geometry add out-of-sample predictive information
  beyond simple raw-price/volatility structure?

Fixed temporal split:
  TRAIN: event time < 2022-01-01 00:00:00 UTC
  TEST : event time >= 2022-01-01 00:00:00 UTC

Three frozen models, trained separately for each symbol:
  PRICE      : raw H1 price/volatility cell only.
  DRUMMOND   : recovered Drummond geometry/state cell only.
  PRICE+DRUM : PRICE forecast plus a Drummond residual correction learned
               only on TRAIN data.

Targets at fixed horizons 1/4/12/24/72 H1 bars:
  directional return normalized by prior-24 completed H1 mean range;
  absolute normalized movement.

No trading entries, SL/TP, PnL, future filtering, or parameter search.
"""
import argparse,bisect,csv,json,math
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

from drummond_replay01 import read_xfbar
import D25 as F
from D17 import dot_dir,distance_mode,dot_in_prev_range,env_pos

HORIZONS=(1,4,12,24,72)
CUTOVER=1640995200  # 2022-01-01 00:00:00 UTC
SHRINK_K=50.0
MIN_TRAIN=500
MIN_TEST=100

MODELS=("BASE","PRICE","DRUMMOND","PRICE_DRUMMOND")

FIELDS=[
 "SYMBOL","HORIZON","MODEL","TRAIN_N","TEST_N",
 "SSE_RET","CORRECT_DIR","SSE_ABS",
 "SUM_RET","SUM_ABS","SUM_PRED_RET","SUM_PRED_ABS"
]

def newstat():
    return {"n":0,"sum":0.0,"abs":0.0}

def addstat(a,y):
    a["n"]+=1;a["sum"]+=y;a["abs"]+=abs(y)

def shrunk(sum_,n,prior,k=SHRINK_K):
    return (sum_+k*prior)/(n+k)

def bucket(v,cuts):
    for i,c in enumerate(cuts):
        if v<c:return str(i)
    return str(len(cuts))

def txtdir(d):
    return "UP" if d>0 else "DOWN" if d<0 else "NONE"

def price_key(h1,idx,scale):
    if idx<4:return None
    b=h1[idx-1]
    rng=max(0.0,float(b[2])-float(b[3]))
    if rng<=0:return None
    body=abs(float(b[4])-float(b[1]))/rng
    cpos=(float(b[4])-float(b[3]))/rng
    rr=rng/scale
    mom3=(float(h1[idx-1][4])-float(h1[idx-4][4]))/scale
    r3=sum(max(0.0,float(h1[k][2])-float(h1[k][3])) for k in range(idx-3,idx))/3.0/scale
    return "|".join([
      bucket(rr,(0.5,0.8,1.2,2.0)),
      bucket(body,(0.2,0.5,0.8)),
      bucket(cpos,(0.25,0.50,0.75)),
      bucket(mom3,(-1.0,-0.25,0.25,1.0)),
      bucket(r3,(0.6,0.9,1.1,1.5)),
    ])

def drum_key(sm,obs,h1,idx,point):
    return "|".join([
      sm,
      env_pos(h1,idx),
      "S" if bool(obs["strong"]) else "W",
      txtdir(dot_dir(h1,idx,point)),
      distance_mode(h1,idx,point),
      txtdir(int(obs["htp_dir"])),
      "IN" if dot_in_prev_range(h1,idx) else "OUT",
    ])

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";")
        w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    rows=[];errs=[];skips=Counter()
    symbols_seen=0;symbols_evaluated=0
    total_train=0;total_test=0

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
            symbols_seen+=1

            rp=[0.0]
            for b in h1:
                rp.append(rp[-1]+max(0.0,float(b[2])-float(b[3])))

            # Per-horizon records: (is_train, y, price_key, drum_key)
            recs={h:[] for h in HORIZONS}
            for idx,t,hi,ma,mb,prev,sm,obs in ctx:
                if idx<24:continue
                scale=(rp[idx]-rp[idx-24])/24.0
                if not math.isfinite(scale) or scale<=point*0.5:
                    skips["SKIP_BAD_LAG24_SCALE"]+=1;continue
                pk=price_key(h1,idx,scale)
                if pk is None:
                    skips["SKIP_BAD_PRICE_FEATURE"]+=1;continue
                dk=drum_key(sm,obs,h1,idx,point)
                event_open=float(h1[idx][1])
                is_train=int(t)<CUTOVER
                for h in HORIZONS:
                    end_idx=idx+h-1
                    if end_idx>=len(h1):continue
                    y=(float(h1[end_idx][4])-event_open)/scale
                    if not math.isfinite(y):
                        skips["SKIP_NONFINITE_TARGET"]+=1;continue
                    recs[h].append((is_train,y,pk,dk))

            any_eval=False
            for h in HORIZONS:
                rr=recs[h]
                tr=[x for x in rr if x[0]]
                te=[x for x in rr if not x[0]]
                if len(tr)<MIN_TRAIN or len(te)<MIN_TEST:
                    skips["SKIP_SYMBOL_HORIZON_SPLIT"]+=1
                    continue
                any_eval=True
                total_train+=len(tr);total_test+=len(te)

                g=newstat()
                pc=defaultdict(newstat)
                dc=defaultdict(newstat)
                for _,y,pk,dk in tr:
                    addstat(g,y);addstat(pc[pk],y);addstat(dc[dk],y)

                gmean=g["sum"]/g["n"];gabs=g["abs"]/g["n"]

                # PRICE residuals -> Drummond correction. This is the direct
                # incremental-information test.
                dr_res=defaultdict(lambda:{"n":0,"sum":0.0,"abs_sum":0.0})
                for _,y,pk,dk in tr:
                    p=pc[pk]
                    pp=shrunk(p["sum"],p["n"],gmean)
                    pa=shrunk(p["abs"],p["n"],gabs)
                    z=dr_res[dk];z["n"]+=1;z["sum"]+=y-pp;z["abs_sum"]+=abs(y)-pa

                ev={m:{"sse_ret":0.0,"correct":0,"sse_abs":0.0,
                       "sum_ret":0.0,"sum_abs":0.0,"sum_pr":0.0,"sum_pa":0.0}
                    for m in MODELS}

                for _,y,pk,dk in te:
                    ay=abs(y)
                    p=pc.get(pk,newstat());d=dc.get(dk,newstat())
                    base_r=gmean;base_a=gabs
                    price_r=shrunk(p["sum"],p["n"],gmean)
                    price_a=shrunk(p["abs"],p["n"],gabs)
                    drum_r=shrunk(d["sum"],d["n"],gmean)
                    drum_a=shrunk(d["abs"],d["n"],gabs)
                    z=dr_res.get(dk,{"n":0,"sum":0.0,"abs_sum":0.0})
                    corr_r=z["sum"]/(z["n"]+SHRINK_K)
                    corr_a=z["abs_sum"]/(z["n"]+SHRINK_K)
                    both_r=price_r+corr_r
                    both_a=max(0.0,price_a+corr_a)

                    preds={
                      "BASE":(base_r,base_a),
                      "PRICE":(price_r,price_a),
                      "DRUMMOND":(drum_r,drum_a),
                      "PRICE_DRUMMOND":(both_r,both_a)
                    }
                    for m,(pr,pa) in preds.items():
                        e=ev[m]
                        e["sse_ret"]+=(y-pr)*(y-pr)
                        e["correct"]+=int((pr>=0 and y>=0) or (pr<0 and y<0))
                        e["sse_abs"]+=(ay-pa)*(ay-pa)
                        e["sum_ret"]+=y;e["sum_abs"]+=ay
                        e["sum_pr"]+=pr;e["sum_pa"]+=pa

                for m in MODELS:
                    e=ev[m]
                    rows.append({
                      "SYMBOL":sym,"HORIZON":h,"MODEL":m,
                      "TRAIN_N":len(tr),"TEST_N":len(te),
                      "SSE_RET":f"{e['sse_ret']:.12f}",
                      "CORRECT_DIR":e["correct"],
                      "SSE_ABS":f"{e['sse_abs']:.12f}",
                      "SUM_RET":f"{e['sum_ret']:.12f}",
                      "SUM_ABS":f"{e['sum_abs']:.12f}",
                      "SUM_PRED_RET":f"{e['sum_pr']:.12f}",
                      "SUM_PRED_ABS":f"{e['sum_pa']:.12f}",
                    })

            if any_eval:symbols_evaluated+=1

        except Exception as e:
            errs.append({"symbol":sym,"error":str(e)})

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D33.csv",rows)

    summary={
      "block":"D33",
      "status":"PASS" if symbols_evaluated>0 and rows and not errs else "FAIL",
      "symbols_seen":symbols_seen,"symbols_evaluated":symbols_evaluated,
      "train_records_across_horizons":total_train,
      "test_records_across_horizons":total_test,
      "errors":len(errs),"skips":dict(skips),
      "split":{"train_before_utc":"2022-01-01T00:00:00Z","test_from_utc":"2022-01-01T00:00:00Z"},
      "horizons_h1_bars":list(HORIZONS),
      "models":{
        "BASE":"per-symbol pre-2022 unconditional mean",
        "PRICE":"frozen raw-H1 cell: last range/24H range, body/range, close position, 3H momentum, 3H range compression",
        "DRUMMOND":"frozen recovered state + envelope position + strong block + PLDot direction/distance + HTP direction + dot-in-range",
        "PRICE_DRUMMOND":"PRICE forecast plus pre-2022 Drummond-cell residual correction"
      },
      "shrink_k":SHRINK_K,"min_train":MIN_TRAIN,"min_test":MIN_TEST,
      "contract":{
        "fixed_time_split_before_run":True,
        "test_period_not_used_for_training":True,
        "feature_sets_frozen_before_run":True,
        "models_frozen_before_run":True,
        "trading_entries_used":False,
        "stops_targets_used":False,
        "pnl_used":False,
        "all_features_known_at_event_time":True,
        "future_filter_used":False,
        "parameter_search":False,
        "selection_or_optimization":False,
        "lookahead":False,
        "envelope_status":"RECOVERED_PROXY"
      },
      "interpretation_limit":"D33 is a temporal out-of-sample comparison inside the already-studied historical universe. It tests incremental information for these frozen PRICE and DRUMMOND representations, not every possible price model."
    }
    (a.out/"D33.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.out/"D33_ERR.json").write_text(json.dumps(errs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("D33",summary["status"],"seen",symbols_seen,"evaluated",symbols_evaluated,
          "train",total_train,"test",total_test,"rows",len(rows),"errors",len(errs))
    if summary["status"]!="PASS":raise SystemExit(2)

if __name__=="__main__":
    main()
