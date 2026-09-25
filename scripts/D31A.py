#!/usr/bin/env python3
import argparse,csv,json
from collections import Counter,defaultdict
from pathlib import Path

FIELDS=[
 "HYPOTHESIS","HORIZON",
 "GROUP_A","N_A","MEAN_RET_A","MEAN_ABS_A","UP_RATE_A",
 "GROUP_B","N_B","MEAN_RET_B","MEAN_ABS_B","UP_RATE_B",
 "EFFECT","HIT_EDGE","UP_RATE_DIFF",
 "SYMBOLS","POS_SYMBOLS","NEG_SYMBOLS","POS_SYMBOL_RATE",
 "YEARS","POS_YEARS","NEG_YEARS","POS_YEAR_RATE"
]

GROUPS={
 "CONTRARIAN_STATE":("DOWN","UP"),
 "ENVELOPE_MEAN_REVERSION":("BELOW_EB","ABOVE_ET"),
 "STRONG_BLOCK_VOLATILITY":("STRONG","WEAK"),
}

def read_csv(p):
    with Path(p).open("r",encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f,delimiter=";"):
            yield r

def newa():
    return {"n":0,"sum":0.0,"abs":0.0,"up":0}

def add(a,r):
    a["n"]+=int(r["N"])
    a["sum"]+=float(r["SUM_RET"])
    a["abs"]+=float(r["SUM_ABS"])
    a["up"]+=int(r["UP_N"])

def mean(a):
    return a["sum"]/a["n"] if a["n"] else None

def mean_abs(a):
    return a["abs"]/a["n"] if a["n"] else None

def up_rate(a):
    return a["up"]/a["n"] if a["n"] else None

def effect(hyp,a,b):
    if not a["n"] or not b["n"]:return None
    if hyp=="STRONG_BLOCK_VOLATILITY":
        return mean_abs(a)-mean_abs(b)
    return 0.5*(mean(a)-mean(b))

def hit_edge(hyp,a,b):
    if hyp=="STRONG_BLOCK_VOLATILITY" or not a["n"] or not b["n"]:
        return None
    # Group A is the group expected UP; group B is expected DOWN.
    hit=0.5*(up_rate(a)+(1.0-up_rate(b)))
    return hit-0.5

def up_diff(a,b):
    if not a["n"] or not b["n"]:return None
    return up_rate(a)-up_rate(b)

def fmt(v,n=12):
    return "" if v is None else f"{v:.{n}f}"

def write_csv(p,rows):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";")
        w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    js=sorted(a.root.rglob("D31.json"))
    cs=sorted(a.root.rglob("D31.csv"))
    if len(js)!=7 or len(cs)!=7:
        raise SystemExit(f"D31A expected 7 shards: json={len(js)} csv={len(cs)}")

    symbols=events=forward_outcomes=0;skips=Counter()
    horizons=None
    for p in js:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s.get("status")!="PASS" or int(s.get("errors",0))!=0:
            raise SystemExit(f"bad D31 shard {p}")
        c=s.get("contract",{})
        if not c.get("hypotheses_frozen_before_run") or not c.get("all_three_tested_together"):
            raise SystemExit("D31 hypothesis contract violation")
        if not c.get("horizons_frozen_before_run"):
            raise SystemExit("D31 horizon contract violation")
        if c.get("trading_entries_used") or c.get("stops_targets_used") or c.get("pnl_used"):
            raise SystemExit("D31 trading contamination")
        if c.get("future_filter_used") or c.get("selection_or_optimization") or c.get("lookahead"):
            raise SystemExit("D31 causality/optimization violation")
        if c.get("promotion_allowed"):
            raise SystemExit("D31 promotion forbidden")
        symbols+=int(s["symbols"]);events+=int(s["events"]);forward_outcomes+=int(s["forward_outcomes"])
        skips.update({k:int(v) for k,v in s.get("skips",{}).items()})
        hh=tuple(int(x) for x in s["horizons_h1_bars"])
        if horizons is None:horizons=hh
        elif horizons!=hh:raise SystemExit("D31 horizon mismatch")

    overall=defaultdict(newa)
    bysym=defaultdict(newa)
    byyear=defaultdict(newa)

    for p in cs:
        for r in read_csv(p):
            hyp=r["HYPOTHESIS"];h=int(r["HORIZON"]);g=r["GROUP"]
            sym=r["SYMBOL"];year=r["YEAR"]
            add(overall[(hyp,h,g)],r)
            add(bysym[(hyp,h,sym,g)],r)
            add(byyear[(hyp,h,year,g)],r)

    rows=[];summary_rows=[]
    for hyp,(ga,gb) in GROUPS.items():
        for h in horizons:
            A=overall[(hyp,h,ga)];B=overall[(hyp,h,gb)]
            ef=effect(hyp,A,B);he=hit_edge(hyp,A,B);ud=up_diff(A,B)

            syms=set(k[2] for k in bysym if k[0]==hyp and k[1]==h)
            pos_s=neg_s=0;valid_s=0
            for sym in syms:
                a1=bysym.get((hyp,h,sym,ga));b1=bysym.get((hyp,h,sym,gb))
                if not a1 or not b1 or not a1["n"] or not b1["n"]:continue
                e=effect(hyp,a1,b1)
                if e is None:continue
                valid_s+=1
                if e>0:pos_s+=1
                elif e<0:neg_s+=1

            yrs=set(k[2] for k in byyear if k[0]==hyp and k[1]==h)
            pos_y=neg_y=0;valid_y=0
            for y in yrs:
                a1=byyear.get((hyp,h,y,ga));b1=byyear.get((hyp,h,y,gb))
                if not a1 or not b1 or not a1["n"] or not b1["n"]:continue
                e=effect(hyp,a1,b1)
                if e is None:continue
                valid_y+=1
                if e>0:pos_y+=1
                elif e<0:neg_y+=1

            row={
              "HYPOTHESIS":hyp,"HORIZON":h,
              "GROUP_A":ga,"N_A":A["n"],"MEAN_RET_A":fmt(mean(A)),
              "MEAN_ABS_A":fmt(mean_abs(A)),"UP_RATE_A":fmt(up_rate(A)),
              "GROUP_B":gb,"N_B":B["n"],"MEAN_RET_B":fmt(mean(B)),
              "MEAN_ABS_B":fmt(mean_abs(B)),"UP_RATE_B":fmt(up_rate(B)),
              "EFFECT":fmt(ef),"HIT_EDGE":fmt(he),"UP_RATE_DIFF":fmt(ud),
              "SYMBOLS":valid_s,"POS_SYMBOLS":pos_s,"NEG_SYMBOLS":neg_s,
              "POS_SYMBOL_RATE":fmt(pos_s/valid_s if valid_s else None),
              "YEARS":valid_y,"POS_YEARS":pos_y,"NEG_YEARS":neg_y,
              "POS_YEAR_RATE":fmt(pos_y/valid_y if valid_y else None)
            }
            rows.append(row)
            summary_rows.append({
              "hypothesis":hyp,"horizon":h,"effect":ef,"hit_edge":he,"up_rate_diff":ud,
              "symbols":valid_s,"positive_symbols":pos_s,
              "years":valid_y,"positive_years":pos_y,
              "n_a":A["n"],"n_b":B["n"]
            })

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D31A.csv",rows)

    out={
      "block":"D31","status":"PASS",
      "symbols":symbols,"events":events,"forward_outcomes":forward_outcomes,
      "skips":dict(skips),"horizons_h1_bars":list(horizons),
      "results":summary_rows,
      "contract":{
        "hypotheses_frozen_before_run":True,
        "all_three_tested_together":True,
        "trading_entries_used":False,
        "stops_targets_used":False,
        "pnl_used":False,
        "future_filter_used":False,
        "selection_or_optimization":False,
        "promotion_allowed":False,
        "lookahead":False
      },
      "interpretation_limit":"D31 uses the same historical universe that produced D30. Positive effects are robustness evidence, not independent unseen validation."
    }
    (a.out/"D31.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
      "D31 FROZEN THREE-HYPOTHESIS STRESS TEST",
      "STATUS: PASS",
      f"SYMBOLS: {symbols}",
      f"EVENTS: {events}",
      f"FORWARD_OUTCOMES: {forward_outcomes}",
      "TRADING/PNL: NO",
      "LOOKAHEAD: NO",
      "SELECTION/OPTIMIZATION: NO",
      "PROMOTION: NOT ALLOWED"
    ]
    for hyp in GROUPS:
        lines.append(hyp+":")
        for x in [z for z in summary_rows if z["hypothesis"]==hyp]:
            he="NA" if x["hit_edge"] is None else f"{x['hit_edge']:+.6f}"
            lines.append(
              f"  H{x['horizon']}: EFFECT={x['effect']:+.8f} HIT_EDGE={he} "
              f"SYMS+={x['positive_symbols']}/{x['symbols']} "
              f"YEARS+={x['positive_years']}/{x['years']} "
              f"N={x['n_a']}+{x['n_b']}"
            )
    (a.out/"D31.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
