#!/usr/bin/env python3
"""
CS06 — all-cross replication of frozen VOL-F5.

This is a stricter falsification step after CS05:
- evaluate EVERY one of the 27 standard FX crosses except EURUSD, where F5 was
  first noticed;
- for each target, remove that target pair from the currency-strength engine;
- keep ALL CS05 parameters frozen;
- separately report the 21 NON-USD crosses as the cleanest replication set.

No pair selection. No optimization. No trading/PnL.
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
DISCOVERY="EURUSD"
TARGETS=[p for p in PAIRS if p!=DISCOVERY]
USD_MAJORS=["GBPUSD","AUDUSD","NZDUSD","USDCHF","USDJPY","USDCAD"]
NON_USD=[p for p in TARGETS if p not in USD_MAJORS]
LB=6; VOL=30; ROLL=252; H=[1,3,6,18]
SPLIT=int(datetime(2022,1,1,tzinfo=timezone.utc).timestamp())

def avg(x): return statistics.fmean(x) if x else None
def sgn(x): return 1 if x>0 else (-1 if x<0 else 0)
def qtile(xs,q):
    z=sorted(xs)
    if not z:return None
    p=(len(z)-1)*q;lo=int(math.floor(p));hi=int(math.ceil(p))
    return z[lo] if lo==hi else z[lo]+(z[hi]-z[lo])*(p-lo)

def load(root,p):
    path=root/p/(p+"_H4.bin")
    h,b=read_xfbar(path)
    if h["period_seconds"]!=14400: raise SystemExit(p+" not H4")
    return {int(x[0]):float(x[4]) for x in b}

def rolling_z(series,common):
    n=len(common)
    one=[0.0]*n
    for i in range(1,n):
        one[i]=math.log(series[common[i]]/series[common[i-1]])
    ps=[0.0]*(n+1); ps2=[0.0]*(n+1)
    for i,x in enumerate(one):
        ps[i+1]=ps[i]+x; ps2[i+1]=ps2[i]+x*x
    z=[None]*n
    for i in range(max(VOL,LB),n):
        lo=i-VOL+1; hi=i+1; m=VOL
        sm=ps[hi]-ps[lo]; ss=ps2[hi]-ps2[lo]
        var=(ss-sm*sm/m)/(m-1) if m>1 else 0.0
        sd=math.sqrt(max(0.0,var))
        r=math.log(series[common[i]]/series[common[i-LB]])
        z[i]=r/(sd*math.sqrt(LB)) if sd>0 else 0.0
    return z

def event_metric(events,common,series,h,start_holdout):
    vals=[]; n=0
    for i,sig in events:
        if start_holdout and common[i]<SPLIT: continue
        if (not start_holdout) and common[i]>=SPLIT: continue
        if i+h>=len(common): continue
        fut=math.log(series[common[i+h]]/series[common[i]])
        vals.append(sgn(sig)*fut*10000); n+=1
    return {"n":n,"mean":avg(vals),
            "acc":sum(x>0 for x in vals)/len(vals) if vals else None}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    s={p:load(a.root,p) for p in PAIRS}
    common=sorted(set.intersection(*(set(s[p]) for p in PAIRS)))
    n=len(common); start=max(VOL,LB)
    z={p:rolling_z(s[p],common) for p in PAIRS}

    # total currency signed z contribution and count at each bar
    totals={c:[0.0]*n for c in CURS}
    counts={c:[0]*n for c in CURS}
    for p in PAIRS:
        b=p[:3];q=p[3:]
        for i in range(start,n):
            v=z[p][i]
            totals[b][i]+=v;counts[b][i]+=1
            totals[q][i]-=v;counts[q][i]+=1

    results=[]; years=[]

    for target in TARGETS:
        b=target[:3];q=target[3:]
        gaps=[]; own=[]
        for i in range(start,n):
            tv=z[target][i]
            bs=(totals[b][i]-tv)/(counts[b][i]-1)
            qs=(totals[q][i]+tv)/(counts[q][i]-1)
            gaps.append(bs-qs)
            own.append(math.log(s[target][common[i]]/s[target][common[i-LB]]))

        cross_events=[];price_events=[]
        gh=[];oh=[]
        prevg=None;prevo=None
        for j,(g,o) in enumerate(zip(gaps,own)):
            i=start+j
            gq=qtile([abs(x) for x in gh[max(0,len(gh)-ROLL):]],.90) if len(gh)>=50 else None
            oq=qtile([abs(x) for x in oh[max(0,len(oh)-ROLL):]],.90) if len(oh)>=50 else None
            if gq is not None and prevg is not None and abs(prevg)>=gq and abs(g)<abs(prevg):
                sig=-sgn(prevg)*(abs(prevg)-abs(g))
                cross_events.append((i,sig))
            if oq is not None and prevo is not None and abs(prevo)>=oq and abs(o)<abs(prevo):
                sig=-sgn(prevo)*(abs(prevo)-abs(o))
                price_events.append((i,sig))
            gh.append(g);oh.append(o);prevg=g;prevo=o

        for h in H:
            for period,hold in [("PRE2022",False),("HOLDOUT2022+",True)]:
                cm=event_metric(cross_events,common,s[target],h,hold)
                pm=event_metric(price_events,common,s[target],h,hold)
                results.append({
                    "TARGET":target,
                    "GROUP":"USD_MAJOR" if target in USD_MAJORS else "NON_USD",
                    "HORIZON_H4":h,"PERIOD":period,
                    "CROSS_N":cm["n"],"CROSS_MEAN_SIGNED_BPS":cm["mean"],"CROSS_ACCURACY":cm["acc"],
                    "PRICE_N":pm["n"],"PRICE_MEAN_SIGNED_BPS":pm["mean"],"PRICE_ACCURACY":pm["acc"],
                    "DELTA_CROSS_MINUS_PRICE_BPS":cm["mean"]-pm["mean"] if cm["mean"] is not None and pm["mean"] is not None else None
                })

            for y in sorted({datetime.fromtimestamp(t,tz=timezone.utc).year for t in common}):
                ce=[(i,sig) for i,sig in cross_events if datetime.fromtimestamp(common[i],tz=timezone.utc).year==y]
                pe=[(i,sig) for i,sig in price_events if datetime.fromtimestamp(common[i],tz=timezone.utc).year==y]
                def em(ev):
                    vals=[]
                    for i,sig in ev:
                        if i+h>=n:continue
                        vals.append(sgn(sig)*math.log(s[target][common[i+h]]/s[target][common[i]])*10000)
                    return len(vals),avg(vals)
                cn,cm=em(ce);pn,pm=em(pe)
                years.append({"TARGET":target,"HORIZON_H4":h,"YEAR":y,
                              "CROSS_N":cn,"CROSS_MEAN_SIGNED_BPS":cm,
                              "PRICE_N":pn,"PRICE_MEAN_SIGNED_BPS":pm,
                              "DELTA_CROSS_MINUS_PRICE_BPS":cm-pm if cm is not None and pm is not None else None})

    agg=[]
    for h in H:
        for group,tgts in [("NON_USD",NON_USD),("USD_MAJOR",USD_MAJORS),("ALL_27",TARGETS)]:
            rr=[r for r in results if r["PERIOD"]=="HOLDOUT2022+" and r["HORIZON_H4"]==h and r["TARGET"] in tgts]
            agg.append({
                "GROUP":group,"HORIZON_H4":h,"TARGETS":len(rr),
                "CROSS_POSITIVE":sum(r["CROSS_MEAN_SIGNED_BPS"]>0 for r in rr),
                "CROSS_GT_PRICE":sum(r["DELTA_CROSS_MINUS_PRICE_BPS"]>0 for r in rr),
                "MEAN_CROSS_BPS":avg([r["CROSS_MEAN_SIGNED_BPS"] for r in rr]),
                "MEAN_PRICE_BPS":avg([r["PRICE_MEAN_SIGNED_BPS"] for r in rr]),
                "MEAN_DELTA_BPS":avg([r["DELTA_CROSS_MINUS_PRICE_BPS"] for r in rr]),
                "TOTAL_CROSS_EVENTS":sum(r["CROSS_N"] for r in rr)
            })

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";")
            w.writeheader();w.writerows(data)
    write("CS06_TARGETS.csv",results);write("CS06_AGGREGATE.csv",agg);write("CS06_YEARLY.csv",years)

    meta={"block":"CS06","status":"PASS","discovery_pair_excluded":DISCOVERY,
          "targets":TARGETS,"non_usd_replication_targets":NON_USD,
          "aggregate_holdout":agg,
          "contract":{"feature":"VOL_F5","parameters_frozen":True,
                      "target_pair_excluded_from_strength":True,
                      "target_selection":False,"parameter_optimization":False,
                      "trading_or_pnl":False,"holdout":"2022-01-01 onward"}}
    (a.out/"CS06.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=["CURRENCY STRENGTH CS06 — ALL-CROSS F5 REPLICATION","STATUS: PASS",
           "DISCOVERY PAIR EXCLUDED: EURUSD","TARGETS: 27","NON-USD REPLICATION TARGETS: 21",
           "HOLDOUT: 2022-01-01 onward","OPTIMIZATION: NO","TRADING/PNL: NO",""]
    for h in H:
        for group in ("NON_USD","USD_MAJOR","ALL_27"):
            r=next(x for x in agg if x["GROUP"]==group and x["HORIZON_H4"]==h)
            lines.append(f"H{h} {group}: POS={r['CROSS_POSITIVE']}/{r['TARGETS']} GT_PRICE={r['CROSS_GT_PRICE']}/{r['TARGETS']} CROSS={r['MEAN_CROSS_BPS']:+.4f} PRICE={r['MEAN_PRICE_BPS']:+.4f} DELTA={r['MEAN_DELTA_BPS']:+.4f} N={r['TOTAL_CROSS_EVENTS']}")
        lines.append("")
    (a.out/"CS06.txt").write_text("\n".join(lines)+"\n",encoding="utf-8");print("\n".join(lines))
if __name__=="__main__":main()
