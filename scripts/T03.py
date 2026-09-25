#!/usr/bin/env python3
"""
T03 — TAKBIR source-faithful H1 signal -> M5 execution backtest.

Frozen lifecycle from the book:
- Setup/confirmation = causal T01 Iqamat on closed H1 bar.
- Entry stop-order = 1 point beyond the Iqamat H1 candle extreme:
    LONG  at Iqamat-bar HIGH + 1 point
    SHORT at Iqamat-bar LOW  - 1 point
- Structural stop:
    LONG  = latest confirmed Yamma known at Iqamat
    SHORT = latest confirmed Kimma known at Iqamat
- Exit = first opposite Iqamat (executed at first M5 open after that H1 closes),
         or structural stop, or data end.
- One position per symbol, no pyramiding.
- Pending setup is replaced by a newer same-direction Iqamat and cancelled by
  an opposite Iqamat or pre-entry structural invalidation.
- M5 bar where entry and stop are both touched is counted conservatively as
  an immediate stop loss (R=-1).

No TP. No fitted parameters. No spread/commission/slippage model yet.
"""
import argparse,csv,json,math
from collections import Counter
from pathlib import Path
from drummond_replay01 import read_xfbar
from T01 import reconstruct

FIELDS=["SYMBOL","SIDE","SIGNAL_TIME","ENTRY_TIME","EXIT_TIME","ENTRY","STOP","EXIT","R","OUTCOME","WAIT_M5","HOLD_M5"]

def signals_from_h1(bars,point):
    r=reconstruct(bars)
    if r["errors"]:raise RuntimeError(",".join(r["errors"]))
    levels=r["levels"]
    sigs=[]
    for e in r["events"]:
        if not e["type"].startswith("IQAMAT"):continue
        i=int(e["idx"]);d=int(e["dir"])
        known=[lv for lv in levels if lv["known_idx"]<=i]
        opp_kind="YAMMA" if d>0 else "KIMMA"
        opp=[lv for lv in known if lv["kind"]==opp_kind]
        if not opp:continue
        stop=float(opp[-1]["price"])
        trigger=(float(bars[i][2])+point) if d>0 else (float(bars[i][3])-point)
        risk=(trigger-stop) if d>0 else (stop-trigger)
        if not math.isfinite(risk) or risk<=point*0.5:continue
        sigs.append({
          "time":int(bars[i][0])+3600,"dir":d,"trigger":trigger,"stop":stop,
          "h1_idx":i
        })
    return sigs,r

def simulate(sym,h1,m5,point):
    sigs,_=signals_from_h1(h1,point)
    si=0;pending=None;pos=None;trades=[];stats=Counter()
    m5n=len(m5)

    def close_pos(t,price,outcome,mi):
        nonlocal pos
        d=pos["dir"];risk=pos["risk"]
        rr=(price-pos["entry"])/risk if d>0 else (pos["entry"]-price)/risk
        trades.append({
          "SYMBOL":sym,"SIDE":"LONG" if d>0 else "SHORT",
          "SIGNAL_TIME":pos["signal_time"],"ENTRY_TIME":pos["entry_time"],"EXIT_TIME":t,
          "ENTRY":f"{pos['entry']:.10f}","STOP":f"{pos['stop']:.10f}","EXIT":f"{price:.10f}",
          "R":f"{rr:.10f}","OUTCOME":outcome,
          "WAIT_M5":pos["entry_mi"]-pos["signal_mi"],"HOLD_M5":mi-pos["entry_mi"]
        })
        stats[outcome]+=1;pos=None

    for mi,b in enumerate(m5):
        t=int(b[0]);op=float(b[1]);hi=float(b[2]);lo=float(b[3]);cl=float(b[4])

        # Signals known before this M5 bar starts.
        while si<len(sigs) and sigs[si]["time"]<=t:
            s=sigs[si];si+=1
            if pos is not None:
                if s["dir"]!=pos["dir"]:
                    close_pos(t,op,"OPPOSITE_IQAMAT",mi)
                    pending={"sig":s,"signal_mi":mi}
                else:
                    stats["SAME_DIR_IQAMAT_WHILE_OPEN"]+=1
            else:
                if pending is not None and s["dir"]!=pending["sig"]["dir"]:
                    stats["PENDING_CANCEL_OPPOSITE_IQAMAT"]+=1
                elif pending is not None:
                    stats["PENDING_REFRESH_SAME_DIR"]+=1
                pending={"sig":s,"signal_mi":mi}

        if pos is None and pending is not None:
            s=pending["sig"];d=s["dir"];tr=s["trigger"];st=s["stop"]
            hit_tr=(hi>=tr) if d>0 else (lo<=tr)
            hit_st=(lo<=st) if d>0 else (hi>=st)
            if hit_tr and hit_st:
                # Conservative intrabar ambiguity: assume entry then stop.
                risk=(tr-st) if d>0 else (st-tr)
                pos={"dir":d,"entry":tr,"stop":st,"risk":risk,"signal_time":s["time"],
                     "entry_time":t,"signal_mi":pending["signal_mi"],"entry_mi":mi}
                pending=None
                close_pos(t,st,"AMBIGUOUS_ENTRY_STOP",mi)
                continue
            if hit_st and not hit_tr:
                stats["PENDING_CANCEL_STOP_INVALIDATION"]+=1;pending=None
            elif hit_tr:
                risk=(tr-st) if d>0 else (st-tr)
                pos={"dir":d,"entry":tr,"stop":st,"risk":risk,"signal_time":s["time"],
                     "entry_time":t,"signal_mi":pending["signal_mi"],"entry_mi":mi}
                pending=None;stats["ENTRY"]+=1

        if pos is not None:
            d=pos["dir"];st=pos["stop"]
            hit=(lo<=st) if d>0 else (hi>=st)
            if hit:
                close_pos(t,st,"STOP",mi)

    if pos is not None:
        close_pos(int(m5[-1][0]),float(m5[-1][4]),"DATA_END",m5n-1)
    return trades,stats,len(sigs)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    alltr=[];tot=Counter();errs=[];skips=Counter();syms=0;signals=0
    for h1p in sorted(a.data_root.rglob("*_H1.bin")):
        sym=h1p.name[:-7]
        try:
            h4s=list(a.data_root.rglob(f"{sym}_H4.bin"));m5s=list(a.data_root.rglob(f"{sym}_M5.bin"))
            if not h4s:skips["SKIP_NO_H4"]+=1;continue
            if not m5s:skips["SKIP_NO_M5"]+=1;continue
            if len(h4s)!=1 or len(m5s)!=1:raise RuntimeError("duplicate required TF")
            hh,h1=read_xfbar(h1p);mh,m5=read_xfbar(m5s[0])
            if hh["period_seconds"]!=3600 or mh["period_seconds"]!=300:raise RuntimeError("TF contract")
            point=float(hh["point"]);tr,st,ns=simulate(sym,h1,m5,point)
            syms+=1;signals+=ns;alltr.extend(tr);tot.update(st)
        except Exception as e:
            errs.append({"symbol":sym,"error":str(e)})

    with (a.out/"T03.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";");w.writeheader();w.writerows(alltr)
    rs=[float(x["R"]) for x in alltr]
    wins=sum(x>0 for x in rs)
    out={
      "block":"T03","status":"PASS" if syms and alltr and not errs else "FAIL",
      "symbols":syms,"iqamat_signals":signals,"trades":len(alltr),
      "mean_r":sum(rs)/len(rs) if rs else None,"win_rate":wins/len(rs) if rs else None,
      "outcomes":dict(tot),"skips":dict(skips),"errors":len(errs),
      "contract":{
        "source":"book-faithful Iqamat breakout lifecycle over frozen T01 geometry",
        "entry":"1 point beyond Iqamat H1 candle extreme",
        "execution":"M5 after signal H1 close",
        "stop":"latest opposite confirmed Yamma/Kimma known at signal",
        "exit":"opposite Iqamat or stop or data end",
        "pyramiding":False,"take_profit":False,
        "spread_slippage_fees":False,
        "ambiguous_entry_stop":"conservative immediate stop",
        "selection_or_optimization":False,"lookahead":False
      }
    }
    (a.out/"T03.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.out/"T03_ERR.json").write_text(json.dumps(errs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"T03 {out['status']} symbols={syms} signals={signals} trades={len(alltr)} meanR={(out['mean_r'] or 0):+.6f} win={(out['win_rate'] or 0):.6f} outcomes={dict(tot)} errors={len(errs)}")
    if out["status"]!="PASS":raise SystemExit(2)
if __name__=="__main__":main()
