#!/usr/bin/env python3
"""
D31 — Frozen Drummond Hypothesis Stress Test.

Three hypotheses are frozen before this run and evaluated together:

H1 CONTRARIAN_STATE
  Every directional recovered state participates symmetrically.
  DOWN states should be followed by higher returns than UP states.
  Effect = 0.5 * (mean_ret(DOWN) - mean_ret(UP)).

H2 ENVELOPE_MEAN_REVERSION
  RECOVERED_PROXY envelope extremes only.
  BELOW_EB should be followed by higher returns than ABOVE_ET.
  Effect = 0.5 * (mean_ret(BELOW_EB) - mean_ret(ABOVE_ET)).

H3 STRONG_BLOCK_VOLATILITY
  BLOCK_STRONG should precede larger absolute movement than not-strong.
  Effect = mean_abs(STRONG) - mean_abs(WEAK).

No trading entries, SL/TP, PnL, parameter fitting, or cell selection.
The five horizons are frozen to D30: 1/4/12/24/72 H1 bars.
"""
import argparse,csv,json,math
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

from drummond_replay01 import read_xfbar
import D25 as F
from D17 import env_pos

HORIZONS=(1,4,12,24,72)
MIN_SCALE_BARS=24

UP_STATES={"TR_UP","EX_UP","CE_UP","REV_UP","CX_UP"}
DOWN_STATES={"TR_DN","EX_DN","CE_DN","REV_DN","CX_DN"}

FIELDS=[
 "SYMBOL","YEAR","HYPOTHESIS","HORIZON","GROUP",
 "N","SUM_RET","SUM_ABS","UP_N"
]

def newagg():
    return {"n":0,"sum":0.0,"abs":0.0,"up":0}

def add(a,r):
    a["n"]+=1
    a["sum"]+=r
    a["abs"]+=abs(r)
    if r>0:a["up"]+=1

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

    cells=defaultdict(newagg)
    syms=0;events=0;forward_outcomes=0;errs=[];skips=Counter()

    for h1p in sorted(a.data_root.rglob("*_H1.bin")):
        sym=h1p.name[:-7]
        try:
            h4s=list(a.data_root.rglob(f"{sym}_H4.bin"))
            m5s=list(a.data_root.rglob(f"{sym}_M5.bin"))
            if not h4s:skips["SKIP_NO_H4"]+=1;continue
            if not m5s:skips["SKIP_NO_M5"]+=1;continue
            if len(h4s)!=1 or len(m5s)!=1:
                raise RuntimeError("duplicate required TF")

            h1h,h1=read_xfbar(h1p)
            h4h,h4=read_xfbar(h4s[0])
            m5h,m5=read_xfbar(m5s[0])
            if h1h["period_seconds"]!=3600 or h4h["period_seconds"]!=14400 or m5h["period_seconds"]!=300:
                raise RuntimeError("TF contract")
            point=float(h1h["point"])
            if point<=0:raise RuntimeError("invalid point")

            ctx,_=F.build_contexts(sym,h1,h4,m5,point)
            syms+=1

            # Causal normalization: only the 24 completed H1 bars before t.
            rp=[0.0]
            for b in h1:
                rp.append(rp[-1]+max(0.0,float(b[2])-float(b[3])))

            for idx,t,hi,ma,mb,prev,sm,obs in ctx:
                if idx<MIN_SCALE_BARS:continue
                scale=(rp[idx]-rp[idx-MIN_SCALE_BARS])/MIN_SCALE_BARS
                if not math.isfinite(scale) or scale<=point*0.5:
                    skips["SKIP_BAD_LAG24_SCALE"]+=1
                    continue

                year=str(datetime.fromtimestamp(int(t),tz=timezone.utc).year)
                event_open=float(h1[idx][1])
                ep=env_pos(h1,idx)
                strong=bool(obs["strong"])
                events+=1

                for h in HORIZONS:
                    end_idx=idx+h-1
                    if end_idx>=len(h1):continue
                    r=(float(h1[end_idx][4])-event_open)/scale
                    if not math.isfinite(r):
                        skips["SKIP_NONFINITE_FORWARD"]+=1
                        continue
                    forward_outcomes+=1

                    if sm in UP_STATES:
                        add(cells[(sym,year,"CONTRARIAN_STATE",h,"UP")],r)
                    elif sm in DOWN_STATES:
                        add(cells[(sym,year,"CONTRARIAN_STATE",h,"DOWN")],r)

                    if ep=="ABOVE_ET":
                        add(cells[(sym,year,"ENVELOPE_MEAN_REVERSION",h,"ABOVE_ET")],r)
                    elif ep=="BELOW_EB":
                        add(cells[(sym,year,"ENVELOPE_MEAN_REVERSION",h,"BELOW_EB")],r)

                    add(cells[(sym,year,"STRONG_BLOCK_VOLATILITY",h,"STRONG" if strong else "WEAK")],r)

        except Exception as e:
            errs.append({"symbol":sym,"error":str(e)})

    rows=[]
    for (sym,year,hyp,h,g),x in sorted(cells.items()):
        rows.append({
          "SYMBOL":sym,"YEAR":year,"HYPOTHESIS":hyp,"HORIZON":h,"GROUP":g,
          "N":x["n"],"SUM_RET":f"{x['sum']:.12f}",
          "SUM_ABS":f"{x['abs']:.12f}","UP_N":x["up"]
        })

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D31.csv",rows)

    summary={
      "block":"D31",
      "status":"PASS" if syms>0 and forward_outcomes>0 and not errs else "FAIL",
      "symbols":syms,"events":events,"forward_outcomes":forward_outcomes,
      "errors":len(errs),"skips":dict(skips),
      "horizons_h1_bars":list(HORIZONS),
      "hypotheses":{
        "CONTRARIAN_STATE":{
          "groups":{"UP":sorted(UP_STATES),"DOWN":sorted(DOWN_STATES)},
          "effect":"0.5*(mean_ret(DOWN)-mean_ret(UP))",
          "positive_supports_hypothesis":True
        },
        "ENVELOPE_MEAN_REVERSION":{
          "groups":["ABOVE_ET","BELOW_EB"],
          "effect":"0.5*(mean_ret(BELOW_EB)-mean_ret(ABOVE_ET))",
          "positive_supports_hypothesis":True,
          "envelope_status":"RECOVERED_PROXY"
        },
        "STRONG_BLOCK_VOLATILITY":{
          "groups":["STRONG","WEAK"],
          "effect":"mean_abs(STRONG)-mean_abs(WEAK)",
          "positive_supports_hypothesis":True
        }
      },
      "scale":"mean H1 high-low range of prior 24 completed H1 bars",
      "contract":{
        "hypotheses_frozen_before_run":True,
        "all_three_tested_together":True,
        "horizons_frozen_before_run":True,
        "trading_entries_used":False,
        "stops_targets_used":False,
        "pnl_used":False,
        "all_features_known_at_event_time":True,
        "future_filter_used":False,
        "selection_or_optimization":False,
        "promotion_allowed":False,
        "lookahead":False
      },
      "interpretation_limit":"D31 stress-tests three hypotheses discovered in D30 on the same historical universe. This is not a genuinely unseen future sample."
    }
    (a.out/"D31.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.out/"D31_ERR.json").write_text(json.dumps(errs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    print("D31",summary["status"],"symbols",syms,"events",events,
          "forward_outcomes",forward_outcomes,"errors",len(errs),"cells",len(rows))
    if summary["status"]!="PASS":raise SystemExit(2)

if __name__=="__main__":
    main()
