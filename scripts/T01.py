#!/usr/bin/env python3
"""
T01 — TAKBIR causal reconstruction.

Source-faithful frozen core from Tim Stigal, "Graal Imana":
- Takbir = 11-bar pivot: head bar is the unique high/low among 5 bars before + 5 after.
- It becomes known only after the 5th bar after the head has closed.
- Kimma/Yamma must alternate. During an unconfirmed same-side run, keep the
  most extreme candidate (highest HIGH / lowest LOW). A potential angle becomes
  a confirmed Kimma/Yamma only when an opposite Takbir is confirmed.
- Bullish Azan = first close above a descending resistance line through the
  last two confirmed Kimma.
- Bearish Azan = first close below an ascending support line through the last
  two confirmed Yamma.
- Iqamat may occur on the same bar as Azan:
    bullish: close above the latest Kimma;
    bearish: close below the latest Yamma.
No future bar is used before its close. No trading/PnL in T01.
"""
import argparse,csv,json,math
from collections import Counter
from pathlib import Path
from drummond_replay01 import read_xfbar

def takbir_candidates(bars):
    out=[]
    n=len(bars)
    for c in range(5,n-5):
        hi=float(bars[c][2]); lo=float(bars[c][3])
        other_hi=[float(bars[j][2]) for j in range(c-5,c+6) if j!=c]
        other_lo=[float(bars[j][3]) for j in range(c-5,c+6) if j!=c]
        if hi>max(other_hi):
            out.append({"side":"HIGH","head_idx":c,"confirm_idx":c+5,"price":hi})
        if lo<min(other_lo):
            out.append({"side":"LOW","head_idx":c,"confirm_idx":c+5,"price":lo})
    out.sort(key=lambda x:(x["confirm_idx"],x["head_idx"],x["side"]))
    return out

def confirmed_levels(cands):
    levels=[]; pending=None; replaced=0; ignored=0
    for x in cands:
        if pending is None:
            pending=dict(x); continue
        if x["side"]==pending["side"]:
            better=(x["price"]>pending["price"]) if x["side"]=="HIGH" else (x["price"]<pending["price"])
            if better:
                pending=dict(x); replaced+=1
            else:
                ignored+=1
            continue
        # Opposite Takbir confirms the previous potential angle.
        levels.append({
          "kind":"KIMMA" if pending["side"]=="HIGH" else "YAMMA",
          "head_idx":pending["head_idx"],"takbir_confirm_idx":pending["confirm_idx"],
          "known_idx":x["confirm_idx"],"price":pending["price"]
        })
        pending=dict(x)
    return levels,pending,replaced,ignored

def line_value(a,b,idx):
    dx=b["head_idx"]-a["head_idx"]
    if dx<=0:return None
    return a["price"]+(b["price"]-a["price"])*(idx-a["head_idx"])/dx

def reconstruct(bars):
    cands=takbir_candidates(bars)
    levels,pending,replaced,ignored=confirmed_levels(cands)
    by_known={}
    for lv in levels: by_known.setdefault(lv["known_idx"],[]).append(lv)

    kim=[]; yam=[]; events=[]
    used_bull=set();used_bear=set()
    pending_sig=None
    start=0
    counts=Counter()

    for i in range(len(bars)):
        for lv in by_known.get(i,[]):
            (kim if lv["kind"]=="KIMMA" else yam).append(lv)

        close=float(bars[i][4])
        prev_close=float(bars[i-1][4]) if i>0 else close

        candidates=[]
        if len(kim)>=2:
            a,b=kim[-2],kim[-1]
            # source-faithful downtrend resistance: later Kimma is not higher
            if b["price"]<=a["price"] and i>=max(a["known_idx"],b["known_idx"]):
                key=(a["head_idx"],b["head_idx"])
                y=line_value(a,b,i); yp=line_value(a,b,i-1) if i>0 else None
                if y is not None and yp is not None and prev_close<=yp and close>y and key not in used_bull:
                    candidates.append((+1,"AZAN_UP",key,b["price"],y))
        if len(yam)>=2:
            a,b=yam[-2],yam[-1]
            # source-faithful uptrend support: later Yamma is not lower
            if b["price"]>=a["price"] and i>=max(a["known_idx"],b["known_idx"]):
                key=(a["head_idx"],b["head_idx"])
                y=line_value(a,b,i); yp=line_value(a,b,i-1) if i>0 else None
                if y is not None and yp is not None and prev_close>=yp and close<y and key not in used_bear:
                    candidates.append((-1,"AZAN_DN",key,b["price"],y))

        # Deterministic collision handling: larger normalized break of its line.
        if candidates:
            if len(candidates)>1:
                counts["AZAN_COLLISION"]+=1
                candidates.sort(key=lambda z:abs(close-z[4]),reverse=True)
            d,etype,key,thr,linep=candidates[0]
            if d>0:used_bull.add(key)
            else:used_bear.add(key)
            pending_sig={"dir":d,"azan_idx":i,"threshold":thr,"line":linep}
            events.append({"type":etype,"idx":i,"dir":d,"price":close,"threshold":thr})
            counts[etype]+=1

        # Iqamat is allowed on the Azan bar, as shown in the book.
        if pending_sig is not None:
            d=pending_sig["dir"];thr=pending_sig["threshold"]
            if (d>0 and close>thr) or (d<0 and close<thr):
                et="IQAMAT_UP" if d>0 else "IQAMAT_DN"
                events.append({
                  "type":et,"idx":i,"dir":d,"price":close,"threshold":thr,
                  "azan_idx":pending_sig["azan_idx"],
                  "wait_bars":i-pending_sig["azan_idx"]
                })
                counts[et]+=1
                pending_sig=None

    # invariants
    errs=[]
    for x in cands:
        if x["confirm_idx"]!=x["head_idx"]+5: errs.append("TAKBIR_CONFIRM_OFFSET")
    for j in range(1,len(levels)):
        if levels[j]["kind"]==levels[j-1]["kind"]: errs.append("LEVEL_ALTERNATION")
        if levels[j]["known_idx"]<levels[j]["takbir_confirm_idx"]: errs.append("LEVEL_KNOWN_BEFORE_TAKBIR")
    for e in events:
        if e["type"].startswith("IQAMAT") and e["idx"]<e["azan_idx"]: errs.append("IQAMAT_BEFORE_AZAN")
    return {
      "candidates":cands,"levels":levels,"events":events,
      "pending_level":pending,"same_side_replaced":replaced,"same_side_ignored":ignored,
      "counts":counts,"errors":sorted(set(errs))
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)

    sums=Counter(); skips=Counter(); errs=[]; symbol_rows=[]; syms=0
    for p in sorted(a.data_root.rglob("*_H1.bin")):
        sym=p.name[:-7]
        try:
            h4s=list(a.data_root.rglob(f"{sym}_H4.bin"))
            m5s=list(a.data_root.rglob(f"{sym}_M5.bin"))
            if not h4s: skips["SKIP_NO_H4"]+=1; continue
            if not m5s: skips["SKIP_NO_M5"]+=1; continue
            if len(h4s)!=1 or len(m5s)!=1: raise RuntimeError("duplicate required TF")
            hdr,bars=read_xfbar(p)
            if hdr["period_seconds"]!=3600:continue
            r=reconstruct(bars); syms+=1
            c=r["counts"]
            row={
              "SYMBOL":sym,"BARS":len(bars),
              "TAKBIR":len(r["candidates"]),"LEVELS":len(r["levels"]),
              "KIMMA":sum(x["kind"]=="KIMMA" for x in r["levels"]),
              "YAMMA":sum(x["kind"]=="YAMMA" for x in r["levels"]),
              "AZAN_UP":c["AZAN_UP"],"AZAN_DN":c["AZAN_DN"],
              "IQAMAT_UP":c["IQAMAT_UP"],"IQAMAT_DN":c["IQAMAT_DN"],
              "SAME_SIDE_REPLACED":r["same_side_replaced"],
              "SAME_SIDE_IGNORED":r["same_side_ignored"],
              "ERRORS":len(r["errors"])
            }
            symbol_rows.append(row)
            for k,v in row.items():
                if k not in ("SYMBOL",): 
                    if isinstance(v,int): sums[k]+=v
            if r["errors"]:errs.append({"symbol":sym,"errors":r["errors"]})
        except Exception as e:
            errs.append({"symbol":sym,"errors":[str(e)]})

    fields=["SYMBOL","BARS","TAKBIR","LEVELS","KIMMA","YAMMA","AZAN_UP","AZAN_DN","IQAMAT_UP","IQAMAT_DN","SAME_SIDE_REPLACED","SAME_SIDE_IGNORED","ERRORS"]
    with (a.out/"T01.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";");w.writeheader();w.writerows(symbol_rows)

    az=sums["AZAN_UP"]+sums["AZAN_DN"];iq=sums["IQAMAT_UP"]+sums["IQAMAT_DN"]
    summary={
      "block":"T01","status":"PASS" if syms and not errs else "FAIL",
      "symbols":syms,"totals":dict(sums),
      "azan_total":az,"iqamat_total":iq,
      "iqamat_per_azan":(iq/az if az else None),
      "errors":len(errs),"skips":dict(skips),
      "contract":{
        "takbir_11_bar":True,"five_bars_right_required":True,
        "strict_unique_extreme":True,"levels_alternate":True,
        "potential_level_confirmed_by_opposite_takbir":True,
        "azan_close_break":True,"iqamat_close_break":True,
        "same_bar_azan_iqamat_allowed":True,
        "canonical_universe_requires_h1_h4_m5":True,
        "trading_pnl":False,"lookahead":False,"selection_or_optimization":False
      },
      "reconstruction_notes":[
        "Same-side Takbirs before the next opposite Takbir are compressed causally to the most extreme candidate.",
        "Bullish Azan uses a non-rising Kimma resistance line; bearish Azan uses a non-falling Yamma support line.",
        "These deterministic choices formalize ambiguous prose and are frozen before statistical testing."
      ]
    }
    (a.out/"T01.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.out/"T01_ERR.json").write_text(json.dumps(errs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"T01 {summary['status']} symbols={syms} takbir={sums['TAKBIR']} levels={sums['LEVELS']} azan={az} iqamat={iq} iq/az={(iq/az if az else 0):.6f} skips={dict(skips)} errors={len(errs)}")
    if summary["status"]!="PASS":raise SystemExit(2)

if __name__=="__main__":
    main()
