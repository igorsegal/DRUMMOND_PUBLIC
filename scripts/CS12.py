#!/usr/bin/env python3
"""
CS12 — stricter matched audit of the CS11 disagreement filter.

Controls target-price conditions WITHOUT using future outcomes:
- abs latest H1 return quintile (cutpoints estimated PRE2022 only)
- latest H1 direction (up/down)
- fixed UTC session bucket: 00-07, 08-15, 16-23

Within each stratum, compare future mean-reversion return for:
  DISAGREE: external strength-gap slope opposes latest target H1 move
  AGREE:    external strength-gap slope agrees with latest target H1 move

Matched delta is weighted by min(DISAGREE_N, AGREE_N) per stratum, which
prevents sparse strata from dominating.

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
            v=z[p][i]
            totals[b][i]+=v;counts[b][i]+=1
            totals[q][i]-=v;counts[q][i]+=1

    allrows=[];cuts={}
    hour_counts={h:0 for h in range(24)}
    for target in TARGETS:
        b=target[:3];q=target[3:];prev_gap=None;tmp=[]
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
                    dt=datetime.fromtimestamp(common[i],tz=timezone.utc)
                    hour_counts[dt.hour]+=1
                    r={"TARGET":target,"TIME":common[i],"EXT":ext,"PRICE":ps,
                       "STATE":"DISAGREE" if ext!=ps else "AGREE",
                       "ABS_RET1":abs(ret1),"DIR":ps,"SESSION":dt.hour//8}
                    for h in H:
                        fut=math.log(s[target][common[i+h]]/s[target][common[i]])*10000
                        r["MR"+str(h)]=(-ps)*fut
                    tmp.append(r)
            prev_gap=gap

        pre=[r["ABS_RET1"] for r in tmp if r["TIME"]<SPLIT]
        if len(pre)<100:raise SystemExit("insufficient PRE2022 "+target)
        c=quantiles(pre);cuts[target]=c
        for r in tmp:
            r["MAG_BIN"]=bin5(r["ABS_RET1"],c)
            r["PERIOD"]="HOLDOUT2022+" if r["TIME"]>=SPLIT else "PRE2022"
            allrows.append(r)

    detail=[]
    for period in ("PRE2022","HOLDOUT2022+"):
      for h in H:
       mk="MR"+str(h)
       for target in TARGETS:
        rr=[r for r in allrows if r["TARGET"]==target and r["PERIOD"]==period]
        d=[r[mk] for r in rr if r["STATE"]=="DISAGREE"]
        g=[r[mk] for r in rr if r["STATE"]=="AGREE"]
        num=0.0;den=0;strata=0;better=0
        md_num=0.0;ma_num=0.0
        for mb in range(1,6):
          for direc in (-1,1):
            for sess in (0,1,2):
                dd=[r[mk] for r in rr if r["STATE"]=="DISAGREE" and r["MAG_BIN"]==mb and r["DIR"]==direc and r["SESSION"]==sess]
                gg=[r[mk] for r in rr if r["STATE"]=="AGREE" and r["MAG_BIN"]==mb and r["DIR"]==direc and r["SESSION"]==sess]
                if not dd or not gg:continue
                w=min(len(dd),len(gg))
                dm=avg(dd);gm=avg(gg);delta=dm-gm
                num+=w*delta;md_num+=w*dm;ma_num+=w*gm;den+=w;strata+=1
                if delta>0:better+=1
        detail.append({
          "TARGET":target,"GROUP":"USD_MAJOR" if target in USD_MAJORS else "NON_USD",
          "PERIOD":period,"HORIZON_H1":h,
          "DISAGREE_N":len(d),"AGREE_N":len(g),
          "RAW_DISAGREE_MR_BPS":avg(d),"RAW_AGREE_MR_BPS":avg(g),
          "RAW_DELTA_BPS":avg(d)-avg(g) if d and g else None,
          "MATCHED_DISAGREE_MR_BPS":md_num/den if den else None,
          "MATCHED_AGREE_MR_BPS":ma_num/den if den else None,
          "MATCHED_DELTA_BPS":num/den if den else None,
          "MATCHED_PAIRS_PER_SIDE":den,
          "STRATA_COMPARED":strata,"STRATA_DISAGREE_BETTER":better
        })

    agg=[]
    for period in ("PRE2022","HOLDOUT2022+"):
      for h in H:
       for group,tgts in [("NON_USD",NON_USD),("USD_MAJOR",USD_MAJORS),("ALL_27",TARGETS)]:
        rr=[r for r in detail if r["PERIOD"]==period and r["HORIZON_H1"]==h and r["TARGET"] in tgts]
        agg.append({
          "PERIOD":period,"HORIZON_H1":h,"GROUP":group,"TARGETS":len(rr),
          "RAW_DELTA_POS":sum(r["RAW_DELTA_BPS"]>0 for r in rr),
          "MATCHED_DELTA_POS":sum(r["MATCHED_DELTA_BPS"]>0 for r in rr),
          "MEAN_RAW_DELTA_BPS":avg([r["RAW_DELTA_BPS"] for r in rr]),
          "MEAN_MATCHED_DELTA_BPS":avg([r["MATCHED_DELTA_BPS"] for r in rr]),
          "MEAN_MATCHED_DISAGREE_MR_BPS":avg([r["MATCHED_DISAGREE_MR_BPS"] for r in rr]),
          "MEAN_MATCHED_AGREE_MR_BPS":avg([r["MATCHED_AGREE_MR_BPS"] for r in rr]),
          "TOTAL_MATCHED_PAIRS_PER_SIDE":sum(r["MATCHED_PAIRS_PER_SIDE"] for r in rr)
        })

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";")
            w.writeheader();w.writerows(data)
    write("CS12_TARGETS.csv",detail);write("CS12_AGGREGATE.csv",agg)

    meta={"block":"CS12","status":"PASS","targets":TARGETS,
          "common_first_utc":datetime.fromtimestamp(common[0],tz=timezone.utc).isoformat(),
          "common_last_utc":datetime.fromtimestamp(common[-1],tz=timezone.utc).isoformat(),
          "hour_event_counts":hour_counts,
          "contract":{"filter":"external-vs-own-H1 disagreement",
                      "matched_strata":["PRE2022 abs-H1-return quintile","own-H1 direction","UTC 8-hour session"],
                      "matched_weight":"min(disagree_n,agree_n)",
                      "cutpoints_frozen_before_holdout":True,
                      "target_pair_excluded_from_strength":True,
                      "parameter_optimization":False,"trading_or_pnl":False}}
    (a.out/"CS12.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=["CURRENCY STRENGTH CS12 — STRICT MATCHED DISAGREEMENT AUDIT","STATUS: PASS",
           "TARGETS: 27","HOLDOUT: 2022-01-01 onward",
           "MATCH: magnitude quintile + price direction + UTC session",
           "WEIGHT: min(disagree, agree) per stratum",
           "OPTIMIZATION: NO","TRADING/PNL: NO",""]
    for period in ("PRE2022","HOLDOUT2022+"):
        lines.append(period+" ALL_27:")
        for h in H:
            r=next(x for x in agg if x["PERIOD"]==period and x["HORIZON_H1"]==h and x["GROUP"]=="ALL_27")
            lines.append(f" H{h}: RAW+={r['RAW_DELTA_POS']}/{r['TARGETS']} MATCHED+={r['MATCHED_DELTA_POS']}/{r['TARGETS']} MATCH_DIS={r['MEAN_MATCHED_DISAGREE_MR_BPS']:+.4f} MATCH_AGR={r['MEAN_MATCHED_AGREE_MR_BPS']:+.4f} DELTA={r['MEAN_MATCHED_DELTA_BPS']:+.4f} MATCHED_N_SIDE={r['TOTAL_MATCHED_PAIRS_PER_SIDE']}")
        lines.append("")
    (a.out/"CS12.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
if __name__=="__main__":main()
