#!/usr/bin/env python3
import argparse,csv,json,statistics
from collections import Counter
from pathlib import Path

import D21 as B
import D23 as E
from drummond_replay01 import read_xfbar
from D17 import static_dot,typ,envelope_proxy

MODES=("STRICT","PROXY")
FIELDS=["MODE"]+B.FIELDS

def strict_zones(bars,idx,point,price):
    z=E.zones(bars,idx,point,price)
    return {
      "near_sup":z["near_sup"],"far_sup":z["far_sup_low"],
      "near_res":z["near_res"],"far_res":z["far_res_high"],
      "lf":z["lf"],"vals":z["vals"],"sup_n":z["sup_n"],"res_n":z["res_n"]
    }

def _valid_target(entry,t,d,point):
    if t is None:return None
    if d>0 and t>entry+point:return t
    if d<0 and t<entry-point:return t
    return None

def targets_strict(family,h1,h4,idx,hi,point,entry,d):
    if family=="EX":
        pl=static_dot(h1,idx)
        ld=(h1[idx][1]+typ(h1[idx-1])+typ(h1[idx-2]))/3.0
        if pl is None:return None,None
        # Conservative exhaust target = first edge of Refresh zone in direction of return.
        t=min(pl,ld) if d>0 else max(pl,ld)
        return _valid_target(entry,t,d,point),None
    z=E.zones(h4,hi,point,entry) if family!="CA" else E.zones(h1,idx,point,entry)
    t=z["near_res"] if d>0 else z["near_sup"]
    ext=z["far_res_high"] if d>0 else z["far_sup_low"]
    return _valid_target(entry,t,d,point),_valid_target(entry,ext,d,point)

def targets_proxy(family,h1,h4,idx,hi,point,entry,d):
    if family=="CA":
        eb,et=envelope_proxy(h1,idx)
        if eb is None:return None,None
        return (_valid_target(entry,et,d,point),None) if d>0 else (_valid_target(entry,eb,d,point),None)
    if family=="EX":
        pl=static_dot(h1,idx)
        ld=(h1[idx][1]+typ(h1[idx-1])+typ(h1[idx-2]))/3.0
        eb,et=envelope_proxy(h1,idx)
        if pl is None:return None,None
        t=min(pl,ld) if d>0 else max(pl,ld)
        ext=et if d>0 else eb
        return _valid_target(entry,t,d,point),_valid_target(entry,ext,d,point)
    t=E.nearby_target(h4,hi,point,entry,d)
    ext=E.further_target(h4,hi,point,entry,d)
    return t,ext

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";");w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    # Freeze D21 engine to D23 corrected energy geometry.
    B.line_zones=strict_zones

    rows=[];errs=[];skips=Counter();syms=0
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
            for mode in MODES:
                B.targets_for=targets_strict if mode=="STRICT" else targets_proxy
                for family in B.FAMILIES:
                    for fn in B.FLOW_NS:
                        rr=B.simulate(sym,h1,h4,m5,point,family,fn)
                        for x in rr:
                            x={"MODE":mode,**x}
                            x["DETAIL"]=x["DETAIL"]+("|D23_STRICT_ENERGY" if mode=="STRICT" else "|D23_STRICT_FO|ENV_PROXY")
                            rows.append(x)
        except Exception as e:
            errs.append({"symbol":sym,"error":str(e)})

    rows.sort(key=lambda r:(r["MODE"],r["FAMILY"],int(r["FLOW_N"]),int(r["ENTRY_TIME"]),r["SYMBOL"]))
    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D24.csv",rows)

    groups={}
    for mode in MODES:
      for fam in B.FAMILIES:
       for fn in B.FLOW_NS:
        rr=[x for x in rows if x["MODE"]==mode and x["FAMILY"]==fam and int(x["FLOW_N"])==fn]
        vals=[float(x["R"]) for x in rr]
        aa=sorted(vals)
        trim=max(0,int(len(aa)*0.01))
        tv=aa[trim:len(aa)-trim] if trim>0 and len(aa)>2*trim else aa
        bysym={}
        for x in rr:bysym.setdefault(x["SYMBOL"],[]).append(float(x["R"]))
        sm=[sum(v)/len(v) for v in bysym.values()]
        groups[f"{mode}:{fam}:F{fn}"]={
          "n":len(rr),"sum_r":sum(vals),
          "mean_r":sum(vals)/len(vals) if vals else None,
          "median_r":statistics.median(vals) if vals else None,
          "trimmed_1pct_mean_r":sum(tv)/len(tv) if tv else None,
          "min_r":min(vals) if vals else None,"max_r":max(vals) if vals else None,
          "equal_weight_symbol_mean_r":sum(sm)/len(sm) if sm else None,
          "symbols":len(sm),
          "positive_rate":sum(v>0 for v in vals)/len(vals) if vals else None
        }

    summary={
      "block":"D24","status":"PASS" if syms>0 and not errs else "FAIL",
      "symbols":syms,"trades":len(rows),"errors":len(errs),"skips":dict(skips),
      "modes":{
        "STRICT":"Further Out=5/2+5/9 only; Nearby=line components; EX target=Refresh only; no envelope target.",
        "PROXY":"Further Out=5/2+5/9 only; Lesson16 map uses explicitly RECOVERED_PROXY ET/EB where needed."
      },
      "stats":groups,
      "factory02_lifecycle_used":False,
      "oos_selection":False,"parameter_optimization":False,"pyramiding":"OFF"
    }
    (a.out/"D24.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.out/"D24_ERR.json").write_text(json.dumps(errs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("D24",summary["status"],"symbols",syms,"trades",len(rows),"errors",len(errs),"skips",dict(skips))
    for k,v in groups.items():
        print(k,"N",v["n"],"MEAN_R",f"{v['mean_r']:.8f}" if v["mean_r"] is not None else "NA")
    if errs:raise SystemExit(2)

if __name__=="__main__":
    main()
