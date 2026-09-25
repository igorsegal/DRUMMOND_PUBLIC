#!/usr/bin/env python3
import argparse,csv,json,math
from collections import Counter,defaultdict
from pathlib import Path

OUT_FIELDS=[
 "HORIZON","DIM","KEY","N",
 "MEAN_RET","UP_RATE","MEAN_ABS",
 "BASE_MEAN_RET","DELTA_RET","BASE_UP_RATE","DELTA_UP_RATE",
 "BASE_MEAN_ABS","DELTA_ABS",
 "SYMBOLS","POS_DELTA_SYMBOLS","NEG_DELTA_SYMBOLS","SAME_SIGN_SYMBOLS","SAME_SIGN_SYMBOL_RATE",
 "YEARS","POS_DELTA_YEARS","NEG_DELTA_YEARS","SAME_SIGN_YEARS","SAME_SIGN_YEAR_RATE",
 "ABS_UP_SYMBOLS","ABS_DOWN_SYMBOLS","ABS_SAME_SIGN_SYMBOLS","ABS_SAME_SIGN_SYMBOL_RATE",
 "ABS_UP_YEARS","ABS_DOWN_YEARS","ABS_SAME_SIGN_YEARS","ABS_SAME_SIGN_YEAR_RATE"
]

def read_csv(p):
    with Path(p).open("r",encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f,delimiter=";"):
            yield r

def write_csv(p,fields,rows):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";")
        w.writeheader();w.writerows(rows)

def newa():
    return {"n":0,"sum":0.0,"sum2":0.0,"up":0,"abs":0.0,"min":None,"max":None}

def add(a,n,s,s2,up,ab,minv=None,maxv=None):
    a["n"]+=int(n);a["sum"]+=float(s);a["sum2"]+=float(s2)
    a["up"]+=int(up);a["abs"]+=float(ab)
    if minv not in (None,""):
        v=float(minv);a["min"]=v if a["min"] is None else min(a["min"],v)
    if maxv not in (None,""):
        v=float(maxv);a["max"]=v if a["max"] is None else max(a["max"],v)

def mean(a):
    return a["sum"]/a["n"] if a["n"] else None

def up_rate(a):
    return a["up"]/a["n"] if a["n"] else None

def mean_abs(a):
    return a["abs"]/a["n"] if a["n"] else None

def fmt(v,n=12):
    return "" if v is None else f"{v:.{n}f}"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    js=sorted(a.root.rglob("D30.json"))
    ds=sorted(a.root.rglob("D30.csv"))
    rs=sorted(a.root.rglob("D30R.csv"))
    ys=sorted(a.root.rglob("D30Y.csv"))
    if len(js)!=7 or len(ds)!=7 or len(rs)!=7 or len(ys)!=7:
        raise SystemExit(
          f"D30A expected 7 shards: json={len(js)} dim={len(ds)} rob={len(rs)} year={len(ys)}"
        )

    symbols=events=forward_outcomes=0;skips=Counter()
    horizons=None;features=None
    for p in js:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s.get("status")!="PASS" or int(s.get("errors",0))!=0:
            raise SystemExit(f"bad D30 shard {p}")
        c=s.get("contract",{})
        if c.get("trading_entries_used") or c.get("stops_targets_used") or c.get("pnl_used"):
            raise SystemExit("D30 trading contamination")
        if not c.get("all_features_known_at_event_time") or not c.get("forward_outcomes_only_after_event"):
            raise SystemExit("D30 causality contract violation")
        if c.get("future_filter_used") or c.get("selection_or_optimization") or c.get("lookahead"):
            raise SystemExit("D30 future/optimization violation")
        if c.get("promotion_allowed"):
            raise SystemExit("D30 promotion forbidden")
        symbols+=int(s["symbols"]);events+=int(s["events"]);forward_outcomes+=int(s["forward_outcomes"])
        skips.update({k:int(v) for k,v in s.get("skips",{}).items()})
        hh=tuple(int(x) for x in s["horizons_h1_bars"])
        ff=tuple(s["features"])
        horizons=hh if horizons is None else horizons
        features=ff if features is None else features
        if hh!=horizons or ff!=features:raise SystemExit("D30 shard schema mismatch")

    agg=defaultdict(newa)
    for p in ds:
        for r in read_csv(p):
            k=(int(r["HORIZON"]),r["DIM"],r["KEY"])
            add(agg[k],r["N"],r["SUM_RET"],r["SUM_RET2"],r["UP_N"],r["SUM_ABS"],r["MIN_RET"],r["MAX_RET"])

    rob=defaultdict(lambda:{
      "symbols":0,"pos":0,"neg":0,"zero":0,
      "abs_up":0,"abs_down":0,"abs_zero":0
    })
    for p in rs:
        for r in read_csv(p):
            k=(int(r["HORIZON"]),r["DIM"],r["KEY"])
            z=rob[k]
            z["symbols"]+=int(r["SYMBOLS"])
            z["pos"]+=int(r["POS_DELTA_SYMBOLS"]);z["neg"]+=int(r["NEG_DELTA_SYMBOLS"])
            z["zero"]+=int(r["ZERO_DELTA_SYMBOLS"])
            z["abs_up"]+=int(r["ABS_UP_SYMBOLS"]);z["abs_down"]+=int(r["ABS_DOWN_SYMBOLS"])
            z["abs_zero"]+=int(r["ABS_ZERO_SYMBOLS"])

    years=defaultdict(newa)
    for p in ys:
        for r in read_csv(p):
            k=(int(r["HORIZON"]),r["DIM"],r["KEY"],r["YEAR"])
            add(years[k],r["N"],r["SUM_RET"],r["SUM_RET2"],r["UP_N"],r["SUM_ABS"],r["MIN_RET"],r["MAX_RET"])

    # Across-shard year robustness must be judged only after all shards are merged.
    yrrob=defaultdict(lambda:{
      "years":0,"pos":0,"neg":0,"zero":0,
      "abs_up":0,"abs_down":0,"abs_zero":0
    })
    by_h_year={}
    for (h,dim,key,y),x in years.items():
        if dim=="ALL" and key=="ALL":
            by_h_year[(h,y)]=x

    eps=1e-15
    for (h,dim,key,y),x in years.items():
        if dim=="ALL" or not x["n"]:continue
        b=by_h_year.get((h,y))
        if not b or not b["n"]:continue
        d=mean(x)-mean(b);ad=mean_abs(x)-mean_abs(b)
        z=yrrob[(h,dim,key)];z["years"]+=1
        if d>eps:z["pos"]+=1
        elif d<-eps:z["neg"]+=1
        else:z["zero"]+=1
        if ad>eps:z["abs_up"]+=1
        elif ad<-eps:z["abs_down"]+=1
        else:z["abs_zero"]+=1

    rows=[]
    for (h,dim,key),x in sorted(agg.items()):
        if dim=="ALL":continue
        b=agg.get((h,"ALL","ALL"))
        if not b or not b["n"] or not x["n"]:continue
        mr=mean(x);br=mean(b);du=up_rate(x)-up_rate(b)
        dr=mr-br;da=mean_abs(x)-mean_abs(b)
        sr=rob[(h,dim,key)];yr=yrrob[(h,dim,key)]
        same_sym=sr["pos"] if dr>0 else sr["neg"] if dr<0 else sr["zero"]
        same_yr=yr["pos"] if dr>0 else yr["neg"] if dr<0 else yr["zero"]
        abs_same_sym=sr["abs_up"] if da>0 else sr["abs_down"] if da<0 else sr["abs_zero"]
        abs_same_yr=yr["abs_up"] if da>0 else yr["abs_down"] if da<0 else yr["abs_zero"]
        rows.append({
          "HORIZON":h,"DIM":dim,"KEY":key,"N":x["n"],
          "MEAN_RET":fmt(mr),"UP_RATE":fmt(up_rate(x)),"MEAN_ABS":fmt(mean_abs(x)),
          "BASE_MEAN_RET":fmt(br),"DELTA_RET":fmt(dr),
          "BASE_UP_RATE":fmt(up_rate(b)),"DELTA_UP_RATE":fmt(du),
          "BASE_MEAN_ABS":fmt(mean_abs(b)),"DELTA_ABS":fmt(da),
          "SYMBOLS":sr["symbols"],
          "POS_DELTA_SYMBOLS":sr["pos"],"NEG_DELTA_SYMBOLS":sr["neg"],
          "SAME_SIGN_SYMBOLS":same_sym,
          "SAME_SIGN_SYMBOL_RATE":fmt(same_sym/sr["symbols"] if sr["symbols"] else None),
          "YEARS":yr["years"],"POS_DELTA_YEARS":yr["pos"],"NEG_DELTA_YEARS":yr["neg"],
          "SAME_SIGN_YEARS":same_yr,
          "SAME_SIGN_YEAR_RATE":fmt(same_yr/yr["years"] if yr["years"] else None),
          "ABS_UP_SYMBOLS":sr["abs_up"],"ABS_DOWN_SYMBOLS":sr["abs_down"],
          "ABS_SAME_SIGN_SYMBOLS":abs_same_sym,
          "ABS_SAME_SIGN_SYMBOL_RATE":fmt(abs_same_sym/sr["symbols"] if sr["symbols"] else None),
          "ABS_UP_YEARS":yr["abs_up"],"ABS_DOWN_YEARS":yr["abs_down"],
          "ABS_SAME_SIGN_YEARS":abs_same_yr,
          "ABS_SAME_SIGN_YEAR_RATE":fmt(abs_same_yr/yr["years"] if yr["years"] else None),
        })

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D30A.csv",OUT_FIELDS,rows)

    baselines=[]
    for h in horizons:
        b=agg.get((h,"ALL","ALL"))
        if not b or not b["n"]:continue
        baselines.append({
          "horizon":h,"n":b["n"],"mean_ret":mean(b),
          "up_rate":up_rate(b),"mean_abs":mean_abs(b)
        })

    summary={
      "block":"D30","status":"PASS",
      "symbols":symbols,"events":events,"forward_outcomes":forward_outcomes,
      "skips":dict(skips),"horizons_h1_bars":list(horizons),
      "features":list(features),"baselines":baselines,
      "cells":len(rows),
      "contract":{
        "trading_entries_used":False,"stops_targets_used":False,"pnl_used":False,
        "all_features_known_at_event_time":True,
        "forward_outcomes_only_after_event":True,
        "future_filter_used":False,"selection_or_optimization":False,
        "promotion_allowed":False,"lookahead":False
      },
      "interpretation_limit":"D30 is a predictive-information audit, not a trading strategy. DELTA_RET and DELTA_ABS compare each Drummond condition with the unconditional same-horizon baseline; sign consistency is reported across symbols and years without promoting any cell."
    }
    (a.out/"D30.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
      "D30 DRUMMOND PREDICTIVE VALUE AUDIT",
      "STATUS: PASS",
      f"SYMBOLS: {symbols}",
      f"EVENTS: {events}",
      f"FORWARD_OUTCOMES: {forward_outcomes}",
      "TRADING/PNL: NO",
      "LOOKAHEAD: NO",
      "SELECTION/OPTIMIZATION: NO",
      "PROMOTION: NOT ALLOWED",
      "BASELINES:"
    ]
    for b in baselines:
        lines.append(
          f"  H{b['horizon']}: N={b['n']} MEAN={b['mean_ret']:.8f} "
          f"UP={b['up_rate']:.6f} ABS={b['mean_abs']:.8f}"
        )

    core=("STATE","RAW","HTP_DIR","PL_PUSH","LOSING_PUSH","MATURE",
          "BLOCK_STRONG","DOT_DIR","DOT_DISTANCE_MODE","DOT_IN_PREV_RANGE",
          "ENV_POS","SUPPORT_CLUSTER","RESIST_CLUSTER")
    for dim in core:
        lines.append(dim+":")
        rr=[x for x in rows if x["DIM"]==dim]
        rr.sort(key=lambda z:(int(z["HORIZON"]),z["KEY"]))
        for x in rr:
            lines.append(
              f"  H{x['HORIZON']} {x['KEY']}: N={x['N']} "
              f"DRET={float(x['DELTA_RET']):+.8f} DUP={float(x['DELTA_UP_RATE']):+.6f} "
              f"DABS={float(x['DELTA_ABS']):+.8f} "
              f"SIGN_SYM={x['SAME_SIGN_SYMBOLS']}/{x['SYMBOLS']} "
              f"SIGN_YR={x['SAME_SIGN_YEARS']}/{x['YEARS']}"
            )

    (a.out/"D30.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
