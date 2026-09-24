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

def newa():return {"n":0,"sum":0.0,"pos":0,"min":None,"max":None}

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

    js=sorted(a.root.rglob("D26.json"))
    ds=sorted(a.root.rglob("D26.csv"))
    rs=sorted(a.root.rglob("D26R.csv"))
    ys=sorted(a.root.rglob("D26Y.csv"))
    cs=sorted(a.root.rglob("D26C.csv"))
    if len(js)!=7 or len(ds)!=7:
        raise SystemExit(f"D26A expected 7 base shards, got json={len(js)} dim={len(ds)}")
    compact=(len(rs)==7 and len(ys)==7)
    legacy=(len(cs)==7)
    if not compact and not legacy:
        raise SystemExit(f"D26A needs compact R/Y or legacy cells: rob={len(rs)} year={len(ys)} cells={len(cs)}")

    symbols=trade_records=0;skips=Counter();states=Counter();trans=Counter()
    for p in js:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s.get("status")!="PASS" or int(s.get("errors",0))!=0:raise SystemExit(f"bad D26 shard {p}")
        c=s.get("contract",{})
        if c.get("changes_to_trading_logic") or c.get("selection_or_optimization") or c.get("outcome_based_filtering"):
            raise SystemExit("D26 xray contract violation")
        symbols+=int(s["symbols"]);trade_records+=int(s["trade_records"])
        skips.update({k:int(v) for k,v in s.get("skips",{}).items()})
        states.update({k:int(v) for k,v in s.get("state_counts",{}).items()})
        trans.update({k:int(v) for k,v in s.get("state_transitions",{}).items()})

    dims=defaultdict(newa)
    for p in ds:
        for r in read_csv(p):
            add(dims[(r["VARIANT"],r["DIM"],r["KEY"])],r["N"],r["SUM_R"],r["POS_N"],r["MIN_R"],r["MAX_R"])

    rob=defaultdict(lambda:{"symbols":0,"pos_symbols":0})
    yrrob=defaultdict(lambda:{"years":0,"pos_years":0})

    if compact:
        # Symbol robustness is directly summable because every symbol belongs to one shard only.
        for p in rs:
            for r in read_csv(p):
                k=(r["VARIANT"],r["DIM"],r["KEY"])
                rob[k]["symbols"]+=int(r["SYMBOLS"])
                rob[k]["pos_symbols"]+=int(r["POS_SYMBOLS"])

        # Year totals must first be merged across all shards, then judged.
        years=defaultdict(newa)
        for p in ys:
            for r in read_csv(p):
                k=(r["VARIANT"],r["DIM"],r["KEY"],r["YEAR"])
                add(years[k],r["N"],r["SUM_R"],r["POS_N"])
        for k,x in years.items():
            base=k[:3];z=yrrob[base];z["years"]+=1
            if x["n"] and x["sum"]/x["n"]>0:z["pos_years"]+=1
    else:
        # Legacy D26C fallback. Scan one diagnostic dimension at a time so
        # memory is bounded even for ~1.8M cell rows.
        specs={
          "ALL":lambda r:"ALL",
          "ENTRY_STATE":lambda r:r["ENTRY_STATE"],
          "EXIT_STATE":lambda r:r["EXIT_STATE"],
          "ENTRY_EXIT":lambda r:r["ENTRY_STATE"]+"->"+r["EXIT_STATE"],
          "SIDE":lambda r:r["SIDE"],
          "ENTRY_KIND":lambda r:r["ENTRY_KIND"],
          "PYRAMIDED":lambda r:r["PYRAMIDED"],
          "ENTRY_SIDE":lambda r:r["ENTRY_STATE"]+"|"+r["SIDE"],
          "ENTRY_KIND_SIDE":lambda r:r["ENTRY_KIND"]+"|"+r["SIDE"],
          "ENTRY_PYR":lambda r:r["ENTRY_STATE"]+"|"+r["PYRAMIDED"],
          "SYMBOL":lambda r:r["SYMBOL"]
        }
        for dim,keyfn in specs.items():
            symagg=defaultdict(newa);yearagg=defaultdict(newa)
            for p in cs:
                for r in read_csv(p):
                    base=(r["VARIANT"],dim,keyfn(r))
                    add(symagg[base+(r["SYMBOL"],)],r["N"],r["SUM_R"],r["POS_N"])
                    add(yearagg[base+(r["YEAR"],)],r["N"],r["SUM_R"],r["POS_N"])
            for k,x in symagg.items():
                base=k[:3];z=rob[base];z["symbols"]+=1
                if x["n"] and x["sum"]/x["n"]>0:z["pos_symbols"]+=1
            for k,x in yearagg.items():
                base=k[:3];z=yrrob[base];z["years"]+=1
                if x["n"] and x["sum"]/x["n"]>0:z["pos_years"]+=1
            del symagg,yearagg

    outrows=[]
    for base,t in sorted(dims.items()):
        v,d,k=base;r=rob[base];y=yrrob[base]
        outrows.append({
          "VARIANT":v,"DIM":d,"KEY":k,
          "N":t["n"],"SUM_R":f"{t['sum']:.10f}","MEAN_R":f"{t['sum']/t['n']:.10f}",
          "POS_N":t["pos"],"POS_RATE":f"{t['pos']/t['n']:.10f}",
          "SYMBOLS":r["symbols"],"POS_SYMBOLS":r["pos_symbols"],
          "POS_SYMBOL_RATE":f"{r['pos_symbols']/r['symbols']:.10f}" if r["symbols"] else "",
          "YEARS":y["years"],"POS_YEARS":y["pos_years"],
          "POS_YEAR_RATE":f"{y['pos_years']/y['years']:.10f}" if y["years"] else ""
        })

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D26A.csv",OUT_FIELDS,outrows)

    variants=sorted({x["VARIANT"] for x in outrows})
    variant_summary=[]
    for v in variants:
        allrow=dims.get((v,"ALL","ALL"))
        er=[x for x in outrows if x["VARIANT"]==v and x["DIM"]=="ENTRY_STATE"]
        xr=[x for x in outrows if x["VARIANT"]==v and x["DIM"]=="ENTRY_EXIT"]
        kr=[x for x in outrows if x["VARIANT"]==v and x["DIM"]=="ENTRY_KIND"]
        variant_summary.append({
          "variant":v,"n":allrow["n"],"mean_r":allrow["sum"]/allrow["n"],
          "positive_entry_states":sum(float(x["MEAN_R"])>0 for x in er),"entry_states":len(er),
          "positive_entry_exit":sum(float(x["MEAN_R"])>0 for x in xr),"entry_exit_cells":len(xr),
          "positive_entry_kinds":sum(float(x["MEAN_R"])>0 for x in kr),"entry_kinds":len(kr)
        })

    sign_matrix={}
    for dim in ("ENTRY_STATE","EXIT_STATE","ENTRY_EXIT","ENTRY_KIND","SIDE","PYRAMIDED"):
        rr=[x for x in outrows if x["DIM"]==dim]
        sign_matrix[dim]=[]
        for key in sorted({x["KEY"] for x in rr}):
            q=[x for x in rr if x["KEY"]==key]
            n=sum(int(x["N"]) for x in q)
            sr=sum(float(x["SUM_R"]) for x in q)
            sign_matrix[dim].append({
              "key":key,"variants_present":len(q),
              "positive_variants":sum(float(x["MEAN_R"])>0 for x in q),
              "negative_or_zero_variants":sum(float(x["MEAN_R"])<=0 for x in q),
              "weighted_n":n,"weighted_mean_r":sr/n if n else None
            })

    summary={
      "block":"D26","status":"PASS","source":"D25","symbols":symbols,"trade_records":trade_records,
      "skips":dict(skips),"state_counts":dict(states),"state_transitions":dict(trans),
      "variant_summary":variant_summary,"sign_matrix":sign_matrix,
      "contract":{"changes_to_trading_logic":False,"selection_or_optimization":False,
                  "outcome_based_filtering":False,"diagnostic_only":True}
    }
    (a.out/"D26.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=["D26 XRAY","STATUS: PASS",f"SYMBOLS: {symbols}",f"TRADE_RECORDS: {trade_records}",
           "TRADING LOGIC CHANGED: NO","SELECTION/OPTIMIZATION: NO"]
    for x in variant_summary:
        lines.append(
          f"{x['variant']}: N={x['n']} MEAN_R={x['mean_r']:.8f} "
          f"ENTRY_STATES+={x['positive_entry_states']}/{x['entry_states']} "
          f"ENTRY_EXIT+={x['positive_entry_exit']}/{x['entry_exit_cells']} "
          f"ENTRY_KIND+={x['positive_entry_kinds']}/{x['entry_kinds']}"
        )
    lines.append("SIGN CONSISTENCY:")
    for dim,rr in sign_matrix.items():
        for x in rr:
            lines.append(f"{dim} {x['key']}: += {x['positive_variants']}/{x['variants_present']} WMEAN={x['weighted_mean_r']:.8f}")
    (a.out/"D26.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
