#!/usr/bin/env python3
import argparse,csv,json,math,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from drummond_replay01 import read_xfbar

TARGET="EURUSD"
ALLIES=["GBPUSD","AUDUSD","NZDUSD"]
OPP=["USDCHF","USDJPY","USDCAD"]
PAIRS=[TARGET]+ALLIES+OPP
LB=6
H=[1,3,6,18]

def sgn(x): return 1 if x>0 else (-1 if x<0 else 0)
def avg(x): return statistics.fmean(x) if x else None
def med(x): return statistics.median(x) if x else None
def acc(x): return sum(v>0 for v in x)/len(x) if x else None

def load(p):
    h,b=read_xfbar(p)
    if h["period_seconds"]!=14400: raise SystemExit("H4 required")
    return {int(x[0]):float(x[4]) for x in b}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args(); a.out.mkdir(parents=True,exist_ok=True)

    s={}
    for p in PAIRS:
        q=a.root/p/(p+"_H4.bin")
        if not q.exists(): raise SystemExit("missing "+str(q))
        s[p]=load(q)
    t=sorted(set.intersection(*(set(s[p]) for p in PAIRS)))
    rows=[]
    for i in range(LB,len(t)-max(H)):
        now=t[i]; old=t[i-LB]
        own=math.log(s[TARGET][now]/s[TARGET][old]); od=sgn(own)
        votes=[]
        for p in ALLIES: votes.append(sgn(math.log(s[p][now]/s[p][old])))
        for p in OPP: votes.append(-sgn(math.log(s[p][now]/s[p][old])))
        score=sum(votes); bd=sgn(score)
        r={"time":now,"year":datetime.fromtimestamp(now,tz=timezone.utc).year,
           "own_dir":od,"basket_dir":bd,"score":score,"abs_score":abs(score)}
        for h in H:
            r["f"+str(h)]=math.log(s[TARGET][t[i+h]]/s[TARGET][now])
        rows.append(r)

    summary=[]; consensus=[]; incr=[]; yearly=[]; scoretab=[]
    for h in H:
        fk="f"+str(h)
        for name,key in [("CROSS_MARKET","basket_dir"),("OWN_PRICE","own_dir")]:
            rr=[r for r in rows if r[key]!=0]
            v=[r[key]*r[fk]*10000 for r in rr]
            summary.append({"HORIZON_H4":h,"MODEL":name,"N":len(rr),
                "MEAN_SIGNED_BPS":avg(v),"MEDIAN_SIGNED_BPS":med(v),
                "DIRECTIONAL_ACCURACY":acc(v),
                "MEAN_ABS_FUTURE_BPS":avg([abs(r[fk])*10000 for r in rr])})
        for name,pred in [
            ("UNANIMOUS_6",lambda r:r["abs_score"]==6),
            ("STRONG_4_6",lambda r:r["abs_score"]>=4),
            ("WEAK_0_2",lambda r:r["abs_score"]<=2),
            ("AGREE_WITH_OWN",lambda r:r["basket_dir"]!=0 and r["basket_dir"]==r["own_dir"]),
            ("CONFLICT_WITH_OWN",lambda r:r["basket_dir"]!=0 and r["own_dir"]!=0 and r["basket_dir"]!=r["own_dir"])]:
            rr=[r for r in rows if pred(r)]
            bv=[r["basket_dir"]*r[fk]*10000 for r in rr if r["basket_dir"]]
            ov=[r["own_dir"]*r[fk]*10000 for r in rr if r["own_dir"]]
            consensus.append({"HORIZON_H4":h,"BUCKET":name,"N":len(rr),
                "MEAN_ABS_FUTURE_BPS":avg([abs(r[fk])*10000 for r in rr]),
                "MEAN_BASKET_SIGNED_BPS":avg(bv),"BASKET_ACCURACY":acc(bv),
                "MEAN_OWN_SIGNED_BPS":avg(ov),"OWN_ACCURACY":acc(ov)})
        for od in (-1,1):
            for rel,bd in [("BASKET_AGREES",od),("BASKET_CONFLICTS",-od)]:
                rr=[r for r in rows if r["own_dir"]==od and r["basket_dir"]==bd]
                v=[od*r[fk]*10000 for r in rr]
                incr.append({"HORIZON_H4":h,"OWN_DIRECTION":"UP" if od>0 else "DOWN",
                    "BASKET_RELATION":rel,"N":len(rr),"MEAN_OWN_DIRECTION_FUTURE_BPS":avg(v),
                    "DIRECTIONAL_ACCURACY":acc(v),"MEAN_ABS_FUTURE_BPS":avg([abs(r[fk])*10000 for r in rr])})
        for sc in (-6,-4,-2,0,2,4,6):
            rr=[r for r in rows if r["score"]==sc]; v=[r[fk]*10000 for r in rr]
            scoretab.append({"HORIZON_H4":h,"BASKET_SCORE":sc,"N":len(rr),
                "MEAN_EURUSD_FUTURE_BPS":avg(v),"MEDIAN_EURUSD_FUTURE_BPS":med(v),
                "MEAN_ABS_FUTURE_BPS":avg([abs(x) for x in v])})

    for y in sorted({r["year"] for r in rows}):
        rr=[r for r in rows if r["year"]==y and r["abs_score"]>=4 and r["basket_dir"]]
        v=[r["basket_dir"]*r["f6"]*10000 for r in rr]
        yearly.append({"YEAR":y,"N":len(rr),"MEAN_SIGNED_BPS":avg(v),
            "DIRECTIONAL_ACCURACY":acc(v),"MEAN_ABS_FUTURE_BPS":avg([abs(r["f6"])*10000 for r in rr])})

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]),delimiter=";"); w.writeheader(); w.writerows(data)
    write("UT03_SUMMARY.csv",summary); write("UT03_CONSENSUS.csv",consensus)
    write("UT03_INCREMENTAL.csv",incr); write("UT03_YEARLY.csv",yearly); write("UT03_SCORE_TABLE.csv",scoretab)

    out={"block":"UT03","status":"PASS","target":"EURUSD","timeframe":"H4",
         "allies":ALLIES,"opponents":OPP,"common_bars":len(t),"observations":len(rows),
         "lookback_h4":LB,"horizons_h4":H,
         "contract":{"trading_or_pnl":False,"parameter_optimization":False,
           "target_excluded_from_basket":True,
           "basket":"sum sign of 24h peer returns, opponent signs inverted",
           "own_price_baseline":"sign of EURUSD 24h return"}}
    (a.out/"UT03.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=["SMART TRADING UT03 — CROSS-MARKET USD CONSENSUS","STATUS: PASS",
           "TARGET: EURUSD H4","PEERS: "+", ".join(ALLIES+OPP),
           f"COMMON_BARS: {len(t)} OBSERVATIONS: {len(rows)}","TRADING/PNL: NO","OPTIMIZATION: NO",""]
    for h in H:
        c=next(r for r in summary if r["HORIZON_H4"]==h and r["MODEL"]=="CROSS_MARKET")
        o=next(r for r in summary if r["HORIZON_H4"]==h and r["MODEL"]=="OWN_PRICE")
        st=next(r for r in consensus if r["HORIZON_H4"]==h and r["BUCKET"]=="STRONG_4_6")
        wk=next(r for r in consensus if r["HORIZON_H4"]==h and r["BUCKET"]=="WEAK_0_2")
        lines += [f"HORIZON {h} H4:",
          f" CROSS: N={c['N']} MEAN_SIGNED_BPS={c['MEAN_SIGNED_BPS']:+.4f} ACC={c['DIRECTIONAL_ACCURACY']:.6f}",
          f" OWN:   N={o['N']} MEAN_SIGNED_BPS={o['MEAN_SIGNED_BPS']:+.4f} ACC={o['DIRECTIONAL_ACCURACY']:.6f}",
          f" CROSS-OWN DELTA={c['MEAN_SIGNED_BPS']-o['MEAN_SIGNED_BPS']:+.4f} bps",
          f" STRONG: N={st['N']} ABS={st['MEAN_ABS_FUTURE_BPS']:.4f} SIGNED={st['MEAN_BASKET_SIGNED_BPS']:+.4f}",
          f" WEAK:   N={wk['N']} ABS={wk['MEAN_ABS_FUTURE_BPS']:.4f} SIGNED={wk['MEAN_BASKET_SIGNED_BPS']:+.4f}",""]
    (a.out/"UT03.txt").write_text("\n".join(lines)+"\n",encoding="utf-8"); print("\n".join(lines))
if __name__=="__main__": main()
