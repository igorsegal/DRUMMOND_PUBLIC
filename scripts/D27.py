#!/usr/bin/env python3
import argparse,bisect,csv,json,statistics
from collections import Counter,defaultdict
from pathlib import Path

from drummond_replay01 import read_xfbar
import D25 as F
import D21 as X
import D23 as E

MODES=("STRICT","PROXY")
FLOW_NS=(1,2,3)
FIELDS=[
 "SYMBOL","MODE","FLOW_N","SIDE","CA_SETUP_TIME","CONFIRM_TIME","ENTRY_TIME",
 "ENTRY_STATE","EXIT_STATE","ENTRY","STOP0","EXIT","OUTCOME","R",
 "WAIT_H1","M5_BARS","TRAIL_UPDATES","DETAIL"
]

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";");w.writeheader();w.writerows(rows)

def pending_dir(prev,sm,obs,h1,h4,idx,hi,point,m5bars):
    # Reuse D25's causal CA setup detector, but do not enter.
    if sm!="CA": return None
    p=F.entry_plan(prev,sm,obs,h1,h4,idx,hi,point,m5bars,"STRICT")
    if p is None:return None
    d,q,why=p
    if why not in ("CA_BLOCK_LONG","CA_DOTTED_SHORT"):return None
    return d,why

def compatible(state,d):
    if d>0:return state in ("CA","CE_UP","CX_UP","REV_UP","TR_UP")
    return state in ("CA","CE_DN","CX_DN","REV_DN","TR_DN")

def invalid(state,d):
    if d>0:return state in ("TR_DN","REV_DN","CX_DN")
    return state in ("TR_UP","REV_UP","CX_UP")

def plan_targets(mode,h1,h4,idx,hi,point,entry,d):
    # Entry occurs only after the lineage has reached confirmed Trend Run.
    if mode=="STRICT":
        return F.strict_targets("TR_UP" if d>0 else "TR_DN",h1,h4,idx,hi,point,entry,d)
    return F.proxy_targets("TR_UP" if d>0 else "TR_DN",h1,h4,idx,hi,point,entry,d)

def record(sym,mode,fn,d,pending,pos,sm,exit_time,exit_px,outcome,rr):
    return {
      "SYMBOL":sym,"MODE":mode,"FLOW_N":fn,"SIDE":"LONG" if d>0 else "SHORT",
      "CA_SETUP_TIME":pending["setup_time"],"CONFIRM_TIME":pos["confirm_time"],
      "ENTRY_TIME":pos["entry_time"],"ENTRY_STATE":pos["entry_state"],"EXIT_STATE":sm,
      "ENTRY":f"{pos['entry']:.10f}","STOP0":f"{pos['stop0']:.10f}",
      "EXIT":f"{exit_px:.10f}","OUTCOME":outcome,"R":f"{rr:.8f}",
      "WAIT_H1":pos["wait_h1"],"M5_BARS":pos["bars"],"TRAIL_UPDATES":pos["trails"],
      "DETAIL":pending["detail"]+"|CAUSAL_TR_LIVE_REFRESH"
    }

def simulate(sym,h1,h4,m5,point,mode,flow_n,contexts):
    trades=[];pending=None;pos=None
    for idx,t,hi,ma,mb,prev,sm,obs in contexts:
        m5bars=m5[ma:mb]
        if not m5bars:continue

        # Existing trade management: same recovered lifecycle as D25, no pyramiding.
        if pos is not None:
            d=pos["d"]
            wrong=(d>0 and sm in ("REV_DN","TR_DN","CX_DN")) or (d<0 and sm in ("REV_UP","TR_UP","CX_UP"))
            streak=X.flow_streak_against(h1,idx,d)
            if wrong or streak>=flow_n:
                ex=X.exec_exit_at_market(m5bars[0],point,d,use_open=True)
                rr=d*(ex-pos["entry"])/pos["risk"]
                trades.append(record(sym,mode,flow_n,d,pos["pending"],pos,sm,t,ex,"STATE_EXIT" if wrong else "FLOW_EXIT",rr))
                pos=None;pending=None
            else:
                cand=F.stop_for(h1,idx,point,m5bars[0][1],d)
                if cand is not None:
                    if d>0 and cand>pos["stop"]+point and cand<m5bars[0][1]:
                        pos["stop"]=cand;pos["trails"]+=1
                    elif d<0 and cand<pos["stop"]-point and cand>m5bars[0][1]:
                        pos["stop"]=cand;pos["trails"]+=1

        # Invalidate a pending CA lineage only on an explicit opposite directional state.
        if pos is None and pending is not None:
            if invalid(sm,pending["d"]):
                pending=None
            elif not compatible(sm,pending["d"]) and sm not in ("EX_UP","EX_DN","CE_UP","CE_DN","UNK"):
                pending=None

        # Establish/refresh a causal CA intent. No position is opened here.
        if pos is None and pending is None:
            pd=pending_dir(prev,sm,obs,h1,h4,idx,hi,point,m5bars)
            if pd is not None:
                d,why=pd
                pending={"d":d,"setup_time":t,"detail":why,"wait":0}

        if pos is None and pending is not None:
            pending["wait"]+=1
            d=pending["d"]
            trend_ok=(d>0 and sm=="TR_UP" and obs["htp_dir"]==1) or (d<0 and sm=="TR_DN" and obs["htp_dir"]==-1)
            if trend_ok:
                q=F.live_refresh_trigger(h1,idx,m5bars,point,d)
                if q is not None:
                    ep=X.exec_entry(m5bars[q],point,d)
                    st=F.stop_for(h1,idx,point,ep,d)
                    tp,ext=plan_targets(mode,h1,h4,idx,hi,point,ep,d)
                    if st is not None and tp is not None and X.valid_geometry(ep,st,tp,d,point):
                        pos={
                          "d":d,"entry":ep,"risk":abs(ep-st),"stop":st,"stop0":st,
                          "tp":tp,"ext":ext,"entry_time":m5bars[q][0]+300,
                          "entry_state":sm,"confirm_time":t,"wait_h1":pending["wait"],
                          "bars":0,"trails":0,"pending":dict(pending)
                        }

        if pos is not None:
            d=pos["d"]
            for b in m5bars:
                if b[0]<pos["entry_time"]:continue
                pos["bars"]+=1
                hit=X.hit_levels(b,point,d,pos["stop"],pos["tp"])
                if not hit:continue
                reason,level=hit
                if reason=="AMBIGUOUS":
                    ex=X.exec_exit_at_market(b,point,d);oc="AMBIGUOUS_EXIT"
                elif reason=="TP" and pos["ext"] is not None and X.should_extend(h4,hi,d,pos["tp"],pos["ext"]):
                    pos["tp"]=pos["ext"];pos["ext"]=None
                    continue
                else:
                    ex=level;oc=reason
                rr=d*(ex-pos["entry"])/pos["risk"]
                trades.append(record(sym,mode,flow_n,d,pos["pending"],pos,sm,b[0]+300,ex,oc,rr))
                pos=None;pending=None
                break

    if pos is not None and m5:
        b=m5[-1];d=pos["d"];ex=X.exec_exit_at_market(b,point,d)
        rr=d*(ex-pos["entry"])/pos["risk"]
        trades.append(record(sym,mode,flow_n,d,pos["pending"],pos,sm,b[0]+300,ex,"DATA_END",rr))
    return trades

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

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
            ctx,_=F.build_contexts(sym,h1,h4,m5,point)
            for mode in MODES:
                for fn in FLOW_NS:
                    rows.extend(simulate(sym,h1,h4,m5,point,mode,fn,ctx))
        except Exception as e:
            errs.append({"symbol":sym,"error":str(e)})

    rows.sort(key=lambda r:(r["MODE"],int(r["FLOW_N"]),int(r["ENTRY_TIME"]),r["SYMBOL"]))
    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D27.csv",rows)

    stats={}
    for mode in MODES:
      for fn in FLOW_NS:
        rr=[x for x in rows if x["MODE"]==mode and int(x["FLOW_N"])==fn]
        vals=[float(x["R"]) for x in rr]
        byyear=defaultdict(list);bysym=defaultdict(list)
        for x in rr:
            from datetime import datetime,timezone
            y=datetime.fromtimestamp(int(x["ENTRY_TIME"]),tz=timezone.utc).year
            byyear[y].append(float(x["R"]));bysym[x["SYMBOL"]].append(float(x["R"]))
        ym=[sum(v)/len(v) for v in byyear.values()]
        sm=[sum(v)/len(v) for v in bysym.values()]
        stats[f"{mode}:F{fn}"]={
          "n":len(rr),"sum_r":sum(vals),
          "mean_r":sum(vals)/len(vals) if vals else None,
          "median_r":statistics.median(vals) if vals else None,
          "positive_rate":sum(v>0 for v in vals)/len(vals) if vals else None,
          "years":len(ym),"positive_years":sum(v>0 for v in ym),
          "symbols":len(sm),"positive_symbols":sum(v>0 for v in sm),
          "equal_weight_symbol_mean_r":sum(sm)/len(sm) if sm else None,
          "mean_wait_h1":sum(int(x["WAIT_H1"]) for x in rr)/len(rr) if rr else None,
          "max_r":max(vals) if vals else None,"min_r":min(vals) if vals else None
        }

    summary={
      "block":"D27","status":"PASS" if syms>0 and not errs else "FAIL",
      "symbols":syms,"trades":len(rows),"errors":len(errs),"skips":dict(skips),"stats":stats,
      "contract":{
        "source":"D26 causal hypothesis",
        "ca_setup_opens_trade":False,
        "first_entry_requires_confirmed_same_direction_trend":True,
        "first_entry_requires_actual_live_pldot_refresh":True,
        "future_refresh_filter_used":False,
        "lookahead":False,
        "pyramiding":"OFF",
        "selection_or_optimization":False,
        "factory02_lifecycle_used":False
      }
    }
    (a.out/"D27.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.out/"D27_ERR.json").write_text(json.dumps(errs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("D27",summary["status"],"symbols",syms,"trades",len(rows),"errors",len(errs))
    for k,v in stats.items():
        print(k,"N",v["n"],"MEAN_R",f"{v['mean_r']:.8f}" if v["mean_r"] is not None else "NA",
              "YEARS+",v["positive_years"],"/",v["years"],"SYMS+",v["positive_symbols"],"/",v["symbols"])
    if errs:raise SystemExit(2)

if __name__=="__main__":
    main()
