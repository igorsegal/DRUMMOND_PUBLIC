#!/usr/bin/env python3
"""
UT02 — "Smart Trading" wave-4 50% claim audit on XAUUSD M1.

Source-derived claims under test:
- wave 4 must not be larger than 50% of wave C; crossing 50% cancels wave 4.
- wave 4 should not enter the price zone of wave A.

We keep the same frozen objective swing proxy as UT01 and ask a predictive,
falsifiable question: do completed 4th-wave retracements at/below 50%,
especially with no A-zone overlap, lead to a new 5th-wave extreme more often
than nearby thresholds?

No trading/PnL. No optimization.
"""
import argparse,csv,json,math,statistics
from pathlib import Path
from drummond_replay01 import read_xfbar
from UT01 import strict_11bar_candidates, alternating_swings

THRESHOLDS=[0.40,0.45,0.50,0.55,0.60,0.70]
BANDS=[
    (".350-.400",0.35,0.40),
    (".400-.450",0.40,0.45),
    (".450-.500",0.45,0.50),
    (".500-.550",0.50,0.55),
    (".550-.600",0.55,0.60),
    (".600-.700",0.60,0.70),
    (".700-1.000",0.70,1.00),
    ("1.000+",1.00,None),
]

def build_patterns(piv):
    out=[]
    # p0->p1=A, p1->p2=B, p2->p3=C, p3->p4=4, p4->p5=5
    for k in range(len(piv)-5):
        p0,p1,p2,p3,p4,p5=piv[k:k+6]
        A=abs(p1[3]-p0[3]);B=abs(p2[3]-p1[3]);C=abs(p3[3]-p2[3])
        W4=abs(p4[3]-p3[3]);W5=abs(p5[3]-p4[3])
        if min(A,B,C,W4,W5)<=0: continue
        d=1 if p1[3]>p0[3] else -1
        # alternating direction consistency
        dirs=[]
        pp=[p0,p1,p2,p3,p4,p5]
        for i in range(5):
            dirs.append(1 if pp[i+1][3]>pp[i][3] else -1)
        if dirs != [d,-d,d,-d,d]: continue

        b_a=B/A
        c_b=C/B
        w4_c=W4/C
        # source: wave4 should stay out of A zone.
        no_a_overlap = (p4[3] > p1[3]) if d>0 else (p4[3] < p1[3])
        # fifth-wave success: fifth wave creates a new trend extreme beyond C.
        new_extreme = (p5[3] > p3[3]) if d>0 else (p5[3] < p3[3])
        # How far fifth wave travels relative to C and A.
        out.append({
            "b_a":b_a,"c_b":c_b,"w4_c":w4_c,
            "no_a_overlap":no_a_overlap,"new_extreme":new_extreme,
            "w5_c":W5/C,"w5_a":W5/A,
            "dir":d
        })
    return out

def rate(rr,key):
    return sum(bool(r[key]) for r in rr)/len(rr) if rr else None

def mean(rr,key):
    return statistics.fmean(r[key] for r in rr) if rr else None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--bin",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    hdr,bars=read_xfbar(a.bin)
    if hdr["symbol"]!="XAUUSD" or hdr["period_seconds"]!=60:
        raise SystemExit("UT02 requires XAUUSD M1")

    cands=strict_11bar_candidates(bars)
    piv,_,_=alternating_swings(cands)
    pats=build_patterns(piv)
    if not pats:raise SystemExit("no five-wave patterns")

    # Primary book context uses the UT01 FZR geometry.
    book=[r for r in pats if r["b_a"]<=0.882 and r["c_b"]>=0.882]

    rows=[]
    for scope,rr in (("ALL_GENERIC",pats),("BOOK_FZR_882",book)):
        base=rate(rr,"new_extreme")
        for t in THRESHOLDS:
            valid=[r for r in rr if r["w4_c"]<=t]
            valid_noov=[r for r in valid if r["no_a_overlap"]]
            rows.append({
                "SCOPE":scope,"W4_MAX_C":t,
                "N_SCOPE":len(rr),"BASE_NEW_EXTREME_RATE":base,
                "N_W4_VALID":len(valid),
                "W4_VALID_RATE":len(valid)/len(rr) if rr else None,
                "NEW_EXTREME_RATE":rate(valid,"new_extreme"),
                "DELTA_VS_BASE":(rate(valid,"new_extreme")-base) if valid and base is not None else None,
                "N_W4_VALID_NO_A_OVERLAP":len(valid_noov),
                "NEW_EXTREME_RATE_NO_A_OVERLAP":rate(valid_noov,"new_extreme"),
                "MEAN_W5_C_NO_A_OVERLAP":mean(valid_noov,"w5_c"),
                "MEAN_W5_A_NO_A_OVERLAP":mean(valid_noov,"w5_a"),
            })

    bins=[]
    for scope,rr in (("ALL_GENERIC",pats),("BOOK_FZR_882",book)):
        for name,lo,hi in BANDS:
            bb=[r for r in rr if r["w4_c"]>=lo and (hi is None or r["w4_c"]<hi)]
            if not bb: continue
            bins.append({
                "SCOPE":scope,"W4_C_BIN":name,"N":len(bb),
                "NEW_EXTREME_RATE":rate(bb,"new_extreme"),
                "NO_A_OVERLAP_RATE":rate(bb,"no_a_overlap"),
                "NEW_EXTREME_RATE_IF_NO_A_OVERLAP":rate([r for r in bb if r["no_a_overlap"]],"new_extreme"),
                "MEAN_W5_C":mean(bb,"w5_c"),
            })

    # Symmetric boundary around 0.50: equal-width 0.45-0.50 vs 0.50-0.55.
    boundary={}
    for scope,rr in (("ALL_GENERIC",pats),("BOOK_FZR_882",book)):
        below=[r for r in rr if 0.45<=r["w4_c"]<0.50]
        above=[r for r in rr if 0.50<=r["w4_c"]<0.55]
        rb=rate(below,"new_extreme");ra=rate(above,"new_extreme")
        nrb=rate([r for r in below if r["no_a_overlap"]],"new_extreme")
        nra=rate([r for r in above if r["no_a_overlap"]],"new_extreme")
        boundary[scope]={
            "below_n":len(below),"above_n":len(above),
            "below_new_extreme_rate":rb,"above_new_extreme_rate":ra,
            "delta_below_minus_above":(rb-ra if rb is not None and ra is not None else None),
            "below_no_overlap_new_extreme_rate":nrb,
            "above_no_overlap_new_extreme_rate":nra,
            "delta_no_overlap":(nrb-nra if nrb is not None and nra is not None else None),
        }

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";")
            w.writeheader();w.writerows(data)
    write("UT02_THRESHOLDS.csv",rows)
    write("UT02_W4_BINS.csv",bins)

    summary={
        "block":"UT02","status":"PASS","symbol":"XAUUSD","timeframe":"M1",
        "bars":len(bars),"five_wave_patterns":len(pats),"book_fzr_patterns":len(book),
        "boundary_0_50":boundary,
        "contract":{
            "trading_or_pnl":False,"parameter_optimization":False,
            "same_swing_proxy_as_ut01":True,
            "book_claims_tested":["wave4/C <= 0.50","wave4 must not overlap A zone"],
            "outcome":"wave5 makes a new price extreme beyond wave C"
        }
    }
    (a.out/"UT02.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
        "SMART TRADING UT02 — WAVE-4 50% CLAIM AUDIT",
        "STATUS: PASS",
        "SYMBOL: XAUUSD M1",
        f"BARS: {len(bars)}",
        f"FIVE_WAVE_PATTERNS: {len(pats)}",
        f"BOOK_FZR_882_PATTERNS: {len(book)}",
        "TRADING/PNL: NO",
        "OPTIMIZATION: NO",
        ""
    ]
    for scope in ("ALL_GENERIC","BOOK_FZR_882"):
        b=boundary[scope]
        lines += [
            scope+" 0.50 BOUNDARY:",
            f" BELOW .45-.50 N={b['below_n']} NEW_EXTREME={b['below_new_extreme_rate']:.6f} NO_OVERLAP_NEW_EXTREME={b['below_no_overlap_new_extreme_rate']:.6f}",
            f" ABOVE .50-.55 N={b['above_n']} NEW_EXTREME={b['above_new_extreme_rate']:.6f} NO_OVERLAP_NEW_EXTREME={b['above_no_overlap_new_extreme_rate']:.6f}",
            f" DELTA BELOW-ABOVE={b['delta_below_minus_above']:+.6f} DELTA_NO_OVERLAP={b['delta_no_overlap']:+.6f}",
            ""
        ]
    (a.out/"UT02.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
