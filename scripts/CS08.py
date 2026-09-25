#!/usr/bin/env python3
"""
CS08 — same-timestamp incremental test for USD-major FULL_GAP_F5.

This removes a weakness of CS05/CS07: cross-market F5 and price-only F5 had
different event timestamps. Here every comparison is made on the EXACT SAME
cross-market event timestamps.

At each frozen FULL_GAP_F5 event:
- CROSS signal = reversal of prior extreme external strength gap
- PRICE_MR = reversal of target's own 24h return
- PRICE_MOM = continuation of target's own 24h return
Also test:
- DISAGREE_MR: CROSS and PRICE_MR point opposite ways
- OWN_NOT_EXTREME: target's own 24h return was below its own causal 90th pct
Thus any surviving effect is harder to explain as ordinary price mean reversion.

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
    for i,x in enumerate(one):
        ps[i+1]=ps[i]+x;ps2[i+1]=ps2[i]+x*x
    z=[None]*n
    for i in range(max(VOL,LB),n):
        lo=i-VOL+1;hi=i+1;m=VOL
        sm=ps[hi]-ps[lo];ss=ps2[hi]-ps2[lo]
        var=max(0.0,(ss-sm*sm/m)/(m-1));sd=math.sqrt(var)
        r=math.log(series[common[i]]/series[common[i-LB]])
        z[i]=r/(sd*math.sqrt(LB)) if sd>0 else 0.0
    return z

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
        b=target[:3];q=target[3:]
        gaps=[];owns=[]
        for i in range(start,n):
            tv=z[target][i]
            bs=(totals[b][i]-tv)/(counts[b][i]-1)
            qs=(totals[q][i]+tv)/(counts[q][i]-1)
            gaps.append(bs-qs)
            owns.append(math.log(s[target][common[i]]/s[target][common[i-LB]]))

        gh=[];oh=[];prevg=None
        events=[]
        for j,(g,o) in enumerate(zip(gaps,owns)):
            i=start+j
            gq=qtile([abs(x) for x in gh[max(0,len(gh)-ROLL):]],.90) if len(gh)>=50 else None
            oq=qtile([abs(x) for x in oh[max(0,len(oh)-ROLL):]],.90) if len(oh)>=50 else None
            if gq is not None and prevg is not None and abs(prevg)>=gq and abs(g)<abs(prevg):
                cs=-sgn(prevg)
                pmr=-sgn(o)
                pmom=sgn(o)
                events.append((i,cs,pmr,pmom,oq,abs(o)))
            gh.append(g);oh.append(o);prevg=g

        for i,cs,pmr,pmom,oq,ownabs in events:
            if i+max(H)>=n:continue
            row={"TARGET":target,"TIME":common[i],
                 "PERIOD":"HOLDOUT2022+" if common[i]>=SPLIT else "PRE2022",
                 "CROSS_SIGNAL":cs,"PRICE_MR_SIGNAL":pmr,"PRICE_MOM_SIGNAL":pmom,
                 "DISAGREE_MR":int(cs!=0 and pmr!=0 and cs!=pmr),
                 "OWN_NOT_EXTREME":int(oq is not None and ownabs<oq)}
            for h in H:
                fut=math.log(s[target][common[i+h]]/s[target][common[i]])*10000
                row["FUT"+str(h)+"_BPS"]=fut
            detail.append(row)

    summary=[]
    subsets=[
      ("ALL",lambda r:True),
      ("DISAGREE_MR",lambda r:r["DISAGREE_MR"]==1),
      ("OWN_NOT_EXTREME",lambda r:r["OWN_NOT_EXTREME"]==1),
      ("DISAGREE_AND_NOT_EXTREME",lambda r:r["DISAGREE_MR"]==1 and r["OWN_NOT_EXTREME"]==1)
    ]
    for h in H:
        fk="FUT"+str(h)+"_BPS"
        for period in ("PRE2022","HOLDOUT2022+"):
            for subname,pred in subsets:
                for target in TARGETS:
                    rr=[r for r in detail if r["TARGET"]==target and r["PERIOD"]==period and pred(r)]
                    cv=[r["CROSS_SIGNAL"]*r[fk] for r in rr if r["CROSS_SIGNAL"]]
                    mv=[r["PRICE_MR_SIGNAL"]*r[fk] for r in rr if r["PRICE_MR_SIGNAL"]]
                    mom=[r["PRICE_MOM_SIGNAL"]*r[fk] for r in rr if r["PRICE_MOM_SIGNAL"]]
                    summary.append({
                      "TARGET":target,"HORIZON_H4":h,"PERIOD":period,"SUBSET":subname,"N":len(rr),
                      "CROSS_MEAN_BPS":avg(cv),"CROSS_ACC":sum(x>0 for x in cv)/len(cv) if cv else None,
                      "PRICE_MR_MEAN_BPS":avg(mv),"PRICE_MR_ACC":sum(x>0 for x in mv)/len(mv) if mv else None,
                      "PRICE_MOM_MEAN_BPS":avg(mom),"PRICE_MOM_ACC":sum(x>0 for x in mom)/len(mom) if mom else None,
                      "DELTA_CROSS_MINUS_MR_BPS":avg([c-m for c,m in zip(cv,mv)]) if len(cv)==len(mv) and cv else None
                    })

    agg=[]
    for h in H:
        for subname,_ in subsets:
            rr=[r for r in summary if r["HORIZON_H4"]==h and r["PERIOD"]=="HOLDOUT2022+" and r["SUBSET"]==subname]
            valid=[r for r in rr if r["CROSS_MEAN_BPS"] is not None and r["PRICE_MR_MEAN_BPS"] is not None]
            agg.append({
              "HORIZON_H4":h,"SUBSET":subname,"TARGETS":len(valid),
              "CROSS_POSITIVE":sum(r["CROSS_MEAN_BPS"]>0 for r in valid),
              "CROSS_GT_PRICE_MR":sum(r["DELTA_CROSS_MINUS_MR_BPS"]>0 for r in valid),
              "MEAN_CROSS_BPS":avg([r["CROSS_MEAN_BPS"] for r in valid]),
              "MEAN_PRICE_MR_BPS":avg([r["PRICE_MR_MEAN_BPS"] for r in valid]),
              "MEAN_DELTA_BPS":avg([r["DELTA_CROSS_MINUS_MR_BPS"] for r in valid]),
              "TOTAL_EVENTS":sum(r["N"] for r in valid)
            })

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";");w.writeheader();w.writerows(data)
    write("CS08_SUMMARY.csv",summary);write("CS08_AGGREGATE.csv",agg)

    meta={"block":"CS08","status":"PASS","targets":TARGETS,"aggregate_holdout":agg,
          "contract":{"same_cross_event_timestamps":True,"price_control":"opposite own 24h return",
                      "own_not_extreme_uses_causal_q90":True,"parameters_frozen":True,
                      "parameter_optimization":False,"trading_or_pnl":False}}
    (a.out/"CS08.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=["CURRENCY STRENGTH CS08 — SAME-TIMESTAMP INCREMENTAL TEST","STATUS: PASS",
           "TARGETS: "+", ".join(TARGETS),"HOLDOUT: 2022-01-01 onward",
           "PRICE CONTROL: mean reversion of own 24h return on SAME event timestamps",
           "OPTIMIZATION: NO","TRADING/PNL: NO",""]
    for h in H:
        lines.append("H"+str(h)+":")
        for sub in ["ALL","DISAGREE_MR","OWN_NOT_EXTREME","DISAGREE_AND_NOT_EXTREME"]:
            r=next(x for x in agg if x["HORIZON_H4"]==h and x["SUBSET"]==sub)
            lines.append(f" {sub}: POS={r['CROSS_POSITIVE']}/{r['TARGETS']} GT_MR={r['CROSS_GT_PRICE_MR']}/{r['TARGETS']} CROSS={r['MEAN_CROSS_BPS']:+.4f} MR={r['MEAN_PRICE_MR_BPS']:+.4f} DELTA={r['MEAN_DELTA_BPS']:+.4f} N={r['TOTAL_EVENTS']}")
        lines.append("")
    (a.out/"CS08.txt").write_text("\n".join(lines)+"\n",encoding="utf-8");print("\n".join(lines))
if __name__=="__main__":main()
