#!/usr/bin/env python3
import argparse,csv,json,math
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

from drummond_replay01 import read_xfbar
import D25 as F
import D27 as C
import D21 as X

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

def bucket(v,cuts,labels):
    for c,l in zip(cuts,labels):
        if v<c:return l
    return labels[-1]

def target_r_bucket(v):
    return bucket(v,[0.50,0.75,1.00,1.50,2.00],
                  ["LT_0.50","0.50_0.75","0.75_1.00","1.00_1.50","1.50_2.00","GE_2.00"])

def stop_h1_bucket(v):
    return bucket(v,[0.25,0.50,1.00,2.00],
                  ["LT_0.25","0.25_0.50","0.50_1.00","1.00_2.00","GE_2.00"])

def target_h1_bucket(v):
    return bucket(v,[0.25,0.50,1.00,2.00],
                  ["LT_0.25","0.25_0.50","0.50_1.00","1.00_2.00","GE_2.00"])

def gap_h1_bucket(v):
    if v < -0.50:return "LT_-0.50"
    if v < -0.25:return "-0.50_-0.25"
    if v < 0.00:return "-0.25_0.00"
    if v < 0.25:return "0.00_0.25"
    if v < 0.50:return "0.25_0.50"
    return "GE_0.50"

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
    reconstruction_errors=0
    reconstruction_reasons=Counter()
    reconstruction_examples=[]
    diagnostic_skips=Counter()

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
            by_time={int(t):(idx,hi) for idx,t,hi,ma,mb,prev,sm,obs in ctx}
            m5_by_time={int(b[0]):b for b in m5}
            local=defaultdict(newagg)

            for mode in C.MODES:
              for fn in C.FLOW_NS:
                variant=f"{mode}:F{fn}"
                rr=C.simulate(sym,h1,h4,m5,point,mode,fn,ctx)
                trade_records+=len(rr)

                for t in rr:
                    r=float(t["R"])
                    year=str(datetime.fromtimestamp(int(t["ENTRY_TIME"]),tz=timezone.utc).year)

                    # Every D27 trade must remain represented in the D29 baseline.
                    base_keys=[("ALL","ALL"),("SIDE",t["SIDE"])]
                    for dim,key in base_keys:
                        base=(variant,dim,key)
                        add(dims[base],r);add(local[base],r);add(years[base+(year,)],r)
                    base=(variant,"SYMBOL",sym)
                    add(dims[base],r);add(local[base],r);add(years[base+(year,)],r)

                    confirm=int(t["CONFIRM_TIME"])
                    z=by_time.get(confirm)
                    if z is None:
                        reconstruction_errors+=1
                        reconstruction_reasons["CONFIRM_CONTEXT_MISSING"]+=1
                        if len(reconstruction_examples)<20:
                            reconstruction_examples.append({"symbol":sym,"variant":variant,"entry_time":t["ENTRY_TIME"],"reason":"CONFIRM_CONTEXT_MISSING"})
                        continue
                    idx,hi=z
                    d=1 if t["SIDE"]=="LONG" else -1

                    # Reconstruct the exact D27 entry from the original M5 bar,
                    # not from D27.csv's 10-decimal display string. This avoids
                    # false geometry failures at a one-point boundary.
                    entry_bar=m5_by_time.get(int(t["ENTRY_TIME"])-300)
                    if entry_bar is None:
                        reconstruction_errors+=1
                        reconstruction_reasons["ENTRY_M5_BAR_MISSING"]+=1
                        if len(reconstruction_examples)<20:
                            reconstruction_examples.append({"symbol":sym,"variant":variant,"entry_time":t["ENTRY_TIME"],"reason":"ENTRY_M5_BAR_MISSING"})
                        continue
                    entry=X.exec_entry(entry_bar,point,d)
                    stop0=F.stop_for(h1,idx,point,entry,d)
                    if stop0 is None:
                        reconstruction_errors+=1
                        reconstruction_reasons["STOP_RECONSTRUCTION_NONE"]+=1
                        if len(reconstruction_examples)<20:
                            reconstruction_examples.append({"symbol":sym,"variant":variant,"entry_time":t["ENTRY_TIME"],"reason":"STOP_RECONSTRUCTION_NONE"})
                        continue
                    risk=abs(entry-stop0)
                    if not math.isfinite(risk) or risk<=point:
                        reconstruction_errors+=1
                        reconstruction_reasons["RISK_GEOMETRY_INVALID"]+=1
                        if len(reconstruction_examples)<20:
                            reconstruction_examples.append({"symbol":sym,"variant":variant,"entry_time":t["ENTRY_TIME"],"reason":"RISK_GEOMETRY_INVALID"})
                        continue

                    tp,ext=C.plan_targets(mode,h1,h4,idx,hi,point,entry,d)
                    if tp is None:
                        reconstruction_errors+=1
                        reconstruction_reasons["TARGET_RECONSTRUCTION_NONE"]+=1
                        if len(reconstruction_examples)<20:
                            reconstruction_examples.append({"symbol":sym,"variant":variant,"entry_time":t["ENTRY_TIME"],"reason":"TARGET_RECONSTRUCTION_NONE"})
                        continue
                    tr=d*(tp-entry)/risk
                    if not math.isfinite(tr) or tr<=0:
                        reconstruction_errors+=1
                        reconstruction_reasons["TARGET_R_INVALID"]+=1
                        if len(reconstruction_examples)<20:
                            reconstruction_examples.append({"symbol":sym,"variant":variant,"entry_time":t["ENTRY_TIME"],"reason":"TARGET_R_INVALID"})
                        continue

                    ext_present="YES" if ext is not None else "NO"
                    geo_keys=[
                      ("TARGET_R",target_r_bucket(tr)),
                      ("EXTENSION",ext_present),
                    ]

                    # H1-normalized diagnostics are undefined on a zero/flat
                    # previous H1 bar. That is missing diagnostic geometry,
                    # not a D27 reconstruction failure.
                    prev=h1[idx-1] if idx>=1 else None
                    hr=(prev[2]-prev[3]) if prev is not None else 0.0
                    if not math.isfinite(hr) or hr<=point*0.5:
                        diagnostic_skips["H1_RANGE_UNAVAILABLE"]+=1
                    else:
                        sh=risk/hr
                        th=abs(tp-entry)/hr
                        gap=d*(entry-prev[4])/hr
                        geo_keys.extend([
                          ("STOP_H1",stop_h1_bucket(sh)),
                          ("TARGET_H1",target_h1_bucket(th)),
                          ("ENTRY_GAP_H1",gap_h1_bucket(gap)),
                          ("TARGET_R_X_STOP_H1",target_r_bucket(tr)+"|"+stop_h1_bucket(sh)),
                        ])

                    for dim,key in geo_keys:
                        base=(variant,dim,key)
                        add(dims[base],r);add(local[base],r);add(years[base+(year,)],r)

            for base,x in local.items():
                z=robust[base];z["symbols"]+=1
                if x["n"] and mean(x)>0:z["pos_symbols"]+=1
        except Exception as e:
            errs.append({"symbol":sym,"error":str(e)})

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D29.csv",DIM_FIELDS,dim_rows(dims))

    rrows=[]
    for (variant,dim,key),z in sorted(robust.items()):
        rrows.append({
          "VARIANT":variant,"DIM":dim,"KEY":key,
          "SYMBOLS":z["symbols"],"POS_SYMBOLS":z["pos_symbols"],
          "POS_SYMBOL_RATE":f"{z['pos_symbols']/z['symbols']:.10f}" if z["symbols"] else ""
        })
    write_csv(a.out/"D29R.csv",ROB_FIELDS,rrows)

    yrows=[]
    for (variant,dim,key,year),x in sorted(years.items()):
        yrows.append({
          "VARIANT":variant,"DIM":dim,"KEY":key,"YEAR":year,
          "N":x["n"],"SUM_R":f"{x['sum']:.10f}","MEAN_R":f"{mean(x):.10f}",
          "POS_N":x["pos"],"POS_RATE":f"{x['pos']/x['n']:.10f}"
        })
    write_csv(a.out/"D29Y.csv",YEAR_FIELDS,yrows)

    summary={
      "block":"D29","status":"PASS" if syms>0 and not errs and reconstruction_errors==0 else "FAIL",
      "source":"D27","purpose":"causal entry-geometry attribution",
      "symbols":syms,"trade_records":trade_records,
      "errors":len(errs),"reconstruction_errors":reconstruction_errors,
      "reconstruction_reasons":dict(reconstruction_reasons),
      "reconstruction_examples":reconstruction_examples,
      "diagnostic_skips":dict(diagnostic_skips),"skips":dict(skips),
      "dimensions":[
        "ALL","SIDE","TARGET_R","STOP_H1","TARGET_H1",
        "ENTRY_GAP_H1","EXTENSION","TARGET_R_X_STOP_H1","SYMBOL"
      ],
      "contract":{
        "source_engine":"D27",
        "d27_trading_logic_changed":False,
        "all_diagnostic_dimensions_known_at_entry":True,
        "entry_geometry_replayed_from_original_m5_bar":True,
        "undefined_h1_normalization_is_skipped_not_imputed":True,
        "selection_or_optimization":False,
        "outcome_based_filtering":False,
        "diagnostic_only":True,
        "lookahead":False,
        "promotion_allowed":False
      }
    }
    (a.out/"D29.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.out/"D29_ERR.json").write_text(json.dumps(errs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    print("D29",summary["status"],"symbols",syms,"trade_records",trade_records,
          "errors",len(errs),"reconstruction_errors",reconstruction_errors,
          "reconstruction_reasons",dict(reconstruction_reasons),
          "diagnostic_skips",dict(diagnostic_skips),"dims",len(dims),"years",len(years))
    if summary["status"]!="PASS":raise SystemExit(2)

if __name__=="__main__":
    main()
