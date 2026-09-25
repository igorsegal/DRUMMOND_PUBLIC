#!/usr/bin/env python3
"""
CS13 — DISAGREEMENT TRADING EMULATOR.

Frozen signal inherited from CS12:
  external 8-currency strength-gap slope opposes the target pair's latest H1 move.

Trading translation:
- 27 replication pairs (EURUSD discovery pair remains excluded);
- signal is known only after the H1 bar closes;
- trade direction = external strength-gap slope (equivalently opposite latest
  target H1 move on a DISAGREE event);
- enter at first M5 OPEN at/after H1 close;
- fixed holding periods: 1h, 4h, 12h, 24h;
- exit at first M5 OPEN at/after entry_time + holding period;
- one open position per target/horizon; overlapping signals are skipped;
- MT4 bid-bar convention: long entry pays entry spread, short exit pays exit
  spread, using recorded M5 spread field and XFBAR point size;
- extra round-trip cost stress: 0, 1, 2, 5, 10 points beyond recorded spread.

This is an execution/profitability emulation, not fresh out-of-sample validation:
the disagreement family was already inspected through CS12 on this history.
"""
import argparse,bisect,csv,json,math,statistics
from collections import defaultdict
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
LB=24
VOL=120
HOLDS=[1,4,12,24]
EXTRA_COST_POINTS=[0,1,2,5,10]

def avg(x): return statistics.fmean(x) if x else None
def med(x): return statistics.median(x) if x else None
def sgn(x): return 1 if x>0 else (-1 if x<0 else 0)

def load_h1(root,p):
    h,b=read_xfbar(root/p/(p+"_H1.bin"))
    if h["period_seconds"]!=3600: raise SystemExit(p+" H1 contract")
    return h,{int(x[0]):float(x[4]) for x in b}

def rolling_z(series,common):
    n=len(common);one=[0.0]*n
    for i in range(1,n):
        one[i]=math.log(series[common[i]]/series[common[i-1]])
    ps=[0.0]*(n+1);ps2=[0.0]*(n+1)
    for i,x in enumerate(one):
        ps[i+1]=ps[i]+x;ps2[i+1]=ps2[i]+x*x
    out=[None]*n
    for i in range(max(VOL,LB),n):
        lo=i-VOL+1;hi=i+1;m=VOL
        sm=ps[hi]-ps[lo];ss=ps2[hi]-ps2[lo]
        var=max(0.0,(ss-sm*sm/m)/(m-1));sd=math.sqrt(var)
        r=math.log(series[common[i]]/series[common[i-LB]])
        out[i]=r/(sd*math.sqrt(LB)) if sd>0 else 0.0
    return out

def metrics(vals):
    if not vals:
        return {"N":0,"MEAN_BPS":None,"MEDIAN_BPS":None,"WIN_RATE":None,
                "PF":None,"SUM_BPS":0.0,"MAX_DD_BPS":None}
    wins=sum(v for v in vals if v>0)
    losses=-sum(v for v in vals if v<0)
    eq=0.0;peak=0.0;mdd=0.0
    for v in vals:
        eq+=v;peak=max(peak,eq);mdd=max(mdd,peak-eq)
    return {
        "N":len(vals),
        "MEAN_BPS":avg(vals),
        "MEDIAN_BPS":med(vals),
        "WIN_RATE":sum(v>0 for v in vals)/len(vals),
        "PF":wins/losses if losses>0 else None,
        "SUM_BPS":sum(vals),
        "MAX_DD_BPS":mdd
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    hmeta={};hs={}
    for p in PAIRS:
        hmeta[p],hs[p]=load_h1(a.root,p)
    common=sorted(set.intersection(*(set(hs[p]) for p in PAIRS)))
    n=len(common);start=max(VOL,LB)
    z={p:rolling_z(hs[p],common) for p in PAIRS}

    totals={c:[0.0]*n for c in CURS};counts={c:[0]*n for c in CURS}
    for p in PAIRS:
        b=p[:3];q=p[3:]
        zp=z[p]
        for i in range(start,n):
            v=zp[i]
            totals[b][i]+=v;counts[b][i]+=1
            totals[q][i]-=v;counts[q][i]+=1

    all_trades=[]
    target_stats=[]
    for ti,target in enumerate(TARGETS,1):
        b=target[:3];q=target[3:]
        signals=[]
        prev_gap=None
        for i in range(start,n):
            tv=z[target][i]
            bs=(totals[b][i]-tv)/(counts[b][i]-1)
            qs=(totals[q][i]+tv)/(counts[q][i]-1)
            gap=bs-qs
            if prev_gap is not None and i>=1:
                ext=sgn(gap-prev_gap)
                ret1=math.log(hs[target][common[i]]/hs[target][common[i-1]])
                ps=sgn(ret1)
                if ext and ps and ext!=ps:
                    # H1 timestamp is bar open; information becomes available at close.
                    signals.append((common[i]+3600,ext,common[i]))
            prev_gap=gap

        mp=a.root/target/(target+"_M5.bin")
        if not mp.exists(): raise SystemExit("missing M5 "+str(mp))
        mh,mb=read_xfbar(mp)
        if mh["period_seconds"]!=300: raise SystemExit(target+" M5 contract")
        mt=[int(x[0]) for x in mb]
        point=float(mh["point"])

        for hold in HOLDS:
            next_free=-1
            sig_count=0;overlap=0;no_entry=0;no_exit=0
            created=[]
            for ready,side,h1_time in signals:
                sig_count+=1
                if ready<next_free:
                    overlap+=1;continue
                ei=bisect.bisect_left(mt,ready)
                if ei>=len(mb):
                    no_entry+=1;continue
                et=mt[ei]
                xi=bisect.bisect_left(mt,et+hold*3600)
                if xi>=len(mb):
                    no_exit+=1;continue

                eb=mb[ei];xb=mb[xi]
                bid_in=float(eb[1]);bid_out=float(xb[1])
                sp_in=max(0,int(eb[6]));sp_out=max(0,int(xb[6]))
                ask_in=bid_in+sp_in*point
                ask_out=bid_out+sp_out*point

                if side>0:
                    entry=ask_in;exitp=bid_out
                    gross=(bid_out-bid_in)/bid_in*10000.0
                    spread_net=(exitp-entry)/entry*10000.0
                else:
                    entry=bid_in;exitp=ask_out
                    gross=(bid_in-bid_out)/bid_in*10000.0
                    spread_net=(entry-exitp)/entry*10000.0

                tr={
                    "TARGET":target,"HOLD_H":hold,"SIGNAL_H1_TIME":h1_time,
                    "READY_TIME":ready,"ENTRY_TIME":et,"EXIT_TIME":mt[xi],
                    "YEAR":datetime.fromtimestamp(et,tz=timezone.utc).year,
                    "SIDE":"LONG" if side>0 else "SHORT",
                    "POINT":point,"ENTRY_BID":bid_in,"EXIT_BID":bid_out,
                    "ENTRY_SPREAD_POINTS":sp_in,"EXIT_SPREAD_POINTS":sp_out,
                    "GROSS_BPS":gross,"SPREAD_NET_BPS":spread_net
                }
                for cp in EXTRA_COST_POINTS:
                    extra_bps=cp*point/entry*10000.0
                    tr["NET_C"+str(cp)+"_BPS"]=spread_net-extra_bps
                created.append(tr);all_trades.append(tr)
                next_free=mt[xi]

            target_stats.append({
                "TARGET":target,"HOLD_H":hold,"SIGNALS":sig_count,
                "TRADES":len(created),"SKIP_OVERLAP":overlap,
                "SKIP_NO_ENTRY":no_entry,"SKIP_NO_EXIT":no_exit,
                "MEAN_ENTRY_SPREAD_POINTS":avg([r["ENTRY_SPREAD_POINTS"] for r in created]),
                "MEAN_EXIT_SPREAD_POINTS":avg([r["EXIT_SPREAD_POINTS"] for r in created]),
                "ZERO_ENTRY_SPREAD_RATE":(
                    sum(r["ENTRY_SPREAD_POINTS"]==0 for r in created)/len(created) if created else None)
            })
        print(f"[{ti}/{len(TARGETS)}] {target} signals={len(signals)} M5={len(mb)} PASS")

    # Preserve deterministic chronological order for pooled equity summaries.
    all_trades.sort(key=lambda r:(r["ENTRY_TIME"],r["TARGET"],r["HOLD_H"]))

    fields=list(all_trades[0].keys())
    with (a.out/"CS13_TRADES.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";");w.writeheader();w.writerows(all_trades)
    with (a.out/"CS13_EXECUTION.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(target_stats[0].keys()),delimiter=";")
        w.writeheader();w.writerows(target_stats)

    summary=[];per_target=[];yearly=[]
    for hold in HOLDS:
        rr=[r for r in all_trades if r["HOLD_H"]==hold]
        for cp in EXTRA_COST_POINTS:
            key="NET_C"+str(cp)+"_BPS"
            m=metrics([r[key] for r in rr])
            summary.append({"HOLD_H":hold,"COST_SCENARIO_POINTS":cp,**m,
                            "MEAN_RECORDED_ENTRY_SPREAD_POINTS":avg([r["ENTRY_SPREAD_POINTS"] for r in rr]),
                            "ZERO_ENTRY_SPREAD_RATE":sum(r["ENTRY_SPREAD_POINTS"]==0 for r in rr)/len(rr) if rr else None})
        for target in TARGETS:
            tt=[r for r in rr if r["TARGET"]==target]
            for cp in (0,2,5):
                m=metrics([r["NET_C"+str(cp)+"_BPS"] for r in tt])
                per_target.append({"TARGET":target,"HOLD_H":hold,"COST_SCENARIO_POINTS":cp,**m})
        for y in sorted({r["YEAR"] for r in rr}):
            yy=[r for r in rr if r["YEAR"]==y]
            for cp in (0,2,5):
                m=metrics([r["NET_C"+str(cp)+"_BPS"] for r in yy])
                yearly.append({"YEAR":y,"HOLD_H":hold,"COST_SCENARIO_POINTS":cp,**m})

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";")
            w.writeheader();w.writerows(data)
    write("CS13_SUMMARY.csv",summary)
    write("CS13_TARGETS.csv",per_target)
    write("CS13_YEARLY.csv",yearly)

    best0=max([r for r in summary if r["COST_SCENARIO_POINTS"]==0],key=lambda r:r["MEAN_BPS"])
    meta={
        "block":"CS13","status":"PASS",
        "signal":"CS12 external-strength-vs-own-H1 DISAGREE",
        "targets":TARGETS,"discovery_pair_excluded":DISCOVERY,
        "holding_hours":HOLDS,"extra_cost_points":EXTRA_COST_POINTS,
        "total_trade_rows":len(all_trades),
        "best_recorded_spread_only":best0,
        "contract":{
            "entry":"first M5 open at/after signal H1 close",
            "exit":"first M5 open at/after fixed holding period",
            "one_position_per_target_horizon":True,
            "recorded_m5_spread_applied":True,
            "extra_cost_is_round_trip_point_equivalent":True,
            "parameter_optimization":False,
            "fresh_out_of_sample_validation":False,
            "reason_not_fresh":"signal family and history already inspected through CS12"
        }
    }
    (a.out/"CS13.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
        "CURRENCY STRENGTH CS13 — DISAGREEMENT TRADING EMULATOR",
        "STATUS: PASS",
        "TARGETS: 27 (EURUSD discovery pair excluded)",
        "ENTRY: first M5 open after closed H1 signal",
        "EXIT: fixed 1h / 4h / 12h / 24h",
        "RECORDED M5 SPREAD: APPLIED",
        "OVERLAPPING SAME-TARGET POSITIONS: BLOCKED",
        "FRESH OUT-OF-SAMPLE: NO (history already inspected through CS12)",
        ""
    ]
    for hold in HOLDS:
        lines.append(f"HOLD {hold}h:")
        for cp in EXTRA_COST_POINTS:
            r=next(x for x in summary if x["HOLD_H"]==hold and x["COST_SCENARIO_POINTS"]==cp)
            pf="NA" if r["PF"] is None else f"{r['PF']:.4f}"
            lines.append(
              f" C{cp}: N={r['N']} MEAN={r['MEAN_BPS']:+.4f}bps MED={r['MEDIAN_BPS']:+.4f} "
              f"WIN={r['WIN_RATE']:.4f} PF={pf} SUM={r['SUM_BPS']:+.1f} MDD={r['MAX_DD_BPS']:.1f}"
            )
        lines.append("")
    (a.out/"CS13.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
