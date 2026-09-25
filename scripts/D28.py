#!/usr/bin/env python3
import argparse,csv,json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

from drummond_replay01 import read_xfbar
import D25 as F
import D27 as C

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

def mean(a):
    return a["sum"]/a["n"] if a["n"] else None

def wait_bucket(n):
    n=int(n)
    if n<=1:return "01"
    if n<=4:return "02_04"
    if n<=8:return "05_08"
    if n<=16:return "09_16"
    if n<=32:return "17_32"
    return "33_PLUS"

def refresh_bucket(t):
    q=max(0,(int(t["ENTRY_TIME"])-int(t["CONFIRM_TIME"]))//300)
    if q<=3:return "01_03"
    if q<=6:return "04_06"
    if q<=9:return "07_09"
    if q<=12:return "10_12"
    return "13_PLUS"

def hold_bucket(n):
    n=int(n)
    if n<=12:return "001_012"
    if n<=48:return "013_048"
    if n<=144:return "049_144"
    if n<=576:return "145_576"
    return "577_PLUS"

def detail_base(s):
    return (s or "UNKNOWN").split("|",1)[0]

def keys_for(t):
    side=t["SIDE"];en=t["ENTRY_STATE"];ex=t["EXIT_STATE"];oc=t["OUTCOME"]
    det=detail_base(t["DETAIL"])
    wb=wait_bucket(t["WAIT_H1"])
    rb=refresh_bucket(t)
    hb=hold_bucket(t["M5_BARS"])
    return [
      ("ALL","ALL"),
      ("SIDE",side),
      ("ENTRY_STATE",en),
      ("EXIT_STATE",ex),
      ("OUTCOME",oc),
      ("DETAIL",det),
      ("WAIT_H1",wb),
      ("REFRESH_M5",rb),
      ("HOLD_M5",hb),
      ("SIDE_WAIT_H1",side+"|"+wb),
      ("SIDE_REFRESH_M5",side+"|"+rb),
      ("SIDE_OUTCOME",side+"|"+oc),
    ]

def write_csv(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";");w.writeheader();w.writerows(rows)

def dim_rows(agg):
    out=[]
    for (variant,dim,key),a in sorted(agg.items()):
        out.append({
          "VARIANT":variant,"DIM":dim,"KEY":key,"N":a["n"],
          "SUM_R":f"{a['sum']:.10f}",
          "MEAN_R":"" if not a["n"] else f"{mean(a):.10f}",
          "POS_N":a["pos"],
          "POS_RATE":"" if not a["n"] else f"{a['pos']/a['n']:.10f}",
          "MIN_R":"" if a["min"] is None else f"{a['min']:.10f}",
          "MAX_R":"" if a["max"] is None else f"{a['max']:.10f}"
        })
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    dims=defaultdict(newagg)
    years=defaultdict(newagg)
    robust=defaultdict(lambda:{"symbols":0,"pos_symbols":0})
    syms=0;trade_records=0;errs=[];skips=Counter()

    for h1p in sorted(a.data_root.rglob("*_H1.bin")):
        sym=h1p.name[:-7]
        try:
            h4s=list(a.data_root.rglob(f"{sym}_H4.bin"))
            m5s=list(a.data_root.rglob(f"{sym}_M5.bin"))
            if not h4s:skips["SKIP_NO_H4"]+=1;continue
            if not m5s:skips["SKIP_NO_M5"]+=1;continue
            if len(h4s)!=1 or len(m5s)!=1:raise RuntimeError("duplicate required TF")
            h1h,h1=read_xfbar(h1p);h4h,h4=read_xfbar(h4s[0]);m5h,m5=read_xfbar(m5s[0])
            if h1h["period_seconds"]!=3600 or h4h["period_seconds"]!=14400 or m5h["period_seconds"]!=300:
                raise RuntimeError("TF contract")
            point=h1h["point"];syms+=1
            ctx,_=F.build_contexts(sym,h1,h4,m5,point)
            local=defaultdict(newagg)

            for mode in C.MODES:
              for fn in C.FLOW_NS:
                variant=f"{mode}:F{fn}"
                rr=C.simulate(sym,h1,h4,m5,point,mode,fn,ctx)
                trade_records+=len(rr)
                for t in rr:
                    r=float(t["R"])
                    year=str(datetime.fromtimestamp(int(t["ENTRY_TIME"]),tz=timezone.utc).year)
                    for dim,key in keys_for(t):
                        base=(variant,dim,key)
                        add(dims[base],r)
                        add(local[base],r)
                        add(years[base+(year,)],r)
                    base=(variant,"SYMBOL",sym)
                    add(dims[base],r)
                    add(local[base],r)
                    add(years[base+(year,)],r)

            for base,x in local.items():
                z=robust[base];z["symbols"]+=1
                if x["n"] and mean(x)>0:z["pos_symbols"]+=1
        except Exception as e:
            errs.append({"symbol":sym,"error":str(e)})

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D28.csv",DIM_FIELDS,dim_rows(dims))

    rrows=[]
    for (variant,dim,key),z in sorted(robust.items()):
        rrows.append({
          "VARIANT":variant,"DIM":dim,"KEY":key,
          "SYMBOLS":z["symbols"],"POS_SYMBOLS":z["pos_symbols"],
          "POS_SYMBOL_RATE":f"{z['pos_symbols']/z['symbols']:.10f}" if z["symbols"] else ""
        })
    write_csv(a.out/"D28R.csv",ROB_FIELDS,rrows)

    yrows=[]
    for (variant,dim,key,year),x in sorted(years.items()):
        yrows.append({
          "VARIANT":variant,"DIM":dim,"KEY":key,"YEAR":year,
          "N":x["n"],"SUM_R":f"{x['sum']:.10f}","MEAN_R":f"{mean(x):.10f}",
          "POS_N":x["pos"],"POS_RATE":f"{x['pos']/x['n']:.10f}"
        })
    write_csv(a.out/"D28Y.csv",YEAR_FIELDS,yrows)

    summary={
      "block":"D28","status":"PASS" if syms>0 and not errs else "FAIL",
      "source":"D27","symbols":syms,"trade_records":trade_records,
      "errors":len(errs),"skips":dict(skips),
      "dimensions":[
        "ALL","SIDE","ENTRY_STATE","EXIT_STATE","OUTCOME","DETAIL",
        "WAIT_H1","REFRESH_M5","HOLD_M5","SIDE_WAIT_H1",
        "SIDE_REFRESH_M5","SIDE_OUTCOME","SYMBOL"
      ],
      "buckets":{
        "WAIT_H1":["01","02_04","05_08","09_16","17_32","33_PLUS"],
        "REFRESH_M5":["01_03","04_06","07_09","10_12","13_PLUS"],
        "HOLD_M5":["001_012","013_048","049_144","145_576","577_PLUS"]
      },
      "contract":{
        "source_engine":"D27",
        "d27_trading_logic_changed":False,
        "selection_or_optimization":False,
        "outcome_based_filtering":False,
        "diagnostic_only":True,
        "lookahead":False,
        "post_trade_dimensions_not_entry_filters":["EXIT_STATE","OUTCOME","HOLD_M5"],
        "purpose":"loss attribution and causal-delay diagnosis only"
      }
    }
    (a.out/"D28.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.out/"D28_ERR.json").write_text(json.dumps(errs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("D28",summary["status"],"symbols",syms,"trade_records",trade_records,
          "errors",len(errs),"dims",len(dims),"years",len(years))
    if errs:raise SystemExit(2)

if __name__=="__main__":
    main()
