#!/usr/bin/env python3
import argparse,csv,json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

from drummond_replay01 import read_xfbar
import D25 as F

DIM_FIELDS=["VARIANT","DIM","KEY","N","SUM_R","MEAN_R","POS_N","POS_RATE","MIN_R","MAX_R"]
ROB_FIELDS=["VARIANT","DIM","KEY","SYMBOLS","POS_SYMBOLS","POS_SYMBOL_RATE"]
YEAR_FIELDS=["VARIANT","DIM","KEY","YEAR","N","SUM_R","MEAN_R","POS_N","POS_RATE"]

def newagg():
    return {"n":0,"sum":0.0,"pos":0,"min":None,"max":None}

def add(a,r):
    a["n"]+=1;a["sum"]+=r
    if r>0:a["pos"]+=1
    a["min"]=r if a["min"] is None else min(a["min"],r)
    a["max"]=r if a["max"] is None else max(a["max"],r)

def merge(a,b):
    a["n"]+=b["n"];a["sum"]+=b["sum"];a["pos"]+=b["pos"]
    if b["min"] is not None:a["min"]=b["min"] if a["min"] is None else min(a["min"],b["min"])
    if b["max"] is not None:a["max"]=b["max"] if a["max"] is None else max(a["max"],b["max"])

def mean(a):return a["sum"]/a["n"] if a["n"] else None

def kind(detail):
    d=detail or ""
    if d.startswith("TREND_REFRESH"):return "TREND_REFRESH"
    if d.startswith("CA_"):return "CA"
    if d.startswith("CONGESTION_EXIT"):return "CX"
    if d.startswith("REVERSAL"):return "REV"
    return "OTHER"

def keys_for(t):
    en=t["ENTRY_STATE"];ex=t["EXIT_STATE"];side=t["SIDE"]
    ek=kind(t["DETAIL"]);pyr="Y" if int(t["PYRAMIDS"])>0 else "N"
    return [
      ("ALL","ALL"),
      ("ENTRY_STATE",en),
      ("EXIT_STATE",ex),
      ("ENTRY_EXIT",en+"->"+ex),
      ("SIDE",side),
      ("ENTRY_KIND",ek),
      ("PYRAMIDED",pyr),
      ("ENTRY_SIDE",en+"|"+side),
      ("ENTRY_KIND_SIDE",ek+"|"+side),
      ("ENTRY_PYR",en+"|"+pyr),
    ]

def write_csv(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";");w.writeheader();w.writerows(rows)

def dim_rows(agg):
    rows=[]
    for (variant,dim,key),a in sorted(agg.items()):
        rows.append({
          "VARIANT":variant,"DIM":dim,"KEY":key,"N":a["n"],"SUM_R":f"{a['sum']:.10f}",
          "MEAN_R":"" if not a["n"] else f"{mean(a):.10f}",
          "POS_N":a["pos"],"POS_RATE":"" if not a["n"] else f"{a['pos']/a['n']:.10f}",
          "MIN_R":"" if a["min"] is None else f"{a['min']:.10f}",
          "MAX_R":"" if a["max"] is None else f"{a['max']:.10f}"
        })
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    dims=defaultdict(newagg)
    years=defaultdict(newagg)
    robust=defaultdict(lambda:{"symbols":0,"pos_symbols":0})
    transitions=Counter();state_counts=Counter()
    syms=0;trades_total=0;errs=[];skips=Counter()

    for h1p in sorted(a.data_root.rglob("*_H1.bin")):
        sym=h1p.name[:-7]
        try:
            h4s=list(a.data_root.rglob(f"{sym}_H4.bin"));m5s=list(a.data_root.rglob(f"{sym}_M5.bin"))
            if not h4s:skips["SKIP_NO_H4"]+=1;continue
            if not m5s:skips["SKIP_NO_M5"]+=1;continue
            if len(h4s)!=1 or len(m5s)!=1:raise RuntimeError("duplicate required TF")
            h1h,h1=read_xfbar(h1p);h4h,h4=read_xfbar(h4s[0]);m5h,m5=read_xfbar(m5s[0])
            if h1h["period_seconds"]!=3600 or h4h["period_seconds"]!=14400 or m5h["period_seconds"]!=300:
                raise RuntimeError("TF contract")
            point=h1h["point"];syms+=1
            ctx,ss=F.build_contexts(sym,h1,h4,m5,point)
            for s in ss:
                transitions[(s["PREV_STATE"],s["STATE"])]+=1
                state_counts[s["STATE"]]+=1

            local=defaultdict(newagg)
            for mode in F.MODES:
              for fn in F.FLOW_NS:
               for pc in F.PYR_CAPS:
                variant=f"{mode}:F{fn}:P{pc}"
                rr=F.simulate_variant(sym,h1,h4,m5,point,mode,fn,pc,ctx)
                trades_total+=len(rr)
                for t in rr:
                    r=float(t["R"])
                    year=str(datetime.fromtimestamp(int(t["ENTRY_TIME"]),tz=timezone.utc).year)
                    for dim,key in keys_for(t):
                        base=(variant,dim,key)
                        add(dims[base],r)
                        add(local[base],r)
                        add(years[base+(year,)],r)
                    # Symbol itself is a first-class diagnostic dimension.
                    base=(variant,"SYMBOL",sym)
                    add(dims[base],r)
                    add(local[base],r)
                    add(years[base+(year,)],r)

            # Symbols are disjoint across shards; sign counts can be reduced safely later.
            for base,x in local.items():
                z=robust[base];z["symbols"]+=1
                if x["n"] and mean(x)>0:z["pos_symbols"]+=1
        except Exception as e:
            errs.append({"symbol":sym,"error":str(e)})

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D26.csv",DIM_FIELDS,dim_rows(dims))

    rrows=[]
    for (variant,dim,key),z in sorted(robust.items()):
        rrows.append({
          "VARIANT":variant,"DIM":dim,"KEY":key,
          "SYMBOLS":z["symbols"],"POS_SYMBOLS":z["pos_symbols"],
          "POS_SYMBOL_RATE":f"{z['pos_symbols']/z['symbols']:.10f}" if z["symbols"] else ""
        })
    write_csv(a.out/"D26R.csv",ROB_FIELDS,rrows)

    yrows=[]
    for (variant,dim,key,year),x in sorted(years.items()):
        yrows.append({
          "VARIANT":variant,"DIM":dim,"KEY":key,"YEAR":year,
          "N":x["n"],"SUM_R":f"{x['sum']:.10f}","MEAN_R":f"{mean(x):.10f}",
          "POS_N":x["pos"],"POS_RATE":f"{x['pos']/x['n']:.10f}"
        })
    write_csv(a.out/"D26Y.csv",YEAR_FIELDS,yrows)

    summary={
      "block":"D26","status":"PASS" if syms>0 and not errs else "FAIL",
      "symbols":syms,"trade_records":trades_total,"errors":len(errs),"skips":dict(skips),
      "state_counts":dict(sorted(state_counts.items())),
      "state_transitions":{f"{x}->{y}":n for (x,y),n in sorted(transitions.items())},
      "dimensions":["ALL","ENTRY_STATE","EXIT_STATE","ENTRY_EXIT","SIDE","ENTRY_KIND","PYRAMIDED","ENTRY_SIDE","ENTRY_KIND_SIDE","ENTRY_PYR","SYMBOL"],
      "contract":{
        "source_engine":"D25","changes_to_trading_logic":False,
        "selection_or_optimization":False,"outcome_based_filtering":False,
        "purpose":"loss attribution only"
      }
    }
    (a.out/"D26.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.out/"D26_ERR.json").write_text(json.dumps(errs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("D26",summary["status"],"symbols",syms,"trade_records",trades_total,"errors",len(errs),
          "dims",len(dims),"years",len(years))
    if errs:raise SystemExit(2)

if __name__=="__main__":
    main()
