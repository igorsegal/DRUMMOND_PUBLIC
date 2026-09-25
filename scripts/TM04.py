#!/usr/bin/env python3
"""
TM04 — XAUUSD price-only 11-bar channel breakout control.

Purpose: test whether a generic price breakout on the same M1 data can reproduce
the kind of gross expectancy seen in TAKBIR TM01.

Frozen control, no fitting:
- lookback = 11 completed M1 bars (chosen before the run because TAKBIR's basic
  pivot window is 11 bars; this is not optimized)
- bullish signal: close of bar i > highest HIGH of the previous 11 closed bars
- bearish signal: close of bar i < lowest LOW of the previous 11 closed bars
- signal becomes tradable only after bar i closes
- long entry stop = signal-bar HIGH + 1 point
- short entry stop = signal-bar LOW - 1 point
- long structural stop = lowest LOW of previous 11 bars at signal
- short structural stop = highest HIGH of previous 11 bars at signal
- exit = structural stop, opposite channel signal at next M1 open, or data end
- one position, no pyramiding; same-direction pending refreshes, opposite cancels
- same-bar entry+stop ambiguity is resolved conservatively as a stop
"""
import argparse,csv,json,math,statistics
from collections import Counter,deque
from pathlib import Path
from drummond_replay01 import read_xfbar

LOOKBACK=11
POINT_COSTS=(0,1,2,5,10)

def metric(vals):
    if not vals:return {"n":0}
    pos=sum(x for x in vals if x>0)
    neg=-sum(x for x in vals if x<0)
    return {
        "n":len(vals),"mean":sum(vals)/len(vals),"median":statistics.median(vals),
        "sum":sum(vals),"win_rate":sum(x>0 for x in vals)/len(vals),
        "profit_factor":pos/neg if neg>0 else None,"min":min(vals),"max":max(vals)
    }

def signals(bars,point):
    # Monotonic deques over PREVIOUS 11 bars.
    maxq=deque(); minq=deque()
    out=[]
    for i,b in enumerate(bars):
        # queues currently contain indices < i, pruned to last LOOKBACK
        lo_keep=i-LOOKBACK
        while maxq and maxq[0]<lo_keep:maxq.popleft()
        while minq and minq[0]<lo_keep:minq.popleft()

        if i>=LOOKBACK and maxq and minq:
            prev_hi=float(bars[maxq[0]][2])
            prev_lo=float(bars[minq[0]][3])
            close=float(b[4])
            if close>prev_hi:
                stop=prev_lo
                trigger=float(b[2])+point
                risk=trigger-stop
                if risk>point*0.5 and math.isfinite(risk):
                    out.append({"known_time":int(b[0])+60,"bar_idx":i,"dir":1,
                                "trigger":trigger,"stop":stop,"risk":risk})
            elif close<prev_lo:
                stop=prev_hi
                trigger=float(b[3])-point
                risk=stop-trigger
                if risk>point*0.5 and math.isfinite(risk):
                    out.append({"known_time":int(b[0])+60,"bar_idx":i,"dir":-1,
                                "trigger":trigger,"stop":stop,"risk":risk})

        # add current bar for future signals
        hi=float(b[2]); lo=float(b[3])
        while maxq and float(bars[maxq[-1]][2])<=hi:maxq.pop()
        maxq.append(i)
        while minq and float(bars[minq[-1]][3])>=lo:minq.pop()
        minq.append(i)
    return out

def simulate(bars,point):
    sigs=signals(bars,point)
    si=0;pending=None;pos=None;rows=[];stats=Counter()

    def close_pos(t,price,outcome,mi):
        nonlocal pos
        d=pos["dir"]; risk=pos["risk"]
        r=(price-pos["entry"])/risk if d>0 else (pos["entry"]-price)/risk
        rows.append({
            "SIDE":"LONG" if d>0 else "SHORT",
            "SIGNAL_TIME":pos["signal_time"],"ENTRY_TIME":pos["entry_time"],"EXIT_TIME":t,
            "ENTRY":pos["entry"],"STOP":pos["stop"],"EXIT":price,
            "RISK_POINTS":risk/point,"GROSS_R":r,"OUTCOME":outcome,
            "WAIT_M1":pos["entry_mi"]-pos["signal_mi"],
            "HOLD_M1":mi-pos["entry_mi"]
        })
        stats[outcome]+=1;pos=None

    for mi,b in enumerate(bars):
        t=int(b[0]);op=float(b[1]);hi=float(b[2]);lo=float(b[3])

        while si<len(sigs) and sigs[si]["known_time"]<=t:
            s=sigs[si];si+=1
            if pos is not None:
                if s["dir"]!=pos["dir"]:
                    close_pos(t,op,"OPPOSITE_CHANNEL",mi)
                    pending={"sig":s,"signal_mi":mi}
                else:
                    stats["SAME_DIR_SIGNAL_WHILE_OPEN"]+=1
            else:
                if pending is not None and s["dir"]!=pending["sig"]["dir"]:
                    stats["PENDING_CANCEL_OPPOSITE"]+=1
                elif pending is not None:
                    stats["PENDING_REFRESH_SAME_DIR"]+=1
                pending={"sig":s,"signal_mi":mi}

        if pos is None and pending is not None:
            s=pending["sig"];d=s["dir"];tr=s["trigger"];st=s["stop"]
            hit_entry=(hi>=tr) if d>0 else (lo<=tr)
            hit_stop=(lo<=st) if d>0 else (hi>=st)
            if hit_entry and hit_stop:
                pos={"dir":d,"entry":tr,"stop":st,"risk":s["risk"],
                     "signal_time":s["known_time"],"entry_time":t,
                     "signal_mi":pending["signal_mi"],"entry_mi":mi}
                pending=None
                close_pos(t,st,"AMBIGUOUS_ENTRY_STOP",mi)
                continue
            if hit_stop and not hit_entry:
                stats["PENDING_CANCEL_STOP_INVALIDATION"]+=1
                pending=None
            elif hit_entry:
                pos={"dir":d,"entry":tr,"stop":st,"risk":s["risk"],
                     "signal_time":s["known_time"],"entry_time":t,
                     "signal_mi":pending["signal_mi"],"entry_mi":mi}
                pending=None;stats["ENTRY"]+=1

        if pos is not None:
            st=pos["stop"];d=pos["dir"]
            if (d>0 and lo<=st) or (d<0 and hi>=st):
                close_pos(t,st,"STOP",mi)

    if pos is not None:
        b=bars[-1]
        close_pos(int(b[0]),float(b[4]),"DATA_END",len(bars)-1)
    return sigs,rows,stats

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--bin",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    hdr,bars=read_xfbar(a.bin)
    if hdr["symbol"]!="XAUUSD" or hdr["period_seconds"]!=60:
        raise SystemExit("TM04 requires XAUUSD M1")
    point=float(hdr["point"])
    sigs,rows,stats=simulate(bars,point)

    fields=["SIDE","SIGNAL_TIME","ENTRY_TIME","EXIT_TIME","ENTRY","STOP","EXIT",
            "RISK_POINTS","GROSS_R","OUTCOME","WAIT_M1","HOLD_M1"]
    with (a.out/"TM04_TRADES.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";");w.writeheader();w.writerows(rows)

    results={}
    scopes={"ALL":rows,"LONG":[r for r in rows if r["SIDE"]=="LONG"],
            "SHORT":[r for r in rows if r["SIDE"]=="SHORT"]}
    for scope,rr in scopes.items():
        results[scope]={}
        for pts in POINT_COSTS:
            vals=[r["GROSS_R"]-pts/r["RISK_POINTS"] for r in rr]
            results[scope][str(pts)]=metric(vals)

    summary={
        "block":"TM04","status":"PASS" if rows else "FAIL",
        "symbol":"XAUUSD","bars":len(bars),"signals":len(sigs),"trades":len(rows),
        "outcomes":dict(stats),"results":results,
        "contract":{
            "control":"price-only 11-bar channel breakout",
            "lookback_bars":LOOKBACK,"entry_buffer_points":1,
            "exit":"structural stop or opposite channel signal or data end",
            "selection_or_optimization":False,"lookahead":False,
            "note":"11-bar lookback frozen from TAKBIR base window, not optimized"
        }
    }
    (a.out/"TM04.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
        "TAKBIR M1 TM04 — XAUUSD PRICE-ONLY 11-BAR CONTROL",
        f"STATUS: {summary['status']}",
        f"M1_BARS: {len(bars)}",
        f"SIGNALS: {len(sigs)}",
        f"TRADES: {len(rows)}",
        "LOOKAHEAD: NO",
        "SELECTION/OPTIMIZATION: NO"
    ]
    for scope in ("ALL","LONG","SHORT"):
        lines.append(scope+":")
        for pts in POINT_COSTS:
            m=results[scope][str(pts)]
            lines.append(f"  COST {pts}pt: N={m['n']} MEAN_R={m.get('mean',0):+.6f} SUM_R={m.get('sum',0):+.1f} PF={(m.get('profit_factor') or 0):.6f}")
    (a.out/"TM04.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
    if summary["status"]!="PASS":raise SystemExit(2)

if __name__=="__main__":
    main()
