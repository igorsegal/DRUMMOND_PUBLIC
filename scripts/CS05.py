#!/usr/bin/env python3
"""
CS05 — cross-pair falsification of frozen Currency Strength F5.

Tests the already-frozen volatility-normalized feature:
    extreme EUR/USD-style strength divergence -> first convergence
on six independent target pairs:
    GBPUSD, AUDUSD, NZDUSD, USDCHF, USDJPY, USDCAD

For EACH target pair:
- rebuild 8-currency strength from the same 28 H4 crosses;
- exclude the target pair entirely from both of its currencies' strength;
- use the same frozen parameters as CS01/CS02:
    24h return = 6 H4 bars
    causal pair-vol normalization = 30 H4 bars
    causal extreme threshold = 90th percentile of prior 252 H4 abs strength gaps
- F5 signal direction = opposite the prior extreme gap when the gap starts shrinking;
- compare with a matched price-only F5 built from that target's own 24h return
  with the SAME causal 90th-percentile convergence rule;
- fixed temporal holdout = 2022-01-01 onward;
- future horizons = 1,3,6,18 H4 bars.

No trading/PnL. No parameter fitting. No target selection.
"""
import argparse,csv,json,math,statistics
from datetime import datetime,timezone
from pathlib import Path
from drummond_replay01 import read_xfbar

CURS=["AUD","CAD","CHF","EUR","GBP","JPY","NZD","USD"]
PAIRS=[
"AUDCAD","AUDCHF","AUDJPY","AUDNZD","AUDUSD",
"CADCHF","CADJPY","CHFJPY",
"EURAUD","EURCAD","EURCHF","EURGBP","EURJPY","EURNZD","EURUSD",
"GBPAUD","GBPCAD","GBPCHF","GBPJPY","GBPNZD","GBPUSD",
"NZDCAD","NZDCHF","NZDJPY","NZDUSD",
"USDCAD","USDCHF","USDJPY"
]
TARGETS=["GBPUSD","AUDUSD","NZDUSD","USDCHF","USDJPY","USDCAD"]
LB=6
VOL=30
ROLL=252
H=[1,3,6,18]
SPLIT=int(datetime(2022,1,1,tzinfo=timezone.utc).timestamp())

def avg(xs): return statistics.fmean(xs) if xs else None
def sgn(x): return 1 if x>0 else (-1 if x<0 else 0)

def qtile(xs,q):
    if not xs:return None
    z=sorted(xs)
    p=(len(z)-1)*q
    lo=int(math.floor(p)); hi=int(math.ceil(p))
    if lo==hi:return z[lo]
    return z[lo]+(z[hi]-z[lo])*(p-lo)

def sd(xs):
    return statistics.stdev(xs) if len(xs)>=2 else None

def load(root,p):
    path=root/p/(p+"_H4.bin")
    if not path.exists(): raise SystemExit("missing "+str(path))
    h,b=read_xfbar(path)
    if h["period_seconds"]!=14400: raise SystemExit(p+" not H4")
    return {int(x[0]):float(x[4]) for x in b}

def make_f5_states(target,s):
    base=target[:3]; quote=target[3:]
    common=sorted(set.intersection(*(set(s[p]) for p in PAIRS)))
    start=max(VOL,LB)
    rows=[]
    gap_hist=[]
    own_hist=[]
    prev_gap=None
    prev_own=None

    for i in range(start,len(common)):
        t=common[i]; t0=common[i-LB]
        strengths={c:[] for c in CURS}

        for p in PAIRS:
            if p==target:
                continue
            b=p[:3]; q=p[3:]
            r=math.log(s[p][t]/s[p][t0])

            one=[]
            for j in range(i-VOL+1,i+1):
                ta=common[j-1]; tb=common[j]
                one.append(math.log(s[p][tb]/s[p][ta]))
            v=sd(one)
            z=r/(v*math.sqrt(LB)) if v and v>0 else 0.0
            strengths[b].append(z)
            strengths[q].append(-z)

        st={c:avg(strengths[c]) for c in CURS}
        if st[base] is None or st[quote] is None:
            continue

        gap=st[base]-st[quote]
        own=math.log(s[target][t]/s[target][t0])

        gh=gap_hist[max(0,len(gap_hist)-ROLL):]
        oh=own_hist[max(0,len(own_hist)-ROLL):]
        gq90=qtile([abs(x) for x in gh],.90) if len(gh)>=50 else None
        oq90=qtile([abs(x) for x in oh],.90) if len(oh)>=50 else None

        cross_f5=0.0
        if gq90 is not None and prev_gap is not None:
            pd=abs(prev_gap); d=abs(gap)
            if pd>=gq90 and d<pd:
                cross_f5=-sgn(prev_gap)*(pd-d)

        price_f5=0.0
        if oq90 is not None and prev_own is not None:
            pd=abs(prev_own); d=abs(own)
            if pd>=oq90 and d<pd:
                price_f5=-sgn(prev_own)*(pd-d)

        rows.append({
            "time":t,
            "gap":gap,
            "own":own,
            "cross_f5":cross_f5,
            "price_f5":price_f5
        })
        gap_hist.append(gap)
        own_hist.append(own)
        prev_gap=gap
        prev_own=own

    return common,rows

def enrich(target,common,rows,s):
    pos={t:i for i,t in enumerate(common)}
    out=[]
    for r in rows:
        i=pos[r["time"]]
        if i+max(H)>=len(common): continue
        z=dict(r)
        ok=True
        for h in H:
            t2=common[i+h]
            if t2 not in s[target]: ok=False; break
            z["f"+str(h)]=math.log(s[target][t2]/s[target][r["time"]])
        if ok: out.append(z)
    return out

def event_metric(rr,key,h):
    fk="f"+str(h)
    ev=[r for r in rr if r[key]!=0]
    signed=[sgn(r[key])*r[fk]*10000 for r in ev]
    return {
        "n":len(ev),
        "mean_signed_bps":avg(signed),
        "accuracy":sum(x>0 for x in signed)/len(signed) if signed else None,
        "mean_abs_future_bps":avg([abs(r[fk])*10000 for r in ev])
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args(); a.out.mkdir(parents=True,exist_ok=True)

    s={p:load(a.root,p) for p in PAIRS}
    rows_out=[]
    yearly=[]
    target_meta={}

    for target in TARGETS:
        common,states=make_f5_states(target,s)
        data=enrich(target,common,states,s)
        target_meta[target]={
            "common_bars":len(common),
            "observations":len(data),
            "first_time":common[0],
            "last_time":common[-1]
        }

        for h in H:
            for period,pred in [
                ("PRE2022",lambda r:r["time"]<SPLIT),
                ("HOLDOUT2022+",lambda r:r["time"]>=SPLIT),
                ("ALL",lambda r:True)
            ]:
                sub=[r for r in data if pred(r)]
                cm=event_metric(sub,"cross_f5",h)
                pm=event_metric(sub,"price_f5",h)
                rows_out.append({
                    "TARGET":target,"HORIZON_H4":h,"PERIOD":period,
                    "CROSS_N":cm["n"],
                    "CROSS_MEAN_SIGNED_BPS":cm["mean_signed_bps"],
                    "CROSS_ACCURACY":cm["accuracy"],
                    "CROSS_MEAN_ABS_FUTURE_BPS":cm["mean_abs_future_bps"],
                    "PRICE_N":pm["n"],
                    "PRICE_MEAN_SIGNED_BPS":pm["mean_signed_bps"],
                    "PRICE_ACCURACY":pm["accuracy"],
                    "PRICE_MEAN_ABS_FUTURE_BPS":pm["mean_abs_future_bps"],
                    "DELTA_CROSS_MINUS_PRICE_BPS":(
                        cm["mean_signed_bps"]-pm["mean_signed_bps"]
                        if cm["mean_signed_bps"] is not None and pm["mean_signed_bps"] is not None else None
                    )
                })

            years=sorted({datetime.fromtimestamp(r["time"],tz=timezone.utc).year for r in data})
            for y in years:
                sub=[r for r in data if datetime.fromtimestamp(r["time"],tz=timezone.utc).year==y]
                cm=event_metric(sub,"cross_f5",h)
                pm=event_metric(sub,"price_f5",h)
                yearly.append({
                    "TARGET":target,"HORIZON_H4":h,"YEAR":y,
                    "CROSS_N":cm["n"],
                    "CROSS_MEAN_SIGNED_BPS":cm["mean_signed_bps"],
                    "PRICE_N":pm["n"],
                    "PRICE_MEAN_SIGNED_BPS":pm["mean_signed_bps"],
                    "DELTA_CROSS_MINUS_PRICE_BPS":(
                        cm["mean_signed_bps"]-pm["mean_signed_bps"]
                        if cm["mean_signed_bps"] is not None and pm["mean_signed_bps"] is not None else None
                    )
                })

    # Aggregate holdout across all six targets.
    aggregate=[]
    for h in H:
        rr=[r for r in rows_out if r["HORIZON_H4"]==h and r["PERIOD"]=="HOLDOUT2022+"]
        valid=[r for r in rr if r["DELTA_CROSS_MINUS_PRICE_BPS"] is not None]
        aggregate.append({
            "HORIZON_H4":h,
            "TARGETS":len(valid),
            "TARGETS_CROSS_POSITIVE":sum(r["CROSS_MEAN_SIGNED_BPS"]>0 for r in valid),
            "TARGETS_CROSS_GT_PRICE":sum(r["DELTA_CROSS_MINUS_PRICE_BPS"]>0 for r in valid),
            "EQUAL_PAIR_MEAN_CROSS_BPS":avg([r["CROSS_MEAN_SIGNED_BPS"] for r in valid]),
            "EQUAL_PAIR_MEAN_PRICE_BPS":avg([r["PRICE_MEAN_SIGNED_BPS"] for r in valid]),
            "EQUAL_PAIR_MEAN_DELTA_BPS":avg([r["DELTA_CROSS_MINUS_PRICE_BPS"] for r in valid]),
            "TOTAL_CROSS_EVENTS":sum(r["CROSS_N"] for r in valid),
            "TOTAL_PRICE_EVENTS":sum(r["PRICE_N"] for r in valid)
        })

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";")
            w.writeheader(); w.writerows(data)

    write("CS05_TARGETS.csv",rows_out)
    write("CS05_YEARLY.csv",yearly)
    write("CS05_AGGREGATE.csv",aggregate)

    meta={
        "block":"CS05","status":"PASS",
        "targets":TARGETS,
        "target_meta":target_meta,
        "aggregate_holdout":aggregate,
        "contract":{
            "feature":"VOL_F5_EXTREME_CONVERGENCE",
            "feature_frozen_before_cross_pair_test":True,
            "target_pair_excluded_from_strength":True,
            "lookback_h4":LB,
            "pair_vol_window_h4":VOL,
            "extreme_percentile":0.90,
            "extreme_rolling_window_h4":ROLL,
            "holdout":"2022-01-01 onward",
            "trading_or_pnl":False,
            "parameter_optimization":False,
            "target_selection":False
        }
    }
    (a.out/"CS05.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
        "CURRENCY STRENGTH CS05 — F5 CROSS-PAIR FALSIFICATION",
        "STATUS: PASS",
        "TARGETS: "+", ".join(TARGETS),
        "HOLDOUT: 2022-01-01 onward",
        "FEATURE: VOL F5 EXTREME DIVERGENCE -> CONVERGENCE",
        "TARGET_PAIR_EXCLUDED_FROM_STRENGTH: YES",
        "TRADING/PNL: NO",
        "OPTIMIZATION: NO",
        ""
    ]
    for arow in aggregate:
        lines.append(
            f"H{arow['HORIZON_H4']}: "
            f"POS={arow['TARGETS_CROSS_POSITIVE']}/{arow['TARGETS']} "
            f"GT_PRICE={arow['TARGETS_CROSS_GT_PRICE']}/{arow['TARGETS']} "
            f"CROSS={arow['EQUAL_PAIR_MEAN_CROSS_BPS']:+.4f}bps "
            f"PRICE={arow['EQUAL_PAIR_MEAN_PRICE_BPS']:+.4f}bps "
            f"DELTA={arow['EQUAL_PAIR_MEAN_DELTA_BPS']:+.4f}bps"
        )
        for r in [x for x in rows_out if x["HORIZON_H4"]==arow["HORIZON_H4"] and x["PERIOD"]=="HOLDOUT2022+"]:
            lines.append(
                f"  {r['TARGET']}: N={r['CROSS_N']} "
                f"CROSS={r['CROSS_MEAN_SIGNED_BPS']:+.4f} "
                f"PRICE={r['PRICE_MEAN_SIGNED_BPS']:+.4f} "
                f"DELTA={r['DELTA_CROSS_MINUS_PRICE_BPS']:+.4f} "
                f"ACC={r['CROSS_ACCURACY']:.4f}"
            )
        lines.append("")
    (a.out/"CS05.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
