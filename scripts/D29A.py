#!/usr/bin/env python3
import argparse,csv,json
from collections import Counter,defaultdict
from pathlib import Path

OUT_FIELDS=[
 "VARIANT","DIM","KEY","N","SUM_R","MEAN_R","POS_N","POS_RATE",
 "SYMBOLS","POS_SYMBOLS","POS_SYMBOL_RATE",
 "YEARS","POS_YEARS","POS_YEAR_RATE"
]

def read_csv(p):
    with Path(p).open("r",encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f,delimiter=";"):
            yield r

def write_csv(p,fields,rows):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";");w.writeheader();w.writerows(rows)

def newa():
    return {"n":0,"sum":0.0,"pos":0,"min":None,"max":None}

def add(a,n,s,pos=0,minv=None,maxv=None):
    a["n"]+=int(n);a["sum"]+=float(s);a["pos"]+=int(pos)
    if minv not in (None,""):
        v=float(minv);a["min"]=v if a["min"] is None else min(a["min"],v)
    if maxv not in (None,""):
        v=float(maxv);a["max"]=v if a["max"] is None else max(a["max"],v)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    js=sorted(a.root.rglob("D29.json"))
    ds=sorted(a.root.rglob("D29.csv"))
    rs=sorted(a.root.rglob("D29R.csv"))
    ys=sorted(a.root.rglob("D29Y.csv"))
    if len(js)!=7 or len(ds)!=7 or len(rs)!=7 or len(ys)!=7:
        raise SystemExit(
          f"D29A expected 7 shards: json={len(js)} dim={len(ds)} rob={len(rs)} year={len(ys)}"
        )

    symbols=trade_records=0;skips=Counter()
    for p in js:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s.get("status")!="PASS" or int(s.get("errors",0))!=0 or int(s.get("reconstruction_errors",0))!=0:
            raise SystemExit(f"bad D29 shard {p}")
        c=s.get("contract",{})
        if c.get("d27_trading_logic_changed"):
            raise SystemExit("D29 changed D27 trading logic")
        if not c.get("all_diagnostic_dimensions_known_at_entry"):
            raise SystemExit("D29 contains non-causal diagnostic dimensions")
        if c.get("selection_or_optimization") or c.get("outcome_based_filtering"):
            raise SystemExit("D29 selection/optimization contamination")
        if not c.get("diagnostic_only") or c.get("lookahead"):
            raise SystemExit("D29 diagnostic/causal contract violation")
        if c.get("promotion_allowed"):
            raise SystemExit("D29 promotion must remain forbidden")
        symbols+=int(s["symbols"]);trade_records+=int(s["trade_records"])
        skips.update({k:int(v) for k,v in s.get("skips",{}).items()})

    dims=defaultdict(newa)
    for p in ds:
        for r in read_csv(p):
            add(dims[(r["VARIANT"],r["DIM"],r["KEY"])],
                r["N"],r["SUM_R"],r["POS_N"],r["MIN_R"],r["MAX_R"])

    rob=defaultdict(lambda:{"symbols":0,"pos_symbols":0})
    for p in rs:
        for r in read_csv(p):
            k=(r["VARIANT"],r["DIM"],r["KEY"])
            rob[k]["symbols"]+=int(r["SYMBOLS"])
            rob[k]["pos_symbols"]+=int(r["POS_SYMBOLS"])

    years=defaultdict(newa)
    for p in ys:
        for r in read_csv(p):
            k=(r["VARIANT"],r["DIM"],r["KEY"],r["YEAR"])
            add(years[k],r["N"],r["SUM_R"],r["POS_N"])

    yrrob=defaultdict(lambda:{"years":0,"pos_years":0})
    for k,x in years.items():
        base=k[:3];z=yrrob[base];z["years"]+=1
        if x["n"] and x["sum"]/x["n"]>0:z["pos_years"]+=1

    outrows=[]
    for base,t in sorted(dims.items()):
        v,d,k=base;r=rob[base];y=yrrob[base]
        outrows.append({
          "VARIANT":v,"DIM":d,"KEY":k,
          "N":t["n"],"SUM_R":f"{t['sum']:.10f}",
          "MEAN_R":f"{t['sum']/t['n']:.10f}" if t["n"] else "",
          "POS_N":t["pos"],"POS_RATE":f"{t['pos']/t['n']:.10f}" if t["n"] else "",
          "SYMBOLS":r["symbols"],"POS_SYMBOLS":r["pos_symbols"],
          "POS_SYMBOL_RATE":f"{r['pos_symbols']/r['symbols']:.10f}" if r["symbols"] else "",
          "YEARS":y["years"],"POS_YEARS":y["pos_years"],
          "POS_YEAR_RATE":f"{y['pos_years']/y['years']:.10f}" if y["years"] else ""
        })

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D29A.csv",OUT_FIELDS,outrows)

    variants=sorted({x["VARIANT"] for x in outrows})
    variant_summary=[]
    for v in variants:
        q=[x for x in outrows if x["VARIANT"]==v and x["DIM"]=="ALL" and x["KEY"]=="ALL"]
        if len(q)!=1:raise SystemExit(f"D29A missing ALL row for {v}")
        x=q[0]
        variant_summary.append({
          "variant":v,"n":int(x["N"]),"mean_r":float(x["MEAN_R"]),
          "positive_symbols":int(x["POS_SYMBOLS"]),"symbols":int(x["SYMBOLS"]),
          "positive_years":int(x["POS_YEARS"]),"years":int(x["YEARS"])
        })

    focus={}
    for dim in ("TARGET_R","STOP_H1","TARGET_H1","ENTRY_GAP_H1","EXTENSION","TARGET_R_X_STOP_H1","SIDE"):
        focus[dim]=[
          {
            "variant":x["VARIANT"],"key":x["KEY"],"n":int(x["N"]),
            "mean_r":float(x["MEAN_R"]),"sum_r":float(x["SUM_R"]),
            "positive_symbols":int(x["POS_SYMBOLS"]),"symbols":int(x["SYMBOLS"]),
            "positive_years":int(x["POS_YEARS"]),"years":int(x["YEARS"])
          }
          for x in outrows if x["DIM"]==dim
        ]

    summary={
      "block":"D29","status":"PASS","source":"D27",
      "symbols":symbols,"trade_records":trade_records,"skips":dict(skips),
      "variant_summary":variant_summary,"focus":focus,
      "contract":{
        "d27_trading_logic_changed":False,
        "all_diagnostic_dimensions_known_at_entry":True,
        "selection_or_optimization":False,
        "outcome_based_filtering":False,
        "diagnostic_only":True,
        "lookahead":False,
        "promotion_allowed":False
      },
      "interpretation_limit":"D29 is post-hoc attribution using only information already known at each D27 entry. Positive cells, if any, remain hypotheses and are not trading rules until frozen and tested separately."
    }
    (a.out/"D29.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
      "D29 CAUSAL ENTRY GEOMETRY XRAY",
      "STATUS: PASS",
      f"SYMBOLS: {symbols}",
      f"TRADE_RECORDS: {trade_records}",
      "D27 TRADING LOGIC CHANGED: NO",
      "ALL DIMENSIONS KNOWN AT ENTRY: YES",
      "SELECTION/OPTIMIZATION: NO",
      "LOOKAHEAD: NO",
      "PROMOTION: NOT ALLOWED"
    ]
    for x in variant_summary:
        lines.append(
          f"{x['variant']}: N={x['n']} MEAN_R={x['mean_r']:.10f} "
          f"SYMBOLS+={x['positive_symbols']}/{x['symbols']} "
          f"YEARS+={x['positive_years']}/{x['years']}"
        )
    for dim in ("TARGET_R","STOP_H1","TARGET_H1","ENTRY_GAP_H1","EXTENSION"):
        lines.append(dim+":")
        rr=sorted(focus[dim],key=lambda z:(z["variant"],z["key"]))
        for x in rr:
            lines.append(
              f"  {x['variant']} {x['key']}: N={x['n']} "
              f"MEAN_R={x['mean_r']:.10f} SUM_R={x['sum_r']:.4f} "
              f"SYMBOLS+={x['positive_symbols']}/{x['symbols']} "
              f"YEARS+={x['positive_years']}/{x['years']}"
            )
    (a.out/"D29.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
