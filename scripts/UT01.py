#!/usr/bin/env python3
"""
UT01 — "Smart Trading" Fibonacci claim audit on XAUUSD M1.

Source-derived claims under test (Boguraev, "Умная торговля"):
- B retracement of A: no more than 88.2%; crossing 88.2% cancels proposed B.
- FZR confirmation: subsequent C-side move breaks 88.2% of B.
- C relative to A: 123.6%–161.8% is presented as the normal/average zone.

This block DOES NOT attempt to automate the author's full Elliott wave labelling.
Instead it uses one frozen, objective swing proxy:
- strict unique 11-bar pivot (5 bars left + pivot + 5 bars right)
- consecutive same-side pivot candidates are compressed to the most extreme
  until an opposite candidate arrives.
The proxy is deliberately generic and is used only to test whether the cited
Fibonacci numbers create visible structural discontinuities/clustering.

No trading, no PnL, no fitting, no parameter optimization.
"""
import argparse,csv,json,math,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from drummond_replay01 import read_xfbar

B_THRESHOLDS=[0.80,0.85,0.882,0.90,0.95,1.00]
C_CONFIRM_THRESHOLDS=[0.80,0.85,0.882,0.90,0.95]
C_TARGETS=[1.20,1.236,1.30,1.382,1.50,1.618,1.70,2.00]
B_BINS=[
    ("0-.500",0.0,0.5),
    (".500-.618",0.5,0.618),
    (".618-.764",0.618,0.764),
    (".764-.800",0.764,0.80),
    (".800-.850",0.80,0.85),
    (".850-.882",0.85,0.882),
    (".882-.914",0.882,0.914),
    (".914-.950",0.914,0.95),
    (".950-1.000",0.95,1.0),
    ("1.000-1.200",1.0,1.2),
    ("1.200+",1.2,None),
]
TARGET_LEVELS=[1.236,1.382,1.618]
TARGET_HALF_WIDTH=0.02

def strict_11bar_candidates(bars):
    out=[]
    n=len(bars)
    for c in range(5,n-5):
        hi=float(bars[c][2]);lo=float(bars[c][3])
        max_other=-math.inf;min_other=math.inf
        for j in range(c-5,c+6):
            if j==c:continue
            h=float(bars[j][2]);l=float(bars[j][3])
            if h>max_other:max_other=h
            if l<min_other:min_other=l
        if hi>max_other:
            out.append((1,c,c+5,hi))
        if lo<min_other:
            out.append((-1,c,c+5,lo))
    out.sort(key=lambda x:(x[2],x[1],x[0]))
    return out

def alternating_swings(cands):
    piv=[]
    pending=None
    same_replace=0;same_ignore=0
    for x in cands:
        if pending is None:
            pending=x;continue
        if x[0]==pending[0]:
            better=(x[3]>pending[3]) if x[0]>0 else (x[3]<pending[3])
            if better:
                pending=x;same_replace+=1
            else:
                same_ignore+=1
            continue
        piv.append(pending)
        pending=x
    return piv,same_replace,same_ignore

def build_patterns(bars,piv):
    rows=[]
    # A=p0->p1, B=p1->p2, C=p2->p3. Alternation guarantees A and C same direction.
    for k in range(len(piv)-3):
        p0,p1,p2,p3=piv[k:k+4]
        a=abs(p1[3]-p0[3]);b=abs(p2[3]-p1[3]);c=abs(p3[3]-p2[3])
        if a<=0 or b<=0 or c<=0:continue
        d=1 if p1[3]>p0[3] else -1
        # Consistency guard.
        if (1 if p2[3]>p1[3] else -1)==d:continue
        if (1 if p3[3]>p2[3] else -1)!=d:continue
        t=int(bars[p2[1]][0])
        rows.append({
            "k":k,"year":datetime.fromtimestamp(t,tz=timezone.utc).year,
            "dir":d,"b_a":b/a,"c_b":c/b,"c_a":c/a,
            "a":a,"b":b,"c":c,
            "p0_idx":p0[1],"p1_idx":p1[1],"p2_idx":p2[1],"p3_idx":p3[1]
        })
    return rows

def prop(rows,pred):
    if not rows:return None
    return sum(1 for r in rows if pred(r))/len(rows)

def safe(x):
    return None if x is None or not math.isfinite(x) else x

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--bin",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    hdr,bars=read_xfbar(a.bin)
    if hdr["symbol"]!="XAUUSD" or hdr["period_seconds"]!=60:
        raise SystemExit("UT01 requires XAUUSD M1")

    cands=strict_11bar_candidates(bars)
    piv,repl,ign=alternating_swings(cands)
    pats=build_patterns(bars,piv)
    if not pats:raise SystemExit("no patterns")

    threshold_rows=[]
    for bt in B_THRESHOLDS:
        valid=[r for r in pats if r["b_a"]<=bt]
        for ct in C_CONFIRM_THRESHOLDS:
            fzr=[r for r in valid if r["c_b"]>=ct]
            row={
                "B_MAX":bt,"C_CONFIRM_B":ct,
                "ALL_PATTERNS":len(pats),"B_VALID":len(valid),"FZR":len(fzr),
                "B_VALID_RATE":len(valid)/len(pats),
                "FZR_RATE_WITHIN_B_VALID":len(fzr)/len(valid) if valid else None,
                "C_A_MEAN":statistics.fmean(r["c_a"] for r in fzr) if fzr else None,
                "C_A_MEDIAN":statistics.median(r["c_a"] for r in fzr) if fzr else None,
            }
            for t in C_TARGETS:
                row[f"HIT_C_A_{str(t).replace('.','_')}"]=prop(fzr,lambda r,t=t:r["c_a"]>=t)
            threshold_rows.append(row)

    # B-ratio neighborhoods: does 88.2 create a break in future C behavior?
    bin_rows=[]
    for name,lo,hi in B_BINS:
        rr=[r for r in pats if r["b_a"]>=lo and (hi is None or r["b_a"]<hi)]
        if not rr:continue
        bin_rows.append({
            "B_RATIO_BIN":name,"N":len(rr),
            "C_B_GE_0_882":prop(rr,lambda r:r["c_b"]>=0.882),
            "C_A_GE_1_236":prop(rr,lambda r:r["c_a"]>=1.236),
            "C_A_GE_1_382":prop(rr,lambda r:r["c_a"]>=1.382),
            "C_A_GE_1_618":prop(rr,lambda r:r["c_a"]>=1.618),
            "MEAN_C_A":statistics.fmean(r["c_a"] for r in rr),
            "MEDIAN_C_A":statistics.median(r["c_a"] for r in rr),
        })

    # Exact book setup: B <= .882 and C retraces/extends >= .882 of B.
    book=[r for r in pats if r["b_a"]<=0.882 and r["c_b"]>=0.882]

    # Do terminal C/A swing ratios cluster near 1.236 / 1.382 / 1.618?
    density=[]
    for t in TARGET_LEVELS:
        hw=TARGET_HALF_WIDTH
        center=[r for r in book if t-hw<=r["c_a"]<t+hw]
        left=[r for r in book if t-3*hw<=r["c_a"]<t-hw]
        right=[r for r in book if t+hw<=r["c_a"]<t+3*hw]
        base=(len(left)+len(right))/2
        density.append({
            "TARGET":t,"WINDOW_HALF_WIDTH":hw,
            "CENTER_N":len(center),"LEFT_ADJACENT_N":len(left),"RIGHT_ADJACENT_N":len(right),
            "CENTER_VS_ADJACENT_MEAN_RATIO":len(center)/base if base>0 else None,
            "BOOK_FZR_N":len(book)
        })

    # Year stability for the exact-book rule.
    year_rows=[]
    for y in sorted({r["year"] for r in pats}):
        yy=[r for r in pats if r["year"]==y]
        valid=[r for r in yy if r["b_a"]<=0.882]
        fzr=[r for r in valid if r["c_b"]>=0.882]
        year_rows.append({
            "YEAR":y,"PATTERNS":len(yy),"B_LE_0_882":len(valid),"FZR_0_882":len(fzr),
            "FZR_RATE_WITHIN_VALID":len(fzr)/len(valid) if valid else None,
            "HIT_1_236":prop(fzr,lambda r:r["c_a"]>=1.236),
            "HIT_1_382":prop(fzr,lambda r:r["c_a"]>=1.382),
            "HIT_1_618":prop(fzr,lambda r:r["c_a"]>=1.618),
        })

    # Symmetric boundary comparison immediately around .882.
    below=[r for r in pats if 0.85<=r["b_a"]<0.882]
    above=[r for r in pats if 0.882<=r["b_a"]<0.914]
    boundary={
        "below_band":"0.850-0.882","above_band":"0.882-0.914",
        "below_n":len(below),"above_n":len(above),
        "below_c_b_ge_0_882":prop(below,lambda r:r["c_b"]>=0.882),
        "above_c_b_ge_0_882":prop(above,lambda r:r["c_b"]>=0.882),
        "delta_confirmation_rate":(
            prop(below,lambda r:r["c_b"]>=0.882)-prop(above,lambda r:r["c_b"]>=0.882)
            if below and above else None
        ),
        "below_hit_1_236":prop(below,lambda r:r["c_a"]>=1.236),
        "above_hit_1_236":prop(above,lambda r:r["c_a"]>=1.236),
        "below_hit_1_382":prop(below,lambda r:r["c_a"]>=1.382),
        "above_hit_1_382":prop(above,lambda r:r["c_a"]>=1.382),
        "below_hit_1_618":prop(below,lambda r:r["c_a"]>=1.618),
        "above_hit_1_618":prop(above,lambda r:r["c_a"]>=1.618),
    }

    def write(name,rows):
        if not rows:return
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0].keys()),delimiter=";")
            w.writeheader();w.writerows(rows)

    write("UT01_THRESHOLDS.csv",threshold_rows)
    write("UT01_B_RATIO_BINS.csv",bin_rows)
    write("UT01_TARGET_DENSITY.csv",density)
    write("UT01_YEARLY.csv",year_rows)

    summary={
        "block":"UT01","status":"PASS",
        "symbol":"XAUUSD","timeframe":"M1","bars":len(bars),
        "pivot_candidates":len(cands),"alternating_pivots":len(piv),
        "patterns_ABC":len(pats),"same_side_replaced":repl,"same_side_ignored":ign,
        "book_0_882":{
            "b_valid":sum(r["b_a"]<=0.882 for r in pats),
            "fzr":len(book),
            "fzr_rate_within_b_valid":len(book)/sum(r["b_a"]<=0.882 for r in pats),
            "hit_1_236":prop(book,lambda r:r["c_a"]>=1.236),
            "hit_1_382":prop(book,lambda r:r["c_a"]>=1.382),
            "hit_1_618":prop(book,lambda r:r["c_a"]>=1.618),
            "mean_c_a":statistics.fmean(r["c_a"] for r in book),
            "median_c_a":statistics.median(r["c_a"] for r in book),
        },
        "boundary_0_882":boundary,
        "target_density":density,
        "contract":{
            "trading_or_pnl":False,
            "parameter_optimization":False,
            "full_author_wave_labelling_claimed":False,
            "swing_proxy":"strict unique 11-bar pivot, 5 left + 5 right; same-side candidates compressed to most extreme",
            "purpose":"test whether book Fibonacci thresholds show structural discontinuity/clustering under an objective frozen swing proxy",
            "book_claims_tested":["B/A <= 0.882","C/B >= 0.882 confirms FZR","C/A zone 1.236-1.618"]
        }
    }
    (a.out/"UT01.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    b=summary["book_0_882"];bd=boundary
    lines=[
        "SMART TRADING UT01 — FIBONACCI CLAIM AUDIT",
        "STATUS: PASS",
        "SYMBOL: XAUUSD M1",
        f"BARS: {len(bars)}",
        f"PIVOT_CANDIDATES: {len(cands)}",
        f"ALTERNATING_PIVOTS: {len(piv)}",
        f"ABC_PATTERNS: {len(pats)}",
        "TRADING/PNL: NO",
        "OPTIMIZATION: NO",
        "",
        f"BOOK 88.2: B_VALID={b['b_valid']} FZR={b['fzr']} FZR_RATE={b['fzr_rate_within_b_valid']:.6f}",
        f"BOOK TARGET HITS: 123.6={b['hit_1_236']:.6f} 138.2={b['hit_1_382']:.6f} 161.8={b['hit_1_618']:.6f}",
        f"C/A: MEAN={b['mean_c_a']:.6f} MEDIAN={b['median_c_a']:.6f}",
        "",
        "88.2 BOUNDARY TEST (equal-width neighboring bands):",
        f"BELOW 0.850-0.882 N={bd['below_n']} C/B>=.882={bd['below_c_b_ge_0_882']:.6f} HIT1.236={bd['below_hit_1_236']:.6f} HIT1.382={bd['below_hit_1_382']:.6f} HIT1.618={bd['below_hit_1_618']:.6f}",
        f"ABOVE 0.882-0.914 N={bd['above_n']} C/B>=.882={bd['above_c_b_ge_0_882']:.6f} HIT1.236={bd['above_hit_1_236']:.6f} HIT1.382={bd['above_hit_1_382']:.6f} HIT1.618={bd['above_hit_1_618']:.6f}",
        f"DELTA CONFIRMATION BELOW-ABOVE={bd['delta_confirmation_rate']:+.6f}",
        "",
        "TARGET TERMINAL-SWING DENSITY (center window vs adjacent equal-width windows):"
    ]
    for d in density:
        lines.append(f"{d['TARGET']:.3f}: center={d['CENTER_N']} left={d['LEFT_ADJACENT_N']} right={d['RIGHT_ADJACENT_N']} center/adj_mean={d['CENTER_VS_ADJACENT_MEAN_RATIO']:.6f}")
    (a.out/"UT01.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
