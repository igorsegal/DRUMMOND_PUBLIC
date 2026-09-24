#!/usr/bin/env python3
import argparse,bisect,csv,json,math,statistics
from collections import Counter,defaultdict
from pathlib import Path

from drummond_replay01 import read_xfbar
from D17 import (
    static_dot,dot_dir,line_features,envelope_proxy,state,pl_push,losing_push,typ
)

FAMILIES=("TR","CA","EX","CX","WB")
FLOW_NS=(1,2,3)
SUP_NAMES=("L51_UP","L52_UP","L53_UP","L59_UP","L11_FROM_LOW","L61_UP","L65_UP","L67_UP","L66_UP")
RES_NAMES=("L51_DOWN","L52_DOWN","L53_DOWN","L59_DOWN","L11_FROM_HIGH","L65_DOWN","L61_DOWN","L67_DOWN","L66_DOWN")

FIELDS=[
 "SYMBOL","FAMILY","FLOW_N","SIDE","SETUP_TIME","ENTRY_TIME","ENTRY",
 "STOP0","TARGET0","TARGET_EXT","OUTCOME","EXIT_TIME","EXIT","R",
 "M5_BARS","TRAIL_UPDATES","TARGET_EXTENDED","FLOW_EXIT_STREAK","DETAIL"
]

def write_csv(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";");w.writeheader();w.writerows(rows)

def one(root,pat,desc):
    hits=list(Path(root).rglob(pat))
    if len(hits)!=1:raise RuntimeError(f"{desc}: expected 1, got {len(hits)}")
    return hits[0]

def med3(vals):
    a=sorted(vals)
    return a[1]

def good_flow(bars,k,d):
    # Source-qualitative operationalization:
    # directional bar, range not smaller than median of prior 3,
    # close is nearer the directional extreme than the opposite extreme.
    if k<4 or k>=len(bars):return False
    b=bars[k];o,h,l,c=b[1],b[2],b[3],b[4]
    rg=h-l
    if rg<=0:return False
    prev=[bars[k-i][2]-bars[k-i][3] for i in (1,2,3)]
    if any(x<=0 for x in prev):return False
    large=rg>=med3(prev)
    if d>0:return c>o and (h-c)<=(c-l) and large
    return c<o and (c-l)<=(h-c) and large

def flow_streak_against(bars,idx,position_dir):
    # idx is current forming bar; evaluate closed bars idx-1 backwards.
    n=0
    for k in range(idx-1,max(-1,idx-4),-1):
        if good_flow(bars,k,-position_dir):n+=1
        else:break
    return n

def line_zones(bars,idx,point,price):
    lf,vals,sup,res=line_features(bars,idx,point)
    sv=[v for n,v in vals.items() if n in SUP_NAMES and v>0 and v<price]
    rv=[v for n,v in vals.items() if n in RES_NAMES and v>price]
    return {
      "near_sup":max(sv) if sv else None,
      "far_sup":min(sv) if sv else None,
      "near_res":min(rv) if rv else None,
      "far_res":max(rv) if rv else None,
      "lf":lf,"vals":vals,"sup_n":sup,"res_n":res
    }

def protective_stop(h1,idx,point,entry,d):
    z=line_zones(h1,idx,point,entry)
    if d>0 and z["far_sup"] is not None:return z["far_sup"]-point
    if d<0 and z["far_res"] is not None:return z["far_res"]+point
    return None

def htp_targets(h4,hi,point,entry,d):
    z=line_zones(h4,hi,point,entry)
    if d>0:return z["near_res"],z["far_res"]
    return z["near_sup"],z["far_sup"]

def block_zone(h1,idx):
    a=static_dot(h1,idx-2);b=static_dot(h1,idx-3)
    if a is None or b is None:return None
    return min(a,b),max(a,b)

def htp_index(h4t,t):
    return bisect.bisect_right(h4t,t)-1

def trend_dir_from_state(s):
    if s=="TREND_RUN_UP":return 1
    if s=="TREND_RUN_DOWN":return -1
    return 0

def live_dot_m5(h1,idx,m5bar,running_hi,running_lo):
    if idx<3:return None
    t1=typ(h1[idx-1]);t2=typ(h1[idx-2])
    cur=(running_hi+running_lo+m5bar[4])/3.0
    return (cur+t1+t2)/3.0

def spread_price(m5bar,point):
    return max(0,m5bar[6])*point

def exec_entry(m5bar,point,d):
    px=m5bar[4];sp=spread_price(m5bar,point)
    return px+sp if d>0 else px

def exec_open(m5bar,point,d):
    px=m5bar[1];sp=spread_price(m5bar,point)
    return px+sp if d>0 else px

def exec_exit_at_market(m5bar,point,d,use_open=False):
    px=m5bar[1] if use_open else m5bar[4]
    sp=spread_price(m5bar,point)
    return px if d>0 else px+sp

def hit_levels(m5bar,point,d,sl,tp):
    sp=spread_price(m5bar,point)
    o,h,l=m5bar[1],m5bar[2],m5bar[3]
    if d<0:o,h,l=o+sp,h+sp,l+sp
    if d>0:
        gap_sl=o<=sl;gap_tp=o>=tp
        hs=l<=sl;ht=h>=tp
    else:
        gap_sl=o>=sl;gap_tp=o<=tp
        hs=h>=sl;ht=l<=tp
    if gap_sl and gap_tp:return ("AMBIGUOUS",None)
    if gap_sl:return ("SL",sl)
    if gap_tp:return ("TP",tp)
    if hs and ht:return ("AMBIGUOUS",None)
    if hs:return ("SL",sl)
    if ht:return ("TP",tp)
    return None

def valid_geometry(entry,sl,tp,d,point):
    if None in (entry,sl,tp):return False
    if min(entry,sl,tp)<=0:return False
    if d>0:return sl<entry-point and tp>entry+point
    return sl>entry+point and tp<entry-point

def setup_at_open(family,h1,h4,idx,hi,point,open_px):
    st=state(h1,idx,point)
    hst=state(h4,hi,point)
    d=trend_dir_from_state(st)
    hd=trend_dir_from_state(hst)
    bz=block_zone(h1,idx)
    z=line_zones(h1,idx,point,open_px)
    hdot=static_dot(h4,hi)

    if family=="TR":
        if d==0 or hd!=d or not pl_push(h1,idx,d):return None
        return {"d":d,"mode":"M5_REFRESH","detail":"TREND_RUN+HTP+PLPUSH"}

    if family=="CA":
        if st!="CONGESTION_ACTION" or bz is None:return None
        if hd!=0:return None
        blo,bhi=bz
        if hdot is None or not (blo<=hdot<=bhi):return None
        if open_px>bhi and z["sup_n"]>0:
            return {"d":1,"mode":"M5_BLOCK_HOLD","zone":bz,"detail":"STRONG_BLOCK_SUPPORT"}
        if open_px<blo and z["res_n"]>0:
            return {"d":-1,"mode":"M5_BLOCK_HOLD","zone":bz,"detail":"STRONG_BLOCK_RESIST"}
        return None

    if family=="EX":
        if d==0:return None
        # HTP must not remain a clean strong trend in same direction, or must be losing push.
        if hd==d and not losing_push(h4,hi,point):return None
        far=z["far_res"] if d>0 else z["far_sup"]
        if far is None:return None
        return {"d":-d,"mode":"M5_EXHAUST_RETURN","far":far,"trend_d":d,"detail":"FURTHER_OUT+HTP_MATURE"}

    if family=="CX":
        if d==0 or hd!=d:return None
        prev=state(h1,idx-1,point)
        if prev not in ("CONGESTION_ACTION","CONGESTION_ENTRANCE_UP","CONGESTION_ENTRANCE_DOWN"):return None
        prevlf,_,_,_=line_features(h1,idx-1,point)
        curlf,_,_,_=line_features(h1,idx,point)
        disappeared=(prevlf["L61_DOWN"] and not curlf["L61_DOWN"]) if d>0 else (prevlf["L61_UP"] and not curlf["L61_UP"])
        if not disappeared:return None
        return {"d":d,"mode":"OPEN","detail":"CONGESTION_EXIT+6/1_DISAPPEAR"}

    if family=="WB":
        if hd==0 or bz is None:return None
        blo,bhi=bz
        if hdot is None:return None
        c1=h1[idx-1][4];c2=h1[idx-2][4]
        if hd>0 and hdot>bhi and c1>bhi and c2<=bhi:
            return {"d":1,"mode":"OPEN","detail":"WEAK_BLOCK_BREAK_UP"}
        if hd<0 and hdot<blo and c1<blo and c2>=blo:
            return {"d":-1,"mode":"OPEN","detail":"WEAK_BLOCK_BREAK_DOWN"}
    return None

def targets_for(family,h1,h4,idx,hi,point,entry,d):
    if family=="CA":
        eb,et=envelope_proxy(h1,idx)
        if eb is None:return None,None
        return (et,None) if d>0 else (eb,None)
    if family=="EX":
        pl=static_dot(h1,idx)
        ld=(h1[idx][1]+typ(h1[idx-1])+typ(h1[idx-2]))/3.0
        eb,et=envelope_proxy(h1,idx)
        if d>0:
            near=min(pl,ld)
            ext=et
        else:
            near=max(pl,ld)
            ext=eb
        if (d>0 and near<=entry) or (d<0 and near>=entry):
            near=ext;ext=None
        return near,ext
    return htp_targets(h4,hi,point,entry,d)

def should_extend(h4,hi,d,primary,extended):
    if extended is None:return False
    if d>0 and extended<=primary:return False
    if d<0 and extended>=primary:return False
    # Nearby can be passed when HTP flow remains favorable.
    return good_flow(h4,hi-1,d) if hi>=5 else False

def trigger_m5(setup,family,h1,idx,m5bars,point):
    d=setup["d"]
    if setup["mode"]=="OPEN":
        return 0,"OPEN"
    static=static_dot(h1,idx)
    touched=False
    for q,b in enumerate(m5bars):
        hi=max(x[2] for x in m5bars[:q+1]);lo=min(x[3] for x in m5bars[:q+1])
        live=live_dot_m5(h1,idx,b,hi,lo)
        if live is None:continue
        if setup["mode"]=="M5_REFRESH":
            zl,zh=min(static,live),max(static,live)
            if b[3]<=zh and b[2]>=zl:
                if touched:
                    if d>0 and b[4]>zh:return q,"REFRESH_RESUME"
                    if d<0 and b[4]<zl:return q,"REFRESH_RESUME"
                touched=True
        elif setup["mode"]=="M5_BLOCK_HOLD":
            zl,zh=setup["zone"]
            if d>0:
                if b[3]<=zh:touched=True
                if touched and q>0 and b[4]>zh:return q,"BLOCK_HOLD"
            else:
                if b[2]>=zl:touched=True
                if touched and q>0 and b[4]<zl:return q,"BLOCK_HOLD"
        elif setup["mode"]=="M5_EXHAUST_RETURN":
            far=setup["far"];td=setup["trend_d"]
            if td>0:
                if b[2]>=far:touched=True
                if touched and q>0 and b[4]<far:return q,"EXHAUST_RETURN"
            else:
                if b[3]<=far:touched=True
                if touched and q>0 and b[4]>far:return q,"EXHAUST_RETURN"
    return None,None

def record_trade(sym,family,flow_n,d,setup_time,entry_time,entry,sl0,tp0,tpext,
                 outcome,exit_time,exit_px,r,bars,trails,extended,streak,detail):
    return {
      "SYMBOL":sym,"FAMILY":family,"FLOW_N":flow_n,"SIDE":"LONG" if d>0 else "SHORT",
      "SETUP_TIME":setup_time,"ENTRY_TIME":entry_time,"ENTRY":f"{entry:.10f}",
      "STOP0":f"{sl0:.10f}","TARGET0":f"{tp0:.10f}",
      "TARGET_EXT":"" if tpext is None else f"{tpext:.10f}",
      "OUTCOME":outcome,"EXIT_TIME":exit_time,"EXIT":f"{exit_px:.10f}",
      "R":f"{r:.8f}","M5_BARS":bars,"TRAIL_UPDATES":trails,
      "TARGET_EXTENDED":"Y" if extended else "N","FLOW_EXIT_STREAK":streak,
      "DETAIL":detail
    }

def simulate(sym,h1,h4,m5,point,family,flow_n):
    h1t=[x[0] for x in h1];h4t=[x[0] for x in h4];m5t=[x[0] for x in m5]
    out=[];pos=None
    start=max(12,bisect.bisect_left(h1t,m5t[0] if m5t else 0))
    for idx in range(start,len(h1)):
        t=h1[idx][0]
        hi=htp_index(h4t,t)
        if hi<10:continue
        ma=bisect.bisect_left(m5t,t)
        mb=bisect.bisect_left(m5t,h1[idx+1][0] if idx+1<len(h1) else t+3600)
        m5bars=m5[ma:mb]
        if not m5bars:continue

        # H1-boundary management for an existing position.
        if pos is not None:
            d=pos["d"]
            streak=flow_streak_against(h1,idx,d)
            if streak>=flow_n:
                ex=exec_exit_at_market(m5bars[0],point,d,use_open=True)
                rr=d*(ex-pos["entry"])/pos["risk"]
                out.append(record_trade(sym,family,flow_n,d,pos["setup_time"],pos["entry_time"],
                    pos["entry"],pos["sl0"],pos["tp0"],pos["tpext"],"FLOW_EXIT",t,ex,rr,
                    pos["bars"],pos["trails"],pos["extended"],streak,pos["detail"]))
                pos=None
            else:
                cand=protective_stop(h1,idx,point,m5bars[0][1],d)
                if cand is not None:
                    if d>0 and cand>pos["sl"]+point and cand<m5bars[0][1]:
                        pos["sl"]=cand;pos["trails"]+=1
                    elif d<0 and cand<pos["sl"]-point and cand>m5bars[0][1]:
                        pos["sl"]=cand;pos["trails"]+=1

        # New setup at this H1 boundary.
        if pos is None:
            setup=setup_at_open(family,h1,h4,idx,hi,point,m5bars[0][1])
            if setup is not None:
                qi,why=trigger_m5(setup,family,h1,idx,m5bars,point)
                if qi is not None:
                    b=m5bars[qi];d=setup["d"]
                    entry=exec_open(b,point,d) if setup["mode"]=="OPEN" else exec_entry(b,point,d)
                    sl=protective_stop(h1,idx,point,entry,d)
                    tp,ext=targets_for(family,h1,h4,idx,hi,point,entry,d)
                    if valid_geometry(entry,sl,tp,d,point):
                        pos={"d":d,"entry":entry,"sl":sl,"sl0":sl,"tp":tp,"tp0":tp,"tpext":ext,
                             "risk":abs(entry-sl),"entry_time":b[0] if setup["mode"]=="OPEN" else b[0]+300,
                             "setup_time":t,"trails":0,"bars":0,"extended":False,
                             "detail":setup["detail"]+"|"+why,"start_q":qi}
        # Intrabar lifecycle.
        if pos is not None:
            d=pos["d"]
            startq=0
            if pos.get("setup_time")==t:
                startq=pos.pop("start_q",0)
                if pos["entry_time"]>m5bars[startq][0]:startq+=1
            for b in m5bars[startq:]:
                if b[0]<pos["entry_time"]:continue
                pos["bars"]+=1
                hit=hit_levels(b,point,d,pos["sl"],pos["tp"])
                if not hit:continue
                reason,level=hit
                if reason=="AMBIGUOUS":
                    ex=exec_exit_at_market(b,point,d)
                    rr=d*(ex-pos["entry"])/pos["risk"]
                    out.append(record_trade(sym,family,flow_n,d,pos["setup_time"],pos["entry_time"],
                        pos["entry"],pos["sl0"],pos["tp0"],pos["tpext"],"AMBIGUOUS_EXIT",b[0]+300,
                        ex,rr,pos["bars"],pos["trails"],pos["extended"],0,pos["detail"]))
                    pos=None;break
                if reason=="TP" and not pos["extended"] and should_extend(h4,hi,d,pos["tp"],pos["tpext"]):
                    pos["tp"]=pos["tpext"];pos["extended"]=True
                    continue
                ex=level
                rr=d*(ex-pos["entry"])/pos["risk"]
                outcome="TP_EXT" if reason=="TP" and pos["extended"] else reason
                out.append(record_trade(sym,family,flow_n,d,pos["setup_time"],pos["entry_time"],
                    pos["entry"],pos["sl0"],pos["tp0"],pos["tpext"],outcome,b[0]+300,ex,rr,
                    pos["bars"],pos["trails"],pos["extended"],0,pos["detail"]))
                pos=None;break

    if pos is not None and m5:
        b=m5[-1];d=pos["d"];ex=exec_exit_at_market(b,point,d)
        rr=d*(ex-pos["entry"])/pos["risk"]
        out.append(record_trade(sym,family,flow_n,d,pos["setup_time"],pos["entry_time"],
            pos["entry"],pos["sl0"],pos["tp0"],pos["tpext"],"DATA_END",b[0]+300,ex,rr,
            pos["bars"],pos["trails"],pos["extended"],0,pos["detail"]))
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    rows=[];errs=[];syms=0;skips=Counter()
    for h1p in sorted(a.data_root.rglob("*_H1.bin")):
        sym=h1p.name[:-7]
        try:
            h4hits=list(a.data_root.rglob(f"{sym}_H4.bin"))
            m5hits=list(a.data_root.rglob(f"{sym}_M5.bin"))
            if len(h4hits)==0:
                skips["SKIP_NO_H4"]+=1
                continue
            if len(m5hits)==0:
                skips["SKIP_NO_M5"]+=1
                continue
            if len(h4hits)!=1 or len(m5hits)!=1:
                raise RuntimeError(f"duplicate required TF: H4={len(h4hits)} M5={len(m5hits)}")
            h4p=h4hits[0]
            m5p=m5hits[0]
            h1h,h1=read_xfbar(h1p);h4h,h4=read_xfbar(h4p);m5h,m5=read_xfbar(m5p)
            if h1h["period_seconds"]!=3600 or h4h["period_seconds"]!=14400 or m5h["period_seconds"]!=300:
                raise RuntimeError("TF contract")
            point=h1h["point"]
            syms+=1
            for family in FAMILIES:
                for fn in FLOW_NS:
                    rows.extend(simulate(sym,h1,h4,m5,point,family,fn))
        except Exception as e:
            errs.append({"symbol":sym,"error":str(e)})
    rows.sort(key=lambda r:(r["FAMILY"],int(r["FLOW_N"]),int(r["ENTRY_TIME"]),r["SYMBOL"]))
    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D21.csv",FIELDS,rows)
    groups=defaultdict(list)
    for r in rows:groups[(r["FAMILY"],int(r["FLOW_N"]))].append(r)
    stats=[]
    for (fam,fn),rr in sorted(groups.items()):
        vals=[float(x["R"]) for x in rr]
        stats.append({
          "family":fam,"flow_n":fn,"n":len(rr),
          "mean_r":sum(vals)/len(vals) if vals else None,
          "median_r":statistics.median(vals) if vals else None,
          "positive_rate":sum(x>0 for x in vals)/len(vals) if vals else None,
          "outcomes":dict(Counter(x["OUTCOME"] for x in rr))
        })
    summary={
      "block":"D21","status":"PASS" if syms>0 and not errs else "FAIL",
      "symbols":syms,"trades":len(rows),"errors":len(errs),"skips":dict(skips),"stats":stats,
      "native_drummond":{
        "factory02_entries_used":False,"factory02_stops_used":False,
        "factory02_targets_used":False,"factory02_trailing_used":False,
        "setup_families":list(FAMILIES),"flow_variants":list(FLOW_NS),
        "pyramiding":"OFF_IN_D21_BASELINE",
        "next":"D22 adds Live PL Dot Refresh pyramiding caps 1 and 2"
      },
      "source_gap_as_gate":False,"oos_selection":False
    }
    (a.out/"D21.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.out/"D21_ERR.json").write_text(json.dumps(errs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("D21",summary["status"],"symbols",syms,"trades",len(rows),"errors",len(errs),"skips",dict(skips))
    for x in stats:
        print(x["family"],"F",x["flow_n"],"N",x["n"],"MEAN_R",f"{x['mean_r']:.8f}" if x["mean_r"] is not None else "NA")
    if errs:raise SystemExit(2)

if __name__=="__main__":
    main()
