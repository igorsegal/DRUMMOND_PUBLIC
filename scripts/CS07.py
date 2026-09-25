#!/usr/bin/env python3
"""
CS07 — decompose the USD-major F5 effect.

After CS06 showed that the frozen F5 is not universally incremental across
non-USD crosses but is more consistent on USD majors, this block asks WHAT
carries that effect.

For each of six replication USD majors:
- FULL_GAP_F5: base-strength minus quote-strength (existing CS05 feature)
- USD_ONLY_F5: target-excluded USD strength alone
- OTHER_ONLY_F5: target-excluded non-USD currency strength alone
- PRICE_F5: matched target-price-only control

All parameters remain frozen: H4, 6-bar lookback, 30-bar vol normalization,
90th percentile of prior 252 abs values, first convergence after extreme.
No trading/PnL. No optimization.
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
LB=6;VOL=30;ROLL=252;H=[1,3,6,18]
SPLIT=int(datetime(2022,1,1,tzinfo=timezone.utc).timestamp())

def avg(x): return statistics.fmean(x) if x else None
def sgn(x): return 1 if x>0 else (-1 if x<0 else 0)
def qtile(xs,q):
    z=sorted(xs)
    if not z:return None
    p=(len(z)-1)*q;lo=int(math.floor(p));hi=int(math.ceil(p))
    return z[lo] if lo==hi else z[lo]+(z[hi]-z[lo])*(p-lo)

def load(root,p):
    h,b=read_xfbar(root/p/(p+"_H4.bin"))
    if h["period_seconds"]!=14400: raise SystemExit(p+" not H4")
    return {int(x[0]):float(x[4]) for x in b}

def rolling_z(series,common):
    n=len(common);one=[0.0]*n
    for i in range(1,n):one[i]=math.log(series[common[i]]/series[common[i-1]])
    ps=[0.0]*(n+1);ps2=[0.0]*(n+1)
    for i,x in enumerate(one):
        ps[i+1]=ps[i]+x;ps2[i+1]=ps2[i]+x*x
    out=[None]*n
    for i in range(max(VOL,LB),n):
        lo=i-VOL+1;hi=i+1;m=VOL
        sm=ps[hi]-ps[lo];ss=ps2[hi]-ps2[lo]
        var=max(0.0,(ss-sm*sm/m)/(m-1))
        sd=math.sqrt(var)
        r=math.log(series[common[i]]/series[common[i-LB]])
        out[i]=r/(sd*math.sqrt(LB)) if sd>0 else 0.0
    return out

def f5_events(values,start,orient=1):
    hist=[];prev=None;ev=[]
    for j,v in enumerate(values):
        i=start+j
        q=qtile([abs(x) for x in hist[max(0,len(hist)-ROLL):]],.90) if len(hist)>=50 else None
        if q is not None and prev is not None and abs(prev)>=q and abs(v)<abs(prev):
            raw=-sgn(prev)*(abs(prev)-abs(v))
            ev.append((i,orient*raw))
        hist.append(v);prev=v
    return ev

def metric(ev,common,series,h,holdout):
    vals=[]
    for i,sig in ev:
        if holdout and common[i]<SPLIT:continue
        if (not holdout) and common[i]>=SPLIT:continue
        if i+h>=len(common):continue
        fut=math.log(series[common[i+h]]/series[common[i]])
        vals.append(sgn(sig)*fut*10000)
    return {"n":len(vals),"mean":avg(vals),
            "acc":sum(x>0 for x in vals)/len(vals) if vals else None}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    s={p:load(a.root,p) for p in PAIRS}
    common=sorted(set.intersection(*(set(s[p]) for p in PAIRS)))
    n=len(common);start=max(VOL,LB)
    z={p:rolling_z(s[p],common) for p in PAIRS}

    totals={c:[0.0]*n for c in CURS};counts={c:[0]*n for c in CURS}
    for p in PAIRS:
        b=p[:3];q=p[3:]
        for i in range(start,n):
            v=z[p][i]
            totals[b][i]+=v;counts[b][i]+=1
            totals[q][i]-=v;counts[q][i]+=1

    out=[]
    for target in TARGETS:
        b=target[:3];q=target[3:]
        other=q if b=="USD" else b
        usd_is_base=(b=="USD")
        full=[];usd=[];oth=[];price=[]
        for i in range(start,n):
            tv=z[target][i]
            bs=(totals[b][i]-tv)/(counts[b][i]-1)
            qs=(totals[q][i]+tv)/(counts[q][i]-1)
            us=(totals["USD"][i]-(tv if b=="USD" else -tv))/(counts["USD"][i]-1)
            os=(totals[other][i]-(tv if b==other else -tv))/(counts[other][i]-1)
            full.append(bs-qs);usd.append(us);oth.append(os)
            price.append(math.log(s[target][common[i]]/s[target][common[i-LB]]))

        evs={
          "FULL_GAP_F5":f5_events(full,start,1),
          # Currency strengthening raises pair if currency is base, lowers if quote.
          # F5 expects reversal of prior strength, hence orientation below.
          "USD_ONLY_F5":f5_events(usd,start,-1 if usd_is_base else 1),
          "OTHER_ONLY_F5":f5_events(oth,start,-1 if not usd_is_base else 1),
          "PRICE_F5":f5_events(price,start,1)
        }
        for h in H:
            for period,hold in [("PRE2022",False),("HOLDOUT2022+",True)]:
                for model,ev in evs.items():
                    m=metric(ev,common,s[target],h,hold)
                    out.append({"TARGET":target,"HORIZON_H4":h,"PERIOD":period,
                                "MODEL":model,"N":m["n"],
                                "MEAN_SIGNED_BPS":m["mean"],"ACCURACY":m["acc"]})

    agg=[]
    for h in H:
        for model in ["FULL_GAP_F5","USD_ONLY_F5","OTHER_ONLY_F5","PRICE_F5"]:
            rr=[r for r in out if r["HORIZON_H4"]==h and r["PERIOD"]=="HOLDOUT2022+" and r["MODEL"]==model]
            agg.append({"HORIZON_H4":h,"MODEL":model,"TARGETS":len(rr),
                        "TARGETS_POSITIVE":sum(r["MEAN_SIGNED_BPS"]>0 for r in rr),
                        "EQUAL_PAIR_MEAN_BPS":avg([r["MEAN_SIGNED_BPS"] for r in rr]),
                        "EQUAL_PAIR_MEAN_ACCURACY":avg([r["ACCURACY"] for r in rr]),
                        "TOTAL_EVENTS":sum(r["N"] for r in rr)})

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";")
            w.writeheader();w.writerows(data)
    write("CS07_TARGETS.csv",out);write("CS07_AGGREGATE.csv",agg)

    meta={"block":"CS07","status":"PASS","targets":TARGETS,"aggregate_holdout":agg,
          "contract":{"parameters_frozen":True,"target_pair_excluded_from_strength":True,
                      "hypothesis":"decompose USD-major F5 into USD-only vs other-currency-only",
                      "parameter_optimization":False,"trading_or_pnl":False}}
    (a.out/"CS07.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=["CURRENCY STRENGTH CS07 — USD-FACTOR DECOMPOSITION","STATUS: PASS",
           "TARGETS: "+", ".join(TARGETS),"HOLDOUT: 2022-01-01 onward",
           "OPTIMIZATION: NO","TRADING/PNL: NO",""]
    for h in H:
        lines.append("H"+str(h)+":")
        for model in ["FULL_GAP_F5","USD_ONLY_F5","OTHER_ONLY_F5","PRICE_F5"]:
            r=next(x for x in agg if x["HORIZON_H4"]==h and x["MODEL"]==model)
            lines.append(f" {model}: POS={r['TARGETS_POSITIVE']}/{r['TARGETS']} MEAN={r['EQUAL_PAIR_MEAN_BPS']:+.4f}bps ACC={r['EQUAL_PAIR_MEAN_ACCURACY']:.4f} N={r['TOTAL_EVENTS']}")
        lines.append("")
    (a.out/"CS07.txt").write_text("\n".join(lines)+"\n",encoding="utf-8");print("\n".join(lines))
if __name__=="__main__":main()
