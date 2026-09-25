#!/usr/bin/env python3
"""
CS11 — external-disagreement as a filter for H1 price mean reversion.

CS10 found that when target-excluded external strength slope disagrees with the
target's latest H1 move, fading that H1 move is stronger. CS11 tests whether
this is a genuine cross-market FILTER rather than simply selecting larger
one-bar moves.

For each of 27 replication pairs:
- external state = sign(change in target-excluded base-minus-quote strength)
- price direction = sign(latest target H1 return)
- DISAGREE if external direction opposes latest price move
- mean-reversion direction = opposite latest price move
- compare MR expectancy in DISAGREE vs AGREE states
- control for target move magnitude using fixed quintile cutpoints estimated
  only on PRE2022 absolute H1 returns, then applied unchanged to HOLDOUT2022+.

No entry/exit trading model, no costs, no optimization.
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

def avg(x): return statistics.fmean(x) if x else None
def sgn(x): return 1 if x>0 else (-1 if x<0 else 0)

def quantiles(xs):
    z=sorted(xs)
    def q(p):
        k=(len(z)-1)*p;lo=int(math.floor(k));hi=int(math.ceil(k))
        return z[lo] if lo==hi else z[lo]+(z[hi]-z[lo])*(k-lo)
    return [q(.2),q(.4),q(.6),q(.8)]

def bin5(x,c):
    if x<c[0]:return 1
    if x<c[1]:return 2
    if x<c[2]:return 3
    if x<c[3]:return 4
    return 5

def load(root,p):
    h,b=read_xfbar(root/p/(p+"_H1.bin"))
    if h["period_seconds"]!=3600: raise SystemExit(p+" not H1")
    return {int(x[0]):float(x[4]) for x in b}

def rolling_z(series,common):
    n=len(common);one=[0.0]*n
    for i in range(1,n):one[i]=math.log(series[common[i]]/series[common[i-1]])
    ps=[0.0]*(n+1);ps2=[0.0]*(n+1)
    for i,x in enumerate(one): ps[i+1]=ps[i]+x;ps2[i+1]=ps2[i]+x*x
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
            v=z[p][i]
            totals[b][i]+=v;counts[b][i]+=1
            totals[q][i]-=v;counts[q][i]+=1

    rows=[]
    cuts={}
    for target in TARGETS:
        b=target[:3];q=target[3:];prev_gap=None
        tmp=[]
        for i in range(start,n-max(H)):
            tv=z[target][i]
            bs=(totals[b][i]-tv)/(counts[b][i]-1)
            qs=(totals[q][i]+tv)/(counts[q][i]-1)
            gap=bs-qs
            if prev_gap is not None:
                ext=sgn(gap-prev_gap)
                ret1=math.log(s[target][common[i]]/s[target][common[i-1]])
                ps=sgn(ret1)
                if ext and ps:
                    r={"TARGET":target,"TIME":common[i],"EXT":ext,"PRICE":ps,
                       "STATE":"DISAGREE" if ext!=ps else "AGREE",
                       "ABS_RET1":abs(ret1)}
                    for h in H:
                        fut=math.log(s[target][common[i+h]]/s[target][common[i]])*10000
                        r["MR"+str(h)]=(-ps)*fut
                    tmp.append(r)
            prev_gap=gap

        train_abs=[r["ABS_RET1"] for r in tmp if r["TIME"]<SPLIT]
        if len(train_abs)<100: raise SystemExit("insufficient PRE2022 "+target)
        c=quantiles(train_abs);cuts[target]=c
        for r in tmp:
            r["MAG_BIN"]=bin5(r["ABS_RET1"],c)
            r["PERIOD"]="HOLDOUT2022+" if r["TIME"]>=SPLIT else "PRE2022"
            rows.append(r)

    detail=[]
    for period in ("PRE2022","HOLDOUT2022+"):
      for h in H:
       mk="MR"+str(h)
       for target in TARGETS:
        rr=[r for r in rows if r["TARGET"]==target and r["PERIOD"]==period]
        d=[r[mk] for r in rr if r["STATE"]=="DISAGREE"]
        g=[r[mk] for r in rr if r["STATE"]=="AGREE"]
        bin_deltas=[];better=0
        for b in range(1,6):
            db=[r[mk] for r in rr if r["STATE"]=="DISAGREE" and r["MAG_BIN"]==b]
            gb=[r[mk] for r in rr if r["STATE"]=="AGREE" and r["MAG_BIN"]==b]
            if db and gb:
                delta=avg(db)-avg(gb);bin_deltas.append(delta)
                if delta>0:better+=1
        detail.append({
          "TARGET":target,"GROUP":"USD_MAJOR" if target in USD_MAJORS else "NON_USD",
          "PERIOD":period,"HORIZON_H1":h,
          "DISAGREE_N":len(d),"AGREE_N":len(g),
          "DISAGREE_MR_BPS":avg(d),"AGREE_MR_BPS":avg(g),
          "RAW_DELTA_BPS":avg(d)-avg(g) if d and g else None,
          "MATCHED_5BIN_DELTA_BPS":avg(bin_deltas),
          "BINS_DISAGREE_BETTER":better,
          "BINS_COMPARED":len(bin_deltas)
        })

    agg=[]
    for period in ("PRE2022","HOLDOUT2022+"):
      for h in H:
       for group,tgts in [("NON_USD",NON_USD),("USD_MAJOR",USD_MAJORS),("ALL_27",TARGETS)]:
        rr=[r for r in detail if r["PERIOD"]==period and r["HORIZON_H1"]==h and r["TARGET"] in tgts]
        agg.append({
          "PERIOD":period,"HORIZON_H1":h,"GROUP":group,"TARGETS":len(rr),
          "TARGETS_RAW_DELTA_POS":sum(r["RAW_DELTA_BPS"]>0 for r in rr),
          "TARGETS_MATCHED_DELTA_POS":sum(r["MATCHED_5BIN_DELTA_BPS"]>0 for r in rr),
          "MEAN_DISAGREE_MR_BPS":avg([r["DISAGREE_MR_BPS"] for r in rr]),
          "MEAN_AGREE_MR_BPS":avg([r["AGREE_MR_BPS"] for r in rr]),
          "MEAN_RAW_DELTA_BPS":avg([r["RAW_DELTA_BPS"] for r in rr]),
          "MEAN_MATCHED_5BIN_DELTA_BPS":avg([r["MATCHED_5BIN_DELTA_BPS"] for r in rr]),
          "TOTAL_DISAGREE":sum(r["DISAGREE_N"] for r in rr),
          "TOTAL_AGREE":sum(r["AGREE_N"] for r in rr)
        })

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";")
            w.writeheader();w.writerows(data)
    write("CS11_TARGETS.csv",detail);write("CS11_AGGREGATE.csv",agg)

    meta={"block":"CS11","status":"PASS","targets":TARGETS,
          "common_h1_bars":len(common),
          "common_first_utc":datetime.fromtimestamp(common[0],tz=timezone.utc).isoformat(),
          "common_last_utc":datetime.fromtimestamp(common[-1],tz=timezone.utc).isoformat(),
          "magnitude_quintile_cutpoints_pre2022":cuts,
          "contract":{"hypothesis":"external disagreement filters stronger target-price mean reversion",
                      "magnitude_control":"PRE2022 target-specific abs H1 return quintiles",
                      "cutpoints_frozen_before_holdout":True,
                      "target_pair_excluded_from_strength":True,
                      "parameter_optimization":False,"trading_or_pnl":False}}
    (a.out/"CS11.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=["CURRENCY STRENGTH CS11 — DISAGREEMENT FILTER AUDIT","STATUS: PASS",
           "DISCOVERY PAIR EXCLUDED: EURUSD","TARGETS: 27",
           f"COMMON H1: {meta['common_first_utc']} -> {meta['common_last_utc']} ({len(common)} bars)",
           "HOLDOUT: 2022-01-01 onward",
           "MAGNITUDE CONTROL: PRE2022 own-H1-return quintiles",
           "OPTIMIZATION: NO","TRADING/PNL: NO",""]
    for period in ("PRE2022","HOLDOUT2022+"):
        lines.append(period+" ALL_27:")
        for h in H:
            r=next(x for x in agg if x["PERIOD"]==period and x["HORIZON_H1"]==h and x["GROUP"]=="ALL_27")
            lines.append(f" H{h}: RAW+={r['TARGETS_RAW_DELTA_POS']}/{r['TARGETS']} MATCHED+={r['TARGETS_MATCHED_DELTA_POS']}/{r['TARGETS']} DIS_MR={r['MEAN_DISAGREE_MR_BPS']:+.4f} AGR_MR={r['MEAN_AGREE_MR_BPS']:+.4f} RAW_DELTA={r['MEAN_RAW_DELTA_BPS']:+.4f} MATCHED_DELTA={r['MEAN_MATCHED_5BIN_DELTA_BPS']:+.4f}")
        lines.append("")
    (a.out/"CS11.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
if __name__=="__main__":main()
