#!/usr/bin/env python3
import argparse,csv,json
from collections import Counter,defaultdict
from pathlib import Path

FIELDS=[
 "HORIZON",
 "STRONG_BELOW_N","STRONG_BELOW_MEAN","STRONG_BELOW_UP",
 "STRONG_ABOVE_N","STRONG_ABOVE_MEAN","STRONG_ABOVE_UP",
 "WEAK_BELOW_N","WEAK_BELOW_MEAN","WEAK_BELOW_UP",
 "WEAK_ABOVE_N","WEAK_ABOVE_MEAN","WEAK_ABOVE_UP",
 "STRONG_EDGE","WEAK_EDGE","INTERACTION",
 "STRONG_HIT_EDGE","WEAK_HIT_EDGE","HIT_INTERACTION",
 "SYMBOLS","POS_INTERACTION_SYMBOLS","NEG_INTERACTION_SYMBOLS","POS_INTERACTION_SYMBOL_RATE",
 "YEARS","POS_INTERACTION_YEARS","NEG_INTERACTION_YEARS","POS_INTERACTION_YEAR_RATE"
]

GROUPS=("STRONG_BELOW_EB","STRONG_ABOVE_ET","WEAK_BELOW_EB","WEAK_ABOVE_ET")

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

def upr(a):
    return a["up"]/a["n"] if a["n"] else None

def edge(below,above):
    if not below["n"] or not above["n"]:return None
    return 0.5*(mean(below)-mean(above))

def hit_edge(below,above):
    if not below["n"] or not above["n"]:return None
    return 0.5*(upr(below)+(1-upr(above)))-0.5

def interaction(groupmap):
    se=edge(groupmap["STRONG_BELOW_EB"],groupmap["STRONG_ABOVE_ET"])
    we=edge(groupmap["WEAK_BELOW_EB"],groupmap["WEAK_ABOVE_ET"])
    if se is None or we is None:return None
    return se-we

def hit_interaction(groupmap):
    se=hit_edge(groupmap["STRONG_BELOW_EB"],groupmap["STRONG_ABOVE_ET"])
    we=hit_edge(groupmap["WEAK_BELOW_EB"],groupmap["WEAK_ABOVE_ET"])
    if se is None or we is None:return None
    return se-we

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

    js=sorted(a.root.rglob("D32.json"))
    cs=sorted(a.root.rglob("D32.csv"))
    if len(js)!=7 or len(cs)!=7:
        raise SystemExit(f"D32A expected 7 shards: json={len(js)} csv={len(cs)}")

    symbols=events=eligible=forward=0;skips=Counter();horizons=None
    for p in js:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s.get("status")!="PASS" or int(s.get("errors",0))!=0:
            raise SystemExit(f"bad D32 shard {p}")
        c=s.get("contract",{})
        if not c.get("single_hypothesis_frozen_before_run") or not c.get("groups_frozen_before_run"):
            raise SystemExit("D32 frozen hypothesis contract violation")
        if not c.get("horizons_frozen_before_run"):
            raise SystemExit("D32 frozen horizon contract violation")
        if c.get("trading_entries_used") or c.get("stops_targets_used") or c.get("pnl_used"):
            raise SystemExit("D32 trading contamination")
        if c.get("future_filter_used") or c.get("selection_or_optimization") or c.get("lookahead"):
            raise SystemExit("D32 causality/optimization violation")
        if c.get("promotion_allowed"):
            raise SystemExit("D32 promotion forbidden")
        symbols+=int(s["symbols"]);events+=int(s["events"])
        eligible+=int(s["eligible_events"]);forward+=int(s["forward_outcomes"])
        skips.update({k:int(v) for k,v in s.get("skips",{}).items()})
        hh=tuple(int(x) for x in s["horizons_h1_bars"])
        if horizons is None:horizons=hh
        elif horizons!=hh:raise SystemExit("D32 horizon mismatch")

    overall=defaultdict(newa)
    bysym=defaultdict(newa)
    byyear=defaultdict(newa)
    for p in cs:
        for r in read_csv(p):
            h=int(r["HORIZON"]);g=r["GROUP"];sym=r["SYMBOL"];year=r["YEAR"]
            add(overall[(h,g)],r)
            add(bysym[(h,sym,g)],r)
            add(byyear[(h,year,g)],r)

    rows=[];results=[]
    for h in horizons:
        gm={g:overall[(h,g)] for g in GROUPS}
        se=edge(gm["STRONG_BELOW_EB"],gm["STRONG_ABOVE_ET"])
        we=edge(gm["WEAK_BELOW_EB"],gm["WEAK_ABOVE_ET"])
        inter=None if se is None or we is None else se-we
        she=hit_edge(gm["STRONG_BELOW_EB"],gm["STRONG_ABOVE_ET"])
        whe=hit_edge(gm["WEAK_BELOW_EB"],gm["WEAK_ABOVE_ET"])
        hi=None if she is None or whe is None else she-whe

        syms={k[1] for k in bysym if k[0]==h}
        ps=ns=vs=0
        for sym in syms:
            sgm={g:bysym.get((h,sym,g),newa()) for g in GROUPS}
            x=interaction(sgm)
            if x is None:continue
            vs+=1
            if x>0:ps+=1
            elif x<0:ns+=1

        yrs={k[1] for k in byyear if k[0]==h}
        py=ny=vy=0
        for y in yrs:
            ygm={g:byyear.get((h,y,g),newa()) for g in GROUPS}
            x=interaction(ygm)
            if x is None:continue
            vy+=1
            if x>0:py+=1
            elif x<0:ny+=1

        row={
          "HORIZON":h,
          "STRONG_BELOW_N":gm["STRONG_BELOW_EB"]["n"],"STRONG_BELOW_MEAN":fmt(mean(gm["STRONG_BELOW_EB"])),"STRONG_BELOW_UP":fmt(upr(gm["STRONG_BELOW_EB"])),
          "STRONG_ABOVE_N":gm["STRONG_ABOVE_ET"]["n"],"STRONG_ABOVE_MEAN":fmt(mean(gm["STRONG_ABOVE_ET"])),"STRONG_ABOVE_UP":fmt(upr(gm["STRONG_ABOVE_ET"])),
          "WEAK_BELOW_N":gm["WEAK_BELOW_EB"]["n"],"WEAK_BELOW_MEAN":fmt(mean(gm["WEAK_BELOW_EB"])),"WEAK_BELOW_UP":fmt(upr(gm["WEAK_BELOW_EB"])),
          "WEAK_ABOVE_N":gm["WEAK_ABOVE_ET"]["n"],"WEAK_ABOVE_MEAN":fmt(mean(gm["WEAK_ABOVE_ET"])),"WEAK_ABOVE_UP":fmt(upr(gm["WEAK_ABOVE_ET"])),
          "STRONG_EDGE":fmt(se),"WEAK_EDGE":fmt(we),"INTERACTION":fmt(inter),
          "STRONG_HIT_EDGE":fmt(she),"WEAK_HIT_EDGE":fmt(whe),"HIT_INTERACTION":fmt(hi),
          "SYMBOLS":vs,"POS_INTERACTION_SYMBOLS":ps,"NEG_INTERACTION_SYMBOLS":ns,
          "POS_INTERACTION_SYMBOL_RATE":fmt(ps/vs if vs else None),
          "YEARS":vy,"POS_INTERACTION_YEARS":py,"NEG_INTERACTION_YEARS":ny,
          "POS_INTERACTION_YEAR_RATE":fmt(py/vy if vy else None)
        }
        rows.append(row)
        results.append({
          "horizon":h,
          "strong_edge":se,"weak_edge":we,"interaction":inter,
          "strong_hit_edge":she,"weak_hit_edge":whe,"hit_interaction":hi,
          "symbols":vs,"positive_interaction_symbols":ps,
          "years":vy,"positive_interaction_years":py,
          "counts":{g:gm[g]["n"] for g in GROUPS}
        })

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D32A.csv",rows)

    summary={
      "block":"D32","status":"PASS",
      "symbols":symbols,"events":events,"eligible_events":eligible,"forward_outcomes":forward,
      "skips":dict(skips),"horizons_h1_bars":list(horizons),
      "hypothesis":"Strong Block amplifies Envelope mean reversion directional edge",
      "results":results,
      "contract":{
        "single_hypothesis_frozen_before_run":True,
        "groups_frozen_before_run":True,
        "horizons_frozen_before_run":True,
        "trading_entries_used":False,
        "stops_targets_used":False,
        "pnl_used":False,
        "future_filter_used":False,
        "selection_or_optimization":False,
        "promotion_allowed":False,
        "lookahead":False
      },
      "interpretation_limit":"D32 uses the same historical universe that generated D30/D31. Positive interaction is robustness evidence, not independent unseen validation."
    }
    (a.out/"D32.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
      "D32 FROZEN STRONG-BLOCK x ENVELOPE INTERSECTION",
      "STATUS: PASS",
      f"SYMBOLS: {symbols}",
      f"EVENTS: {events}",
      f"ELIGIBLE_EVENTS: {eligible}",
      f"FORWARD_OUTCOMES: {forward}",
      "TRADING/PNL: NO",
      "LOOKAHEAD: NO",
      "SELECTION/OPTIMIZATION: NO",
      "PROMOTION: NOT ALLOWED"
    ]
    for x in results:
        lines.append(
          f"H{x['horizon']}: STRONG_EDGE={x['strong_edge']:+.8f} "
          f"WEAK_EDGE={x['weak_edge']:+.8f} INTERACTION={x['interaction']:+.8f} "
          f"HIT_INT={x['hit_interaction']:+.6f} "
          f"SYMS+={x['positive_interaction_symbols']}/{x['symbols']} "
          f"YEARS+={x['positive_interaction_years']}/{x['years']}"
        )
    (a.out/"D32.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
