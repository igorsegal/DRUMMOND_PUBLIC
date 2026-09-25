#!/usr/bin/env python3
"""
TM01 — TAKBIR M1 causal reconstruction + source-faithful execution.

Input: one genuine XFBAR001 M1 file.

Frozen geometry:
- 11-bar Takbir, confirmed only after 5 bars to the right have CLOSED.
- Kimma/Yamma alternate; potential level is confirmed by opposite Takbir.
- Azan = close break of same-side structural line.
- Iqamat = close break of latest opposite confirmed level.
- Entry candidate only AFTER Iqamat bar closes.
- Entry trigger = 1 point beyond Iqamat candle extreme.
- Structural stop = latest opposite confirmed Yamma/Kimma known at Iqamat.
- Exit = stop, opposite Iqamat, or data end.
- One position per symbol. No TP. No parameter fitting.

Two returns are reported:
GROSS_R  : chart-price execution, no costs.
SPREAD_R : historical MT4 M1 spread applied to fills, using the same gross
           structural risk denominator so spread drag is visible.

With M1-only data, any bar touching both entry and stop is resolved
conservatively as entry then stop.
"""
import argparse,csv,json,math,statistics
from collections import Counter
from pathlib import Path

from drummond_replay01 import read_xfbar
from T01 import reconstruct

FIELDS=[
 "SYMBOL","SIDE","SIGNAL_TIME","ENTRY_TIME","EXIT_TIME",
 "ENTRY_TRIGGER","ENTRY_GROSS","ENTRY_SPREAD","STOP","EXIT_GROSS","EXIT_SPREAD",
 "GROSS_R","SPREAD_R","OUTCOME","WAIT_M1","HOLD_M1",
 "ENTRY_SPREAD_POINTS","EXIT_SPREAD_POINTS"
]

def prepare_signals(bars,point):
    r=reconstruct(bars)
    if r["errors"]:
        raise RuntimeError(",".join(r["errors"]))
    levels=r["levels"]
    out=[]
    for e in r["events"]:
        if not e["type"].startswith("IQAMAT"):
            continue
        i=int(e["idx"]); d=int(e["dir"])
        known=[lv for lv in levels if lv["known_idx"]<=i]
        opp_kind="YAMMA" if d>0 else "KIMMA"
        opp=[lv for lv in known if lv["kind"]==opp_kind]
        if not opp:
            continue
        stop=float(opp[-1]["price"])
        trigger=float(bars[i][2])+point if d>0 else float(bars[i][3])-point
        risk=trigger-stop if d>0 else stop-trigger
        if not math.isfinite(risk) or risk<=point*0.5:
            continue
        out.append({
            "known_time":int(bars[i][0])+60,
            "bar_idx":i,
            "dir":d,
            "trigger":trigger,
            "stop":stop,
            "risk":risk
        })
    return out,r

def simulate(symbol,bars,point):
    sigs,recon=prepare_signals(bars,point)
    si=0
    pending=None
    pos=None
    rows=[]
    stats=Counter()

    def spread_px(b):
        return max(0,int(b[6]))*point

    def close_position(t,bar,exit_bid,outcome,mi,forced_exit_spread=None):
        nonlocal pos
        d=pos["dir"]
        risk=pos["risk"]

        gross_exit=float(exit_bid)
        if forced_exit_spread is None:
            esp=max(0,int(bar[6]))
        else:
            esp=max(0,int(forced_exit_spread))
        spr=esp*point

        # Long exits by selling at bid. Short exits by buying at ask.
        spread_exit=gross_exit if d>0 else gross_exit+spr

        gross_r=(gross_exit-pos["entry_gross"])/risk if d>0 else (pos["entry_gross"]-gross_exit)/risk
        spread_r=(spread_exit-pos["entry_spread"])/risk if d>0 else (pos["entry_spread"]-spread_exit)/risk

        rows.append({
            "SYMBOL":symbol,
            "SIDE":"LONG" if d>0 else "SHORT",
            "SIGNAL_TIME":pos["signal_time"],
            "ENTRY_TIME":pos["entry_time"],
            "EXIT_TIME":t,
            "ENTRY_TRIGGER":f"{pos['trigger']:.10f}",
            "ENTRY_GROSS":f"{pos['entry_gross']:.10f}",
            "ENTRY_SPREAD":f"{pos['entry_spread']:.10f}",
            "STOP":f"{pos['stop']:.10f}",
            "EXIT_GROSS":f"{gross_exit:.10f}",
            "EXIT_SPREAD":f"{spread_exit:.10f}",
            "GROSS_R":f"{gross_r:.10f}",
            "SPREAD_R":f"{spread_r:.10f}",
            "OUTCOME":outcome,
            "WAIT_M1":pos["entry_mi"]-pos["signal_mi"],
            "HOLD_M1":mi-pos["entry_mi"],
            "ENTRY_SPREAD_POINTS":pos["entry_spread_points"],
            "EXIT_SPREAD_POINTS":esp
        })
        stats[outcome]+=1
        pos=None

    for mi,b in enumerate(bars):
        t=int(b[0])
        op=float(b[1]); hi=float(b[2]); lo=float(b[3])
        sp_points=max(0,int(b[6]))
        spr=sp_points*point

        # A signal is available only after its Iqamat bar has closed.
        while si<len(sigs) and sigs[si]["known_time"]<=t:
            s=sigs[si]; si+=1
            if pos is not None:
                if s["dir"]!=pos["dir"]:
                    # Opposite Iqamat is known at this M1 open.
                    close_position(t,b,op,"OPPOSITE_IQAMAT",mi)
                    pending={"sig":s,"signal_mi":mi}
                else:
                    stats["SAME_DIR_IQAMAT_WHILE_OPEN"]+=1
            else:
                if pending is not None and s["dir"]!=pending["sig"]["dir"]:
                    stats["PENDING_CANCEL_OPPOSITE_IQAMAT"]+=1
                elif pending is not None:
                    stats["PENDING_REFRESH_SAME_DIR"]+=1
                pending={"sig":s,"signal_mi":mi}

        # Pending stop-entry. Trigger is defined on chart/Bid structure.
        if pos is None and pending is not None:
            s=pending["sig"]; d=s["dir"]; tr=s["trigger"]; st=s["stop"]
            hit_entry=(hi>=tr) if d>0 else (lo<=tr)

            # Structural stop before entry invalidates the setup.
            if d>0:
                hit_stop=(lo<=st)
            else:
                # Short stop is a buy-to-cover; Ask crossing stop matters.
                hit_stop=(hi+spr>=st)

            if hit_entry and hit_stop:
                entry_gross=tr
                entry_spread=tr+spr if d>0 else tr
                pos={
                    "dir":d,"trigger":tr,"stop":st,"risk":s["risk"],
                    "entry_gross":entry_gross,"entry_spread":entry_spread,
                    "signal_time":s["known_time"],"entry_time":t,
                    "signal_mi":pending["signal_mi"],"entry_mi":mi,
                    "entry_spread_points":sp_points
                }
                pending=None
                # Conservative same-minute ambiguity: entry then stop.
                stop_bid=st if d>0 else st-spr
                close_position(t,b,stop_bid,"AMBIGUOUS_ENTRY_STOP",mi,sp_points)
                continue

            if hit_stop and not hit_entry:
                stats["PENDING_CANCEL_STOP_INVALIDATION"]+=1
                pending=None
            elif hit_entry:
                entry_gross=tr
                entry_spread=tr+spr if d>0 else tr
                pos={
                    "dir":d,"trigger":tr,"stop":st,"risk":s["risk"],
                    "entry_gross":entry_gross,"entry_spread":entry_spread,
                    "signal_time":s["known_time"],"entry_time":t,
                    "signal_mi":pending["signal_mi"],"entry_mi":mi,
                    "entry_spread_points":sp_points
                }
                pending=None
                stats["ENTRY"]+=1

        # Stop monitoring after entry.
        if pos is not None:
            d=pos["dir"]; st=pos["stop"]
            if d>0:
                stop_hit=(lo<=st)
                stop_bid=st
            else:
                stop_hit=(hi+spr>=st)
                stop_bid=st-spr
            if stop_hit:
                close_position(t,b,stop_bid,"STOP",mi,sp_points)

    if pos is not None:
        b=bars[-1]
        close_position(int(b[0]),b,float(b[4]),"DATA_END",len(bars)-1)

    return rows,stats,len(sigs),recon

def metric(rs):
    if not rs:
        return {"n":0}
    pos=sum(x for x in rs if x>0)
    neg=-sum(x for x in rs if x<0)
    return {
        "n":len(rs),
        "mean":sum(rs)/len(rs),
        "median":statistics.median(rs),
        "sum":sum(rs),
        "win_rate":sum(x>0 for x in rs)/len(rs),
        "profit_factor":(pos/neg if neg>0 else None),
        "min":min(rs),"max":max(rs)
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--bin",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)

    hdr,bars=read_xfbar(a.bin)
    if hdr["period_seconds"]!=60:
        raise SystemExit(f"TM01 requires M1/60 sec, got {hdr['period_seconds']}")
    sym=hdr["symbol"]; point=float(hdr["point"])

    rows,stats,nsig,recon=simulate(sym,bars,point)
    with (a.out/f"{sym}_TM01_TRADES.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";")
        w.writeheader(); w.writerows(rows)

    def subset(side=None):
        rr=rows if side is None else [x for x in rows if x["SIDE"]==side]
        return {
            "gross":metric([float(x["GROSS_R"]) for x in rr]),
            "spread":metric([float(x["SPREAD_R"]) for x in rr])
        }

    summary={
        "block":"TM01",
        "status":"PASS" if rows and not recon["errors"] else "FAIL",
        "symbol":sym,
        "data":hdr,
        "takbir_candidates":len(recon["candidates"]),
        "confirmed_levels":len(recon["levels"]),
        "azan":recon["counts"]["AZAN_UP"]+recon["counts"]["AZAN_DN"],
        "iqamat":nsig,
        "trades":len(rows),
        "outcomes":dict(stats),
        "results":{
            "ALL":subset(),
            "LONG":subset("LONG"),
            "SHORT":subset("SHORT")
        },
        "contract":{
            "timeframe":"M1",
            "takbir_right_confirmation_bars":5,
            "entry_after_iqamat_close":True,
            "entry_trigger":"1 point beyond Iqamat M1 candle extreme",
            "stop":"latest opposite confirmed Yamma/Kimma",
            "exit":"stop or opposite Iqamat or data end",
            "same_bar_entry_stop":"conservative stop",
            "spread":"historical MT4 M1 spread field",
            "fees":False,
            "slippage":False,
            "take_profit":False,
            "pyramiding":False,
            "selection_or_optimization":False,
            "lookahead":False
        }
    }
    (a.out/f"{sym}_TM01.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    g=summary["results"]["ALL"]["gross"]
    s=summary["results"]["ALL"]["spread"]
    lines=[
        "TAKBIR M1 TM01",
        f"STATUS: {summary['status']}",
        f"SYMBOL: {sym}",
        f"M1_BARS: {len(bars)}",
        f"TAKBIR: {summary['takbir_candidates']}",
        f"LEVELS: {summary['confirmed_levels']}",
        f"AZAN: {summary['azan']}",
        f"IQAMAT: {summary['iqamat']}",
        f"TRADES: {len(rows)}",
        f"GROSS: MEAN_R={g.get('mean',0):+.6f} SUM_R={g.get('sum',0):+.3f} WIN={g.get('win_rate',0):.6f} PF={(g.get('profit_factor') or 0):.6f}",
        f"SPREAD: MEAN_R={s.get('mean',0):+.6f} SUM_R={s.get('sum',0):+.3f} WIN={s.get('win_rate',0):.6f} PF={(s.get('profit_factor') or 0):.6f}",
        "FEES: NO",
        "SLIPPAGE: NO",
        "LOOKAHEAD: NO",
        "SELECTION/OPTIMIZATION: NO"
    ]
    (a.out/f"{sym}_TM01.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
    if summary["status"]!="PASS":
        raise SystemExit(2)

if __name__=="__main__":
    main()
