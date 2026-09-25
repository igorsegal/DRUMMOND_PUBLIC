#!/usr/bin/env python3
"""
D32 — Frozen Predictive Intersection Test.

Single predeclared hypothesis:
  Strong Block amplifies Envelope mean reversion.

Four mutually exclusive groups at each H1 event:
  STRONG_BELOW_EB
  STRONG_ABOVE_ET
  WEAK_BELOW_EB
  WEAK_ABOVE_ET

Directional mean-reversion edge:
  strong_edge = 0.5 * (mean_ret(STRONG_BELOW_EB) - mean_ret(STRONG_ABOVE_ET))
  weak_edge   = 0.5 * (mean_ret(WEAK_BELOW_EB)   - mean_ret(WEAK_ABOVE_ET))
  interaction = strong_edge - weak_edge

Positive interaction supports the hypothesis that Strong Block adds directional
predictive value to Envelope extremes.

No trading entries, SL/TP, PnL, optimization, cell selection, or look-ahead.
Horizons are frozen to D30/D31: 1/4/12/24/72 H1 bars.
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
GROUPS=("STRONG_BELOW_EB","STRONG_ABOVE_ET","WEAK_BELOW_EB","WEAK_ABOVE_ET")

FIELDS=[
 "SYMBOL","YEAR","HORIZON","GROUP",
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

def group_name(strong,ep):
    if ep=="BELOW_EB":
        return "STRONG_BELOW_EB" if strong else "WEAK_BELOW_EB"
    if ep=="ABOVE_ET":
        return "STRONG_ABOVE_ET" if strong else "WEAK_ABOVE_ET"
    return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    cells=defaultdict(newagg)
    syms=0;events=0;eligible_events=0;forward_outcomes=0;errs=[];skips=Counter()

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

            rp=[0.0]
            for b in h1:
                rp.append(rp[-1]+max(0.0,float(b[2])-float(b[3])))

            for idx,t,hi,ma,mb,prev,sm,obs in ctx:
                events+=1
                if idx<MIN_SCALE_BARS:continue
                scale=(rp[idx]-rp[idx-MIN_SCALE_BARS])/MIN_SCALE_BARS
                if not math.isfinite(scale) or scale<=point*0.5:
                    skips["SKIP_BAD_LAG24_SCALE"]+=1
                    continue

                ep=env_pos(h1,idx)
                g=group_name(bool(obs["strong"]),ep)
                if g is None:
                    skips["SKIP_NOT_ENVELOPE_EXTREME"]+=1
                    continue

                eligible_events+=1
                year=str(datetime.fromtimestamp(int(t),tz=timezone.utc).year)
                event_open=float(h1[idx][1])

                for h in HORIZONS:
                    end_idx=idx+h-1
                    if end_idx>=len(h1):continue
                    r=(float(h1[end_idx][4])-event_open)/scale
                    if not math.isfinite(r):
                        skips["SKIP_NONFINITE_FORWARD"]+=1
                        continue
                    forward_outcomes+=1
                    add(cells[(sym,year,h,g)],r)

        except Exception as e:
            errs.append({"symbol":sym,"error":str(e)})

    rows=[]
    for (sym,year,h,g),x in sorted(cells.items()):
        rows.append({
          "SYMBOL":sym,"YEAR":year,"HORIZON":h,"GROUP":g,
          "N":x["n"],"SUM_RET":f"{x['sum']:.12f}",
          "SUM_ABS":f"{x['abs']:.12f}","UP_N":x["up"]
        })

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D32.csv",rows)

    summary={
      "block":"D32",
      "status":"PASS" if syms>0 and eligible_events>0 and forward_outcomes>0 and not errs else "FAIL",
      "symbols":syms,"events":events,"eligible_events":eligible_events,
      "forward_outcomes":forward_outcomes,
      "errors":len(errs),"skips":dict(skips),
      "horizons_h1_bars":list(HORIZONS),
      "hypothesis":"Strong Block amplifies Envelope mean reversion directional edge",
      "groups":list(GROUPS),
      "effect":{
        "strong_edge":"0.5*(mean_ret(STRONG_BELOW_EB)-mean_ret(STRONG_ABOVE_ET))",
        "weak_edge":"0.5*(mean_ret(WEAK_BELOW_EB)-mean_ret(WEAK_ABOVE_ET))",
        "interaction":"strong_edge-weak_edge",
        "positive_interaction_supports_hypothesis":True
      },
      "scale":"mean H1 high-low range of prior 24 completed H1 bars",
      "contract":{
        "single_hypothesis_frozen_before_run":True,
        "groups_frozen_before_run":True,
        "horizons_frozen_before_run":True,
        "trading_entries_used":False,
        "stops_targets_used":False,
        "pnl_used":False,
        "all_features_known_at_event_time":True,
        "future_filter_used":False,
        "selection_or_optimization":False,
        "promotion_allowed":False,
        "lookahead":False,
        "envelope_status":"RECOVERED_PROXY"
      },
      "interpretation_limit":"D32 tests an interaction discovered from D30/D31 on the same historical universe. It is not independent unseen validation."
    }
    (a.out/"D32.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.out/"D32_ERR.json").write_text(json.dumps(errs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    print("D32",summary["status"],"symbols",syms,"events",events,
          "eligible_events",eligible_events,"forward_outcomes",forward_outcomes,
          "errors",len(errs),"cells",len(rows))
    if summary["status"]!="PASS":raise SystemExit(2)

if __name__=="__main__":
    main()
