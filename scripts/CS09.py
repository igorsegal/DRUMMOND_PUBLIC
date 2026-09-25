#!/usr/bin/env python3
"""
CS09 — all-cross atlas for all 8 frozen Currency Strength features.

Purpose: finish the first-pass study of the whole 8-brick complex without
selecting one feature by eye.

Replication universe: all 27 standard FX crosses except discovery pair EURUSD.
For every target, its own pair is removed from the strength engine.

At the EXACT SAME external-feature timestamps, compare direction with a simple
target-price directional control:
- F1,F2,F3,F4,F6,F7,F8: own 24h momentum sign
- F5 convergence: own 24h mean-reversion sign

Reports PRE2022 and fixed HOLDOUT2022+ separately, and NON_USD / USD_MAJOR /
ALL_27 aggregates. Exploratory atlas only: no trading/PnL, no optimization,
no feature promoted to a trading rule by this block.
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
LB=6;VOL=30;ROLL=252;POST=3;LEAD=6;BREADTH=.50;H=[1,3,6,18]
SPLIT=int(datetime(2022,1,1,tzinfo=timezone.utc).timestamp())
FEATURES=["F1_CROSS","F2_POSTCROSS","F3_OPPOSING_SLOPES","F4_LARGE_DISTANCE",
          "F5_EXTREME_CONVERGENCE","F6_ACCELERATION","F7_LEADERSHIP","F8_BREADTH"]

def avg(x):return statistics.fmean(x) if x else None
def sgn(x):return 1 if x>0 else (-1 if x<0 else 0)
def qtile(xs,q):
    z=sorted(xs)
    if not z:return None
    p=(len(z)-1)*q;lo=int(math.floor(p));hi=int(math.ceil(p))
    return z[lo] if lo==hi else z[lo]+(z[hi]-z[lo])*(p-lo)

def load(root,p):
    h,b=read_xfbar(root/p/(p+"_H4.bin"))
    if h["period_seconds"]!=14400:raise SystemExit(p+" not H4")
    return {int(x[0]):float(x[4]) for x in b}

def rolling_z(series,common):
    n=len(common);one=[0.0]*n
    for i in range(1,n):one[i]=math.log(series[common[i]]/series[common[i-1]])
    ps=[0.0]*(n+1);ps2=[0.0]*(n+1)
    for i,x in enumerate(one):ps[i+1]=ps[i]+x;ps2[i+1]=ps2[i]+x*x
    out=[None]*n
    for i in range(max(VOL,LB),n):
        lo=i-VOL+1;hi=i+1;m=VOL
        sm=ps[hi]-ps[lo];ss=ps2[hi]-ps2[lo]
        var=max(0.0,(ss-sm*sm/m)/(m-1));sd=math.sqrt(var)
        r=math.log(series[common[i]]/series[common[i-LB]])
        out[i]=r/(sd*math.sqrt(LB)) if sd>0 else 0.0
    return out

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
            v=z[p][i];totals[b][i]+=v;counts[b][i]+=1;totals[q][i]-=v;counts[q][i]+=1

    # signed contribution lists for generic breadth, per target computed below
    allrows=[]
    for target in TARGETS:
        b=target[:3];q=target[3:]
        lastsign=0;since=10**9;lead=0
        prevd=None;prevb=None;prevq=None;prevspeed=None
        dhist=[]
        for i in range(start,n-max(H)):
            tv=z[target][i]
            bs=(totals[b][i]-tv)/(counts[b][i]-1)
            qs=(totals[q][i]+tv)/(counts[q][i]-1)
            d=bs-qs;sd=sgn(d)

            cross=0.0
            if lastsign and sd and sd!=lastsign:
                cross=float(sd);since=0;lead=1
            else:
                since+=1
                if sd and sd==lastsign:lead+=1
                elif sd:lead=1
                else:lead=0
            if sd:lastsign=sd

            speed=d-prevd if prevd is not None else 0.0
            db=bs-prevb if prevb is not None else 0.0
            dq=qs-prevq if prevq is not None else 0.0
            accel=speed-prevspeed if prevspeed is not None else 0.0
            dist=abs(d);pd=abs(prevd) if prevd is not None else None
            hist=dhist[max(0,len(dhist)-ROLL):]
            q75=qtile([abs(x) for x in hist],.75) if len(hist)>=50 else None
            q90=qtile([abs(x) for x in hist],.90) if len(hist)>=50 else None

            f2=sd*(dist-pd) if since<=POST and pd is not None and dist>pd else 0.0
            f3=(db-dq) if db*dq<0 else 0.0
            f4=d if q75 is not None and dist>=q75 else 0.0
            f5=-sgn(prevd)*(pd-dist) if q90 is not None and prevd is not None and pd>=q90 and dist<pd else 0.0
            f6=accel
            f7=sd*lead if lead>=LEAD else 0.0

            votes=[]
            for p in PAIRS:
                if p==target:continue
                pb=p[:3];pq=p[3:];v=z[p][i]
                # contribution to base strength, oriented to target price
                if pb==b:votes.append(sgn(v))
                elif pq==b:votes.append(sgn(-v))
                # contribution to quote strength must be inverted for target price
                if pb==q:votes.append(-sgn(v))
                elif pq==q:votes.append(-sgn(-v))
            breadth=avg(votes) if votes else 0.0
            f8=breadth if abs(breadth)>=BREADTH else 0.0

            own=math.log(s[target][common[i]]/s[target][common[i-LB]])
            feats=[cross,f2,f3,f4,f5,f6,f7,f8]
            for j,(name,val) in enumerate(zip(FEATURES,feats)):
                if val==0:continue
                base_sig=-sgn(own) if name=="F5_EXTREME_CONVERGENCE" else sgn(own)
                row={"TARGET":target,"GROUP":"USD_MAJOR" if target in USD_MAJORS else "NON_USD",
                     "TIME":common[i],"PERIOD":"HOLDOUT2022+" if common[i]>=SPLIT else "PRE2022",
                     "FEATURE":name,"CROSS_SIG":sgn(val),"PRICE_SIG":base_sig,
                     "DISAGREE":int(base_sig!=0 and sgn(val)!=base_sig)}
                for h in H:
                    row["F"+str(h)]=math.log(s[target][common[i+h]]/s[target][common[i]])*10000
                allrows.append(row)

            dhist.append(d);prevd=d;prevb=bs;prevq=qs;prevspeed=speed

    target_rows=[]
    for h in H:
        fk="F"+str(h)
        for period in ("PRE2022","HOLDOUT2022+"):
            for feat in FEATURES:
                for target in TARGETS:
                    rr=[r for r in allrows if r["TARGET"]==target and r["PERIOD"]==period and r["FEATURE"]==feat]
                    cv=[r["CROSS_SIG"]*r[fk] for r in rr]
                    pv=[r["PRICE_SIG"]*r[fk] for r in rr if r["PRICE_SIG"]]
                    paired=[(r["CROSS_SIG"]*r[fk],r["PRICE_SIG"]*r[fk]) for r in rr if r["PRICE_SIG"]]
                    target_rows.append({
                        "TARGET":target,"GROUP":"USD_MAJOR" if target in USD_MAJORS else "NON_USD",
                        "HORIZON_H4":h,"PERIOD":period,"FEATURE":feat,"N":len(rr),
                        "CROSS_MEAN_BPS":avg(cv),"CROSS_ACC":sum(x>0 for x in cv)/len(cv) if cv else None,
                        "PRICE_MEAN_BPS":avg(pv),"PRICE_ACC":sum(x>0 for x in pv)/len(pv) if pv else None,
                        "DELTA_CROSS_MINUS_PRICE_BPS":avg([c-p for c,p in paired]) if paired else None,
                        "DISAGREE_N":sum(r["DISAGREE"] for r in rr)
                    })

    agg=[]
    for period in ("PRE2022","HOLDOUT2022+"):
      for h in H:
       for feat in FEATURES:
        for group,tgts in [("NON_USD",NON_USD),("USD_MAJOR",USD_MAJORS),("ALL_27",TARGETS)]:
            rr=[r for r in target_rows if r["PERIOD"]==period and r["HORIZON_H4"]==h and r["FEATURE"]==feat and r["TARGET"] in tgts]
            vv=[r for r in rr if r["CROSS_MEAN_BPS"] is not None and r["DELTA_CROSS_MINUS_PRICE_BPS"] is not None]
            agg.append({
              "PERIOD":period,"HORIZON_H4":h,"FEATURE":feat,"GROUP":group,"TARGETS":len(vv),
              "CROSS_POSITIVE":sum(r["CROSS_MEAN_BPS"]>0 for r in vv),
              "CROSS_GT_PRICE":sum(r["DELTA_CROSS_MINUS_PRICE_BPS"]>0 for r in vv),
              "MEAN_CROSS_BPS":avg([r["CROSS_MEAN_BPS"] for r in vv]),
              "MEAN_PRICE_BPS":avg([r["PRICE_MEAN_BPS"] for r in vv]),
              "MEAN_DELTA_BPS":avg([r["DELTA_CROSS_MINUS_PRICE_BPS"] for r in vv]),
              "TOTAL_EVENTS":sum(r["N"] for r in vv),
              "TOTAL_DISAGREE":sum(r["DISAGREE_N"] for r in vv)
            })

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";");w.writeheader();w.writerows(data)
    write("CS09_TARGETS.csv",target_rows);write("CS09_AGGREGATE.csv",agg)

    meta={"block":"CS09","status":"PASS","features":FEATURES,"targets":TARGETS,
          "contract":{"discovery_pair_excluded":"EURUSD","same_event_price_control":True,
                      "f5_control":"own24_mean_reversion","other_controls":"own24_momentum",
                      "parameters_frozen":True,"feature_selection_for_trading":False,
                      "parameter_optimization":False,"trading_or_pnl":False}}
    (a.out/"CS09.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=["CURRENCY STRENGTH CS09 — 8-FEATURE ALL-CROSS ATLAS","STATUS: PASS",
           "DISCOVERY PAIR EXCLUDED: EURUSD","TARGETS: 27",
           "HOLDOUT: 2022-01-01 onward","SAME-EVENT PRICE CONTROLS: YES",
           "OPTIMIZATION: NO","TRADING/PNL: NO",""]
    for h in H:
        lines.append("H"+str(h)+" HOLDOUT ALL_27:")
        for feat in FEATURES:
            r=next(x for x in agg if x["PERIOD"]=="HOLDOUT2022+" and x["HORIZON_H4"]==h and x["FEATURE"]==feat and x["GROUP"]=="ALL_27")
            lines.append(f" {feat}: POS={r['CROSS_POSITIVE']}/{r['TARGETS']} GT_PRICE={r['CROSS_GT_PRICE']}/{r['TARGETS']} CROSS={r['MEAN_CROSS_BPS']:+.4f} PRICE={r['MEAN_PRICE_BPS']:+.4f} DELTA={r['MEAN_DELTA_BPS']:+.4f} N={r['TOTAL_EVENTS']}")
        lines.append("")
    (a.out/"CS09.txt").write_text("\n".join(lines)+"\n",encoding="utf-8");print("\n".join(lines))
if __name__=="__main__":main()
