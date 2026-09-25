#!/usr/bin/env python3
"""
CS10 — H1 cross-market lead/lag falsification.

New hypothesis after the first Currency Strength signal family largely reduced
to price effects:
    does a CHANGE in target-excluded external currency-strength gap lead the
    target pair itself?

For each of 27 replication pairs (EURUSD excluded):
- build 8-currency H1 strength from all 28 crosses;
- exclude the target pair from its base/quote currencies;
- strength lookback = 24 H1 bars;
- vol normalization window = 120 H1 bars (H1-scaled analogue of H4 30 bars);
- external signal = sign(change in base-minus-quote strength gap);
- price control on the SAME timestamps = sign(target's latest H1 return);
- critical subset = DISAGREE, where external and own-price directions oppose;
- future horizons = 1,4,12,24 H1 bars.

If external strength really leads price, it should win the disagreement test.
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
DISCOVERY="EURUSD"
TARGETS=[p for p in PAIRS if p!=DISCOVERY]
USD_MAJORS=["GBPUSD","AUDUSD","NZDUSD","USDCHF","USDJPY","USDCAD"]
NON_USD=[p for p in TARGETS if p not in USD_MAJORS]
LB=24;VOL=120;H=[1,4,12,24]
SPLIT=int(datetime(2022,1,1,tzinfo=timezone.utc).timestamp())

def avg(x):return statistics.fmean(x) if x else None
def sgn(x):return 1 if x>0 else (-1 if x<0 else 0)

def load(root,p):
    h,b=read_xfbar(root/p/(p+"_H1.bin"))
    if h["period_seconds"]!=3600:raise SystemExit(p+" not H1")
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

    detail=[]
    for target in TARGETS:
        b=target[:3];q=target[3:];prev_gap=None
        for i in range(start,n-max(H)):
            tv=z[target][i]
            bs=(totals[b][i]-tv)/(counts[b][i]-1)
            qs=(totals[q][i]+tv)/(counts[q][i]-1)
            gap=bs-qs
            if prev_gap is not None:
                ext=sgn(gap-prev_gap)
                own1=sgn(math.log(s[target][common[i]]/s[target][common[i-1]]))
                if ext:
                    r={"TARGET":target,"GROUP":"USD_MAJOR" if target in USD_MAJORS else "NON_USD",
                       "TIME":common[i],"PERIOD":"HOLDOUT2022+" if common[i]>=SPLIT else "PRE2022",
                       "EXT_SIG":ext,"PRICE_SIG":own1,
                       "DISAGREE":int(own1!=0 and ext!=own1)}
                    for h in H:
                        r["F"+str(h)]=math.log(s[target][common[i+h]]/s[target][common[i]])*10000
                    detail.append(r)
            prev_gap=gap

    targets=[]
    for period in ("PRE2022","HOLDOUT2022+"):
      for h in H:
       fk="F"+str(h)
       for subset,pred in [("ALL",lambda r:True),("DISAGREE",lambda r:r["DISAGREE"]==1)]:
        for target in TARGETS:
            rr=[r for r in detail if r["TARGET"]==target and r["PERIOD"]==period and pred(r)]
            cv=[r["EXT_SIG"]*r[fk] for r in rr]
            pv=[r["PRICE_SIG"]*r[fk] for r in rr if r["PRICE_SIG"]]
            paired=[(r["EXT_SIG"]*r[fk],r["PRICE_SIG"]*r[fk]) for r in rr if r["PRICE_SIG"]]
            targets.append({
              "TARGET":target,"GROUP":"USD_MAJOR" if target in USD_MAJORS else "NON_USD",
              "PERIOD":period,"HORIZON_H1":h,"SUBSET":subset,"N":len(rr),
              "EXT_MEAN_BPS":avg(cv),"EXT_ACC":sum(x>0 for x in cv)/len(cv) if cv else None,
              "PRICE_MEAN_BPS":avg(pv),"PRICE_ACC":sum(x>0 for x in pv)/len(pv) if pv else None,
              "DELTA_EXT_MINUS_PRICE_BPS":avg([c-p for c,p in paired]) if paired else None
            })

    agg=[]
    for period in ("PRE2022","HOLDOUT2022+"):
      for h in H:
       for subset in ("ALL","DISAGREE"):
        for group,tgts in [("NON_USD",NON_USD),("USD_MAJOR",USD_MAJORS),("ALL_27",TARGETS)]:
            rr=[r for r in targets if r["PERIOD"]==period and r["HORIZON_H1"]==h and r["SUBSET"]==subset and r["TARGET"] in tgts]
            vv=[r for r in rr if r["EXT_MEAN_BPS"] is not None and r["DELTA_EXT_MINUS_PRICE_BPS"] is not None]
            agg.append({
              "PERIOD":period,"HORIZON_H1":h,"SUBSET":subset,"GROUP":group,"TARGETS":len(vv),
              "EXT_POSITIVE":sum(r["EXT_MEAN_BPS"]>0 for r in vv),
              "EXT_GT_PRICE":sum(r["DELTA_EXT_MINUS_PRICE_BPS"]>0 for r in vv),
              "MEAN_EXT_BPS":avg([r["EXT_MEAN_BPS"] for r in vv]),
              "MEAN_PRICE_BPS":avg([r["PRICE_MEAN_BPS"] for r in vv]),
              "MEAN_DELTA_BPS":avg([r["DELTA_EXT_MINUS_PRICE_BPS"] for r in vv]),
              "TOTAL_EVENTS":sum(r["N"] for r in vv)
            })

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";");w.writeheader();w.writerows(data)
    write("CS10_TARGETS.csv",targets);write("CS10_AGGREGATE.csv",agg)

    meta={"block":"CS10","status":"PASS","targets":TARGETS,"common_h1_bars":len(common),
          "contract":{"hypothesis":"external strength-gap slope leads target H1 price",
                      "discovery_pair_excluded":"EURUSD","target_pair_excluded_from_strength":True,
                      "same_timestamp_price_control":True,"lookback_h1":LB,"vol_window_h1":VOL,
                      "parameter_optimization":False,"trading_or_pnl":False}}
    (a.out/"CS10.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=["CURRENCY STRENGTH CS10 — H1 LEAD/LAG FALSIFICATION","STATUS: PASS",
           "DISCOVERY PAIR EXCLUDED: EURUSD","TARGETS: 27",
           f"COMMON_H1_BARS: {len(common)}","HOLDOUT: 2022-01-01 onward",
           "SAME-TIMESTAMP PRICE CONTROL: latest own H1 return",
           "OPTIMIZATION: NO","TRADING/PNL: NO",""]
    for h in H:
        lines.append("HORIZON "+str(h)+" H1 HOLDOUT:")
        for subset in ("ALL","DISAGREE"):
            r=next(x for x in agg if x["PERIOD"]=="HOLDOUT2022+" and x["HORIZON_H1"]==h and x["SUBSET"]==subset and x["GROUP"]=="ALL_27")
            lines.append(f" {subset}: POS={r['EXT_POSITIVE']}/{r['TARGETS']} GT_PRICE={r['EXT_GT_PRICE']}/{r['TARGETS']} EXT={r['MEAN_EXT_BPS']:+.4f} PRICE={r['MEAN_PRICE_BPS']:+.4f} DELTA={r['MEAN_DELTA_BPS']:+.4f} N={r['TOTAL_EVENTS']}")
        lines.append("")
    (a.out/"CS10.txt").write_text("\n".join(lines)+"\n",encoding="utf-8");print("\n".join(lines))
if __name__=="__main__":main()
