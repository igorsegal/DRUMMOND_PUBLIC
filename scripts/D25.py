#!/usr/bin/env python3
import argparse,bisect,csv,json,math,statistics
from collections import Counter,defaultdict
from pathlib import Path

from drummond_replay01 import read_xfbar
from D17 import (
    static_dot,typ,three_trend,state as raw_state,line_features,
    pl_push,losing_push,envelope_proxy
)
import D21 as X
import D23 as E

STATES=("UNK","TR_UP","TR_DN","EX_UP","EX_DN","CE_UP","CE_DN","CA","REV_UP","REV_DN","CX_UP","CX_DN")
MODES=("STRICT","PROXY")
FLOW_NS=(1,2,3)
PYR_CAPS=(0,1,2)

TRADE_FIELDS=[
 "SYMBOL","MODE","FLOW_N","PYR_CAP","ENTRY_STATE","EXIT_STATE","SIDE",
 "SETUP_TIME","ENTRY_TIME","EXIT_TIME","UNITS","ENTRY0","STOP0",
 "EXIT","OUTCOME","R","M5_BARS","TRAIL_UPDATES","PYRAMIDS","DETAIL"
]
STATE_FIELDS=[
 "SYMBOL","TIME","STATE","PREV_STATE","RAW","HTP_RAW","HTP_DIR",
 "PL_PUSH_UP","PL_PUSH_DN","LOSING_PUSH","MATURE_UP","MATURE_DN",
 "BLOCK_STRONG","EXIT_UP","EXIT_DN","REASON"
]

def one(root,pat,desc):
    h=list(Path(root).rglob(pat))
    if len(h)!=1:raise RuntimeError(f"{desc}: expected 1 got {len(h)}")
    return h[0]

def write_csv(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";");w.writeheader();w.writerows(rows)

def hidx(h4t,t):
    return bisect.bisect_right(h4t,t)-1

def tdir(s):
    if s=="TREND_RUN_UP":return 1
    if s=="TREND_RUN_DOWN":return -1
    return 0

def block_zone(h1,idx):
    a=static_dot(h1,idx-2);b=static_dot(h1,idx-3)
    if a is None or b is None:return None
    return (min(a,b),max(a,b))

def block_strong(h1,h4,idx,hi,point):
    bz=block_zone(h1,idx)
    hp=static_dot(h4,hi)
    if bz is None or hp is None:return False
    lo,hi2=bz
    return lo-10*point<=hp<=hi2+10*point

def reached_htp_far(h1,h4,idx,hi,point,d):
    # Current completed LTP bar reaching recovered HTP Further Out.
    if idx<1:return False
    b=h1[idx-1]
    ref=b[4]
    z=E.zones(h4,hi,point,ref)
    if d>0:
        far=z["far_res_low"]
        return far is not None and b[2]>=far
    far=z["far_sup_high"]
    return far is not None and b[3]<=far

def nearby_holds(h1,idx,point,d):
    lf,vals,sn,rn=line_features(h1,idx,point)
    # Counter-trend energy cluster: 5/1 + 5/2 + 5/9 family evidence.
    if d>0:
        return sum(lf[n] for n in ("L51_DOWN","L52_DOWN","L59_DOWN"))>=2
    return sum(lf[n] for n in ("L51_UP","L52_UP","L59_UP"))>=2

def exit_signal(h1,idx,point,d,htp_dir):
    if htp_dir!=d:return False
    if idx<2:return False
    p,_,_,_=line_features(h1,idx-1,point)
    c,_,_,_=line_features(h1,idx,point)
    if d>0:return bool(p["L61_DOWN"] and not c["L61_DOWN"])
    return bool(p["L61_UP"] and not c["L61_UP"])

def evolve(prev,h1,h4,idx,hi,point):
    raw=raw_state(h1,idx,point)
    hr=raw_state(h4,hi,point)
    hd=tdir(hr)
    rdir=tdir(raw)
    lose=losing_push(h1,idx,point)
    mup=reached_htp_far(h1,h4,idx,hi,point,1) and lose and nearby_holds(h1,idx,point,1)
    mdn=reached_htp_far(h1,h4,idx,hi,point,-1) and lose and nearby_holds(h1,idx,point,-1)
    strong=block_strong(h1,h4,idx,hi,point)
    exup=exit_signal(h1,idx,point,1,hd)
    exdn=exit_signal(h1,idx,point,-1,hd)

    reason=""
    nxt=prev

    if prev in ("UNK","REV_UP","REV_DN","CX_UP","CX_DN"):
        if rdir==1 and hd==1:nxt="TR_UP";reason="CONFIRMED_TREND_UP"
        elif rdir==-1 and hd==-1:nxt="TR_DN";reason="CONFIRMED_TREND_DN"
        elif raw=="CONGESTION_ACTION":nxt="CA";reason="RAW_CONGESTION"
        elif raw=="CONGESTION_ENTRANCE_UP":nxt="CE_UP";reason="RAW_CE_UP"
        elif raw=="CONGESTION_ENTRANCE_DOWN":nxt="CE_DN";reason="RAW_CE_DN"

    elif prev=="TR_UP":
        if mup:nxt="EX_UP";reason="HTP_FAR+LOSE+COUNTER_NEARBY"
        elif raw=="CONGESTION_ENTRANCE_DOWN":nxt="CE_DN";reason="TREND_TO_CE"
        elif rdir==-1 and hd==-1:nxt="REV_DN";reason="CONFIRMED_REVERSAL"
        else:nxt="TR_UP";reason="TREND_CONTINUE"

    elif prev=="TR_DN":
        if mdn:nxt="EX_DN";reason="HTP_FAR+LOSE+COUNTER_NEARBY"
        elif raw=="CONGESTION_ENTRANCE_UP":nxt="CE_UP";reason="TREND_TO_CE"
        elif rdir==1 and hd==1:nxt="REV_UP";reason="CONFIRMED_REVERSAL"
        else:nxt="TR_DN";reason="TREND_CONTINUE"

    elif prev=="EX_UP":
        # Exhaust is context, not an autonomous reversal trade.
        if raw in ("CONGESTION_ENTRANCE_DOWN","CONGESTION_ACTION"):
            nxt="CE_DN";reason="EXHAUST_REFRESH_TO_CE"
        elif rdir==1 and hd==1 and pl_push(h1,idx,1):
            nxt="TR_UP";reason="EXHAUST_FAILED_TREND_RESUME"
        elif rdir==-1 and hd==-1:
            nxt="REV_DN";reason="HTP_CONFIRMED_REVERSAL"
        else:nxt="EX_UP";reason="EXHAUST_WAIT"

    elif prev=="EX_DN":
        if raw in ("CONGESTION_ENTRANCE_UP","CONGESTION_ACTION"):
            nxt="CE_UP";reason="EXHAUST_REFRESH_TO_CE"
        elif rdir==-1 and hd==-1 and pl_push(h1,idx,-1):
            nxt="TR_DN";reason="EXHAUST_FAILED_TREND_RESUME"
        elif rdir==1 and hd==1:
            nxt="REV_UP";reason="HTP_CONFIRMED_REVERSAL"
        else:nxt="EX_DN";reason="EXHAUST_WAIT"

    elif prev in ("CE_UP","CE_DN"):
        if strong:
            nxt="CA";reason="STRONG_BLOCK_TO_CA"
        elif rdir==1 and hd==1:
            nxt="REV_UP";reason="WEAK_BLOCK_REV_UP"
        elif rdir==-1 and hd==-1:
            nxt="REV_DN";reason="WEAK_BLOCK_REV_DN"
        else:
            nxt=prev;reason="CE_WAIT"

    elif prev=="CA":
        if exup:nxt="CX_UP";reason="6/1_DISAPPEAR+HTP_UP"
        elif exdn:nxt="CX_DN";reason="6/1_DISAPPEAR+HTP_DN"
        elif rdir==1 and hd==1:nxt="CX_UP";reason="CA_BREAK_UP"
        elif rdir==-1 and hd==-1:nxt="CX_DN";reason="CA_BREAK_DN"
        else:nxt="CA";reason="CA_HOLD"

    return nxt,{
      "raw":raw,"htp_raw":hr,"htp_dir":hd,
      "pl_up":pl_push(h1,idx,1),"pl_dn":pl_push(h1,idx,-1),
      "lose":lose,"mup":mup,"mdn":mdn,"strong":strong,
      "exit_up":exup,"exit_dn":exdn,"reason":reason
    }

def live_refresh_trigger(h1,idx,m5bars,point,d,start_q=0):
    static=static_dot(h1,idx)
    if static is None:return None
    touched=False;hi=-math.inf;lo=math.inf
    for q,b in enumerate(m5bars):
        hi=max(hi,b[2]);lo=min(lo,b[3])
        if q<start_q:continue
        live=X.live_dot_m5(h1,idx,b,hi,lo)
        if live is None:continue
        zl,zh=min(static,live),max(static,live)
        if b[3]<=zh and b[2]>=zl:touched=True
        if touched:
            if d>0 and b[4]>zh:return q
            if d<0 and b[4]<zl:return q
    return None

def boundary_hold_trigger(h1,idx,m5bars,d):
    bz=block_zone(h1,idx)
    if bz is None:return None
    lo,hi=bz;t=False
    for q,b in enumerate(m5bars):
        if d>0:
            if b[3]<=hi:t=True
            if t and b[4]>hi:return q
        else:
            if b[2]>=lo:t=True
            if t and b[4]<lo:return q
    return None

def entry_plan(prev,cur,obs,h1,h4,idx,hi,point,m5bars,mode):
    # Full-machine entries arise from state/transition, never standalone Exhaust.
    if cur=="TR_UP":
        q=live_refresh_trigger(h1,idx,m5bars,point,1)
        return (1,q,"TREND_REFRESH") if q is not None else None
    if cur=="TR_DN":
        q=live_refresh_trigger(h1,idx,m5bars,point,-1)
        return (-1,q,"TREND_REFRESH") if q is not None else None
    if cur=="CA" and prev in ("CE_UP","CE_DN","CA"):
        # Direction comes from which side of the block/open is being defended.
        bz=block_zone(h1,idx)
        if bz is None:return None
        op=m5bars[0][1]
        if op>=bz[1]:
            q=boundary_hold_trigger(h1,idx,m5bars,1)
            return (1,q,"CA_BLOCK_LONG") if q is not None else None
        if op<=bz[0]:
            q=boundary_hold_trigger(h1,idx,m5bars,-1)
            return (-1,q,"CA_DOTTED_SHORT") if q is not None else None
    if cur=="CX_UP" and prev=="CA":return (1,0,"CONGESTION_EXIT_UP")
    if cur=="CX_DN" and prev=="CA":return (-1,0,"CONGESTION_EXIT_DN")
    if cur=="REV_UP":return (1,0,"REVERSAL_UP")
    if cur=="REV_DN":return (-1,0,"REVERSAL_DN")
    return None

def strict_targets(cur,h1,h4,idx,hi,point,entry,d):
    if cur=="CA":
        z=E.zones(h1,idx,point,entry)
    else:
        z=E.zones(h4,hi,point,entry)
    t=z["near_res"] if d>0 else z["near_sup"]
    ext=z["far_res_high"] if d>0 else z["far_sup_low"]
    if t is not None and ((d>0 and t<=entry+point) or (d<0 and t>=entry-point)):t=None
    if ext is not None and ((d>0 and ext<=entry+point) or (d<0 and ext>=entry-point)):ext=None
    return t,ext

def proxy_targets(cur,h1,h4,idx,hi,point,entry,d):
    if cur=="CA":
        eb,et=envelope_proxy(h1,idx)
        t=et if d>0 else eb
        if t is not None and ((d>0 and t>entry+point) or (d<0 and t<entry-point)):
            return t,None
        return None,None
    return strict_targets(cur,h1,h4,idx,hi,point,entry,d)

def stop_for(h1,idx,point,entry,d):
    return E.stop_further_out(h1,idx,point,entry,d)

def add_unit(pos,entry,stop,time_):
    risk=abs(entry-stop)
    if risk<=0:return False
    pos["units"].append({"entry":entry,"risk":risk,"time":time_})
    return True

def portfolio_r(pos,exit_px):
    d=pos["d"]
    vals=[d*(exit_px-u["entry"])/u["risk"] for u in pos["units"]]
    return sum(vals)/len(vals) if vals else 0.0

def build_contexts(sym,h1,h4,m5,point):
    h1t=[x[0] for x in h1];h4t=[x[0] for x in h4];m5t=[x[0] for x in m5]
    contexts=[];states=[];sm="UNK"
    start=max(12,bisect.bisect_left(h1t,m5t[0] if m5t else 0))
    for idx in range(start,len(h1)):
        t=h1[idx][0];hi=hidx(h4t,t)
        if hi<10:continue
        ma=bisect.bisect_left(m5t,t)
        mb=bisect.bisect_left(m5t,h1[idx+1][0] if idx+1<len(h1) else t+3600)
        if mb<=ma:continue
        prev=sm;sm,obs=evolve(prev,h1,h4,idx,hi,point)
        contexts.append((idx,t,hi,ma,mb,prev,sm,obs))
        states.append({
          "SYMBOL":sym,"TIME":t,"STATE":sm,"PREV_STATE":prev,
          "RAW":obs["raw"],"HTP_RAW":obs["htp_raw"],"HTP_DIR":obs["htp_dir"],
          "PL_PUSH_UP":int(obs["pl_up"]),"PL_PUSH_DN":int(obs["pl_dn"]),
          "LOSING_PUSH":int(obs["lose"]),"MATURE_UP":int(obs["mup"]),"MATURE_DN":int(obs["mdn"]),
          "BLOCK_STRONG":int(obs["strong"]),"EXIT_UP":int(obs["exit_up"]),"EXIT_DN":int(obs["exit_dn"]),
          "REASON":obs["reason"]
        })
    return contexts,states


def simulate_variant(sym,h1,h4,m5,point,mode,flow_n,pyr_cap,contexts):
    trades=[];pos=None;sm="UNK"
    for idx,t,hi,ma,mb,prev,sm,obs in contexts:
        m5bars=m5[ma:mb]

        # State transition can close/invalidate an existing trade.
        if pos is not None:
            d=pos["d"]
            wrong=(
              (d>0 and sm in ("REV_DN","TR_DN","CX_DN")) or
              (d<0 and sm in ("REV_UP","TR_UP","CX_UP"))
            )
            streak=X.flow_streak_against(h1,idx,d)
            if wrong or streak>=flow_n:
                ex=X.exec_exit_at_market(m5bars[0],point,d,use_open=True)
                rr=portfolio_r(pos,ex)
                trades.append({
                  "SYMBOL":sym,"MODE":mode,"FLOW_N":flow_n,"PYR_CAP":pyr_cap,
                  "ENTRY_STATE":pos["entry_state"],"EXIT_STATE":sm,"SIDE":"LONG" if d>0 else "SHORT",
                  "SETUP_TIME":pos["setup_time"],"ENTRY_TIME":pos["units"][0]["time"],"EXIT_TIME":t,
                  "UNITS":len(pos["units"]),"ENTRY0":f"{pos['units'][0]['entry']:.10f}","STOP0":f"{pos['stop0']:.10f}",
                  "EXIT":f"{ex:.10f}","OUTCOME":"STATE_EXIT" if wrong else "FLOW_EXIT",
                  "R":f"{rr:.8f}","M5_BARS":pos["bars"],"TRAIL_UPDATES":pos["trails"],
                  "PYRAMIDS":max(0,len(pos["units"])-1),"DETAIL":pos["detail"]
                })
                pos=None
            else:
                cand=stop_for(h1,idx,point,m5bars[0][1],d)
                if cand is not None:
                    if d>0 and cand>pos["stop"]+point and cand<m5bars[0][1]:
                        pos["stop"]=cand;pos["trails"]+=1
                    elif d<0 and cand<pos["stop"]-point and cand>m5bars[0][1]:
                        pos["stop"]=cand;pos["trails"]+=1

                if pos is not None and max(0,len(pos["units"])-1)<pyr_cap:
                    trend_ok=(d>0 and sm=="TR_UP" and obs["htp_dir"]==1) or (d<0 and sm=="TR_DN" and obs["htp_dir"]==-1)
                    if trend_ok:
                        q=live_refresh_trigger(h1,idx,m5bars,point,d)
                        if q is not None:
                            ep=X.exec_entry(m5bars[q],point,d)
                            st=stop_for(h1,idx,point,ep,d)
                            if st is not None and ((d>0 and st<ep-point) or (d<0 and st>ep+point)):
                                add_unit(pos,ep,st,m5bars[q][0]+300)

        # Entry from full state machine.
        if pos is None:
            plan=entry_plan(prev,sm,obs,h1,h4,idx,hi,point,m5bars,mode)
            if plan is not None:
                d,q,why=plan
                ep=X.exec_open(m5bars[q],point,d) if q==0 and why.startswith(("CONGESTION_EXIT","REVERSAL")) else X.exec_entry(m5bars[q],point,d)
                st=stop_for(h1,idx,point,ep,d)
                tp,ext=(strict_targets(sm,h1,h4,idx,hi,point,ep,d) if mode=="STRICT" else proxy_targets(sm,h1,h4,idx,hi,point,ep,d))
                if st is not None and tp is not None and X.valid_geometry(ep,st,tp,d,point):
                    pos={"d":d,"entry_state":sm,"setup_time":t,"stop":st,"stop0":st,"tp":tp,"ext":ext,
                         "units":[],"trails":0,"bars":0,"detail":why}
                    add_unit(pos,ep,st,m5bars[q][0] if q==0 else m5bars[q][0]+300)

        # M5 lifecycle with common stop/target.
        if pos is not None:
            d=pos["d"]
            for b in m5bars:
                if b[0]<pos["units"][0]["time"]:continue
                pos["bars"]+=1
                hit=X.hit_levels(b,point,d,pos["stop"],pos["tp"])
                if not hit:continue
                reason,level=hit
                if reason=="AMBIGUOUS":
                    ex=X.exec_exit_at_market(b,point,d)
                    rr=portfolio_r(pos,ex);oc="AMBIGUOUS_EXIT"
                elif reason=="TP" and pos["ext"] is not None and X.should_extend(h4,hi,d,pos["tp"],pos["ext"]):
                    pos["tp"]=pos["ext"];pos["ext"]=None
                    continue
                else:
                    ex=level;rr=portfolio_r(pos,ex);oc=reason
                trades.append({
                  "SYMBOL":sym,"MODE":mode,"FLOW_N":flow_n,"PYR_CAP":pyr_cap,
                  "ENTRY_STATE":pos["entry_state"],"EXIT_STATE":sm,"SIDE":"LONG" if d>0 else "SHORT",
                  "SETUP_TIME":pos["setup_time"],"ENTRY_TIME":pos["units"][0]["time"],"EXIT_TIME":b[0]+300,
                  "UNITS":len(pos["units"]),"ENTRY0":f"{pos['units'][0]['entry']:.10f}","STOP0":f"{pos['stop0']:.10f}",
                  "EXIT":f"{ex:.10f}","OUTCOME":oc,"R":f"{rr:.8f}","M5_BARS":pos["bars"],
                  "TRAIL_UPDATES":pos["trails"],"PYRAMIDS":max(0,len(pos["units"])-1),"DETAIL":pos["detail"]
                })
                pos=None;break

    if pos is not None and m5:
        b=m5[-1];d=pos["d"];ex=X.exec_exit_at_market(b,point,d);rr=portfolio_r(pos,ex)
        trades.append({
          "SYMBOL":sym,"MODE":mode,"FLOW_N":flow_n,"PYR_CAP":pyr_cap,
          "ENTRY_STATE":pos["entry_state"],"EXIT_STATE":sm,"SIDE":"LONG" if d>0 else "SHORT",
          "SETUP_TIME":pos["setup_time"],"ENTRY_TIME":pos["units"][0]["time"],"EXIT_TIME":b[0]+300,
          "UNITS":len(pos["units"]),"ENTRY0":f"{pos['units'][0]['entry']:.10f}","STOP0":f"{pos['stop0']:.10f}",
          "EXIT":f"{ex:.10f}","OUTCOME":"DATA_END","R":f"{rr:.8f}","M5_BARS":pos["bars"],
          "TRAIL_UPDATES":pos["trails"],"PYRAMIDS":max(0,len(pos["units"])-1),"DETAIL":pos["detail"]
        })
    return trades

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    trades=[];states=[];errs=[];skips=Counter();syms=0
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
            syms+=1;point=h1h["point"]
            contexts,ss=build_contexts(sym,h1,h4,m5,point)
            states.extend(ss)
            for mode in MODES:
                for fn in FLOW_NS:
                    for pc in PYR_CAPS:
                        trades.extend(simulate_variant(sym,h1,h4,m5,point,mode,fn,pc,contexts))
        except Exception as e:
            errs.append({"symbol":sym,"error":str(e)})

    trades.sort(key=lambda r:(r["MODE"],int(r["FLOW_N"]),int(r["PYR_CAP"]),int(r["ENTRY_TIME"]),r["SYMBOL"]))
    states.sort(key=lambda r:(int(r["TIME"]),r["SYMBOL"]))
    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D25.csv",TRADE_FIELDS,trades)
    write_csv(a.out/"D25S.csv",STATE_FIELDS,states)

    stats={}
    for mode in MODES:
      for fn in FLOW_NS:
       for pc in PYR_CAPS:
        rr=[x for x in trades if x["MODE"]==mode and int(x["FLOW_N"])==fn and int(x["PYR_CAP"])==pc]
        vals=[float(x["R"]) for x in rr]
        byst=Counter(x["ENTRY_STATE"] for x in rr)
        stats[f"{mode}:F{fn}:P{pc}"]={
          "n":len(rr),"sum_r":sum(vals),
          "mean_r":sum(vals)/len(vals) if vals else None,
          "median_r":statistics.median(vals) if vals else None,
          "positive_rate":sum(v>0 for v in vals)/len(vals) if vals else None,
          "pyramided":sum(int(x["PYRAMIDS"])>0 for x in rr),
          "entry_states":dict(byst),
          "max_r":max(vals) if vals else None,"min_r":min(vals) if vals else None
        }

    trans=Counter((x["PREV_STATE"],x["STATE"]) for x in states)
    summary={
      "block":"D25","status":"PASS" if syms>0 and not errs else "FAIL",
      "symbols":syms,"trades":len(trades),"state_rows":len(states),"errors":len(errs),"skips":dict(skips),
      "stats":stats,
      "state_transitions":{f"{a}->{b}":n for (a,b),n in sorted(trans.items())},
      "contract":{
        "continuous_state_machine":True,
        "exhaust_standalone_entry":False,
        "factory02_lifecycle_used":False,
        "further_out":"5/2+5/9 only",
        "live_pldot_refresh_entry_and_pyramid":True,
        "pyramid_caps":[0,1,2],"flow_variants":[1,2,3],
        "modes":["STRICT","PROXY"],
        "selection_or_optimization":False
      }
    }
    (a.out/"D25.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.out/"D25_ERR.json").write_text(json.dumps(errs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("D25",summary["status"],"symbols",syms,"trades",len(trades),"states",len(states),"errors",len(errs),"skips",dict(skips))
    for k,v in stats.items():
        print(k,"N",v["n"],"MEAN_R",f"{v['mean_r']:.8f}" if v["mean_r"] is not None else "NA","PYR",v["pyramided"])
    if errs:raise SystemExit(2)

if __name__=="__main__":
    main()
