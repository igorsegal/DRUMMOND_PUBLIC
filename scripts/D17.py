#!/usr/bin/env python3
import argparse,bisect,csv,json,math
from collections import Counter
from pathlib import Path

from drummond_replay01 import read_xfbar

LINE_NAMES=[
 "L51_UP","L51_DOWN","L52_UP","L52_DOWN","L53_UP","L53_DOWN",
 "L59_UP","L59_DOWN","L11_FROM_LOW","L11_FROM_HIGH",
 "L61_UP","L65_DOWN","L61_DOWN","L65_UP","L67_UP","L67_DOWN","L66_UP","L66_DOWN"
]

FIELDS=[
 "SYMBOL","SIDE","SIGNAL_ID","ENTRY_TIME","OUTCOME","LEVEL_R",
 "ENTRY_REFERENCE","INITIAL_SL","INITIAL_RISK",
 "H1_STATIC_PLDOT","H1_LIVE_OPEN","H1_REFRESH_AT_OPEN","H1_PLDOT_SIDE_R","H1_LIVE_SIDE_R",
 "H1_DOT_DIR","H1_DOT_DISTANCE_MODE","H1_DOT_IN_RANGE","H1_MCLINE",
 "H1_STATE","H4_STATE","H4_DOT_DIR","HTP_ALIGNED",
 "SUPPORT_LINES","RESIST_LINES","SUPPORT_CLUSTER","RESIST_CLUSTER",
 *LINE_NAMES,
 "ENV_EB","ENV_ET","ENV_POS",
 "NEAR_SUPPORT_LOW","NEAR_SUPPORT_HIGH","NEAR_RESIST_LOW","NEAR_RESIST_HIGH",
 "FAR_SUPPORT_LOW","FAR_SUPPORT_HIGH",
 "BLOCK_LOW","BLOCK_HIGH","BLOCK_REL","BLOCK_STRONG",
 "DOTS_FWD_LOW","DOTS_FWD_HIGH",
 "POWER_UP","POWER_DOWN","EXHAUST_UP","EXHAUST_DOWN",
 "DOTTED_UP","DOTTED_DOWN","PRIMARY_SIGNAL",
 "LIVE_PREV_N","LIVE_PATH_STATUS","LIVE_PREV_STATIC",
 "LIVE_PREV_START","LIVE_PREV_END","LIVE_PREV_MIN","LIVE_PREV_MAX",
 "LIVE_PREV_PUSH","LIVE_PREV_CROSS_STATIC","LIVE_PREV_REFRESH_TOUCH",
 "LIVE_PREV_RANGE_R","LIVE_ENDPOINT_ERROR_POINTS",
 "CLOSED_51_STATUS","CLOSED_59_STATUS","JAWS_59_STATUS","ENV_STATUS"
]

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";")
        w.writeheader();w.writerows(rows)

def one(root,pattern,desc):
    hits=list(Path(root).rglob(pattern))
    if len(hits)!=1:
        raise RuntimeError(f"{desc}: expected 1 match for {pattern}, got {len(hits)}")
    return hits[0]

def typ(b):
    return (b[2]+b[3]+b[4])/3.0

def sgn(x,eps=0.0):
    return 1 if x>eps else -1 if x<-eps else 0

def txtdir(d):
    return "UP" if d>0 else "DOWN" if d<0 else "NONE"

def static_dot(bars,idx):
    if idx<4 or idx>=len(bars): return None
    return (typ(bars[idx-1])+typ(bars[idx-2])+typ(bars[idx-3]))/3.0

def dot_dir(bars,idx,point):
    a=static_dot(bars,idx);b=static_dot(bars,idx-1)
    if a is None or b is None:return 0
    return sgn(a-b,point*.1)

def dot_dist(bars,idx):
    a=static_dot(bars,idx);b=static_dot(bars,idx-1)
    return None if a is None or b is None else abs(a-b)

def distance_mode(bars,idx,point):
    d0=dot_dist(bars,idx);d1=dot_dist(bars,idx-1)
    if d0 is None or d1 is None:return "UNKNOWN"
    if d0>d1+point*.1:return "EXPANDING"
    if d0<d1-point*.1:return "CONTRACTING"
    return "FLAT"

def dot_in_prev_range(bars,idx):
    p=static_dot(bars,idx)
    if p is None or idx<1:return False
    b=bars[idx-1]
    return b[3]<=p<=b[2]

def mcline(bars,idx):
    p0=static_dot(bars,idx);p1=static_dot(bars,idx-1)
    return None if p0 is None or p1 is None else 2*p0-p1

def three_trend(bars,idx,point):
    if idx<7:return 0
    d=0
    for shift in (1,2,3):
        k=idx-shift
        dot=static_dot(bars,k)
        if dot is None:return 0
        x=sgn(bars[k][4]-dot,point*.1)
        if x==0:return 0
        if d==0:d=x
        elif d!=x:return 0
    return d

def state(bars,idx,point):
    now=three_trend(bars,idx,point)
    if now>0:return "TREND_RUN_UP"
    if now<0:return "TREND_RUN_DOWN"
    prev=three_trend(bars,idx-1,point)
    if idx<1:return "UNKNOWN"
    d1=static_dot(bars,idx-1)
    if d1 is None:return "UNKNOWN"
    c1=bars[idx-1][4]
    if prev>0 and c1<d1:return "CONGESTION_ENTRANCE_DOWN"
    if prev<0 and c1>d1:return "CONGESTION_ENTRANCE_UP"
    return "CONGESTION_ACTION"

def pl_push(bars,idx,direction):
    p0=static_dot(bars,idx);p1=static_dot(bars,idx-1);p2=static_dot(bars,idx-2)
    if None in (p0,p1,p2):return False
    return (p0>p1>p2) if direction>0 else (p0<p1<p2)

def losing_push(bars,idx,point):
    return distance_mode(bars,idx,point)=="CONTRACTING" or dot_in_prev_range(bars,idx)

def project12(p1,p2):
    return 2*p1-p2

def halfproj(barpoint,dot):
    return 2*dot-barpoint

def line_features(bars,idx,point):
    out={k:0 for k in LINE_NAMES}
    vals={}
    if idx<7:return out,vals,0,0
    b1,b2=bars[idx-1],bars[idx-2]
    h1,l1,c1=b1[2],b1[3],b1[4]
    h2,l2=b2[2],b2[3]
    pl0=static_dot(bars,idx);pl1=static_dot(bars,idx-1)
    one=typ(b1)
    def add(name,v):
        out[name]=1;vals[name]=v
    x=project12(h1,h2)
    if h1<h2 and x<c1:add("L51_UP",x)
    x=project12(l1,l2)
    if l1>l2 and x>c1:add("L51_DOWN",x)
    if l1<l2:add("L52_UP",project12(l1,l2))
    if h1>h2:add("L52_DOWN",project12(h1,h2))
    x=project12(l1,l2)
    if l1>l2 and x<c1:add("L53_UP",x)
    x=project12(h1,h2)
    if h1<h2 and x>c1:add("L53_DOWN",x)
    add("L59_UP",project12(l1,h2))
    add("L59_DOWN",project12(h1,l2))
    add("L11_FROM_LOW",halfproj(l1,one))
    add("L11_FROM_HIGH",halfproj(h1,one))
    if pl0 is not None:
        x=halfproj(h1,pl0)
        if x<c1:add("L61_UP",x)
        else:add("L65_DOWN",x)
        x=halfproj(l1,pl0)
        if x>c1:add("L61_DOWN",x)
        else:add("L65_UP",x)
        if pl0<l1:add("L67_UP",halfproj(l1,pl0))
        if pl0>h1:add("L67_DOWN",halfproj(h1,pl0))
    if pl1 is not None and l1<=pl1<=h1:
        add("L66_UP",3*l1-2*pl1)
        add("L66_DOWN",3*h1-2*pl1)
    support=sum(out[x] for x in ["L51_UP","L52_UP","L53_UP","L59_UP","L11_FROM_LOW","L61_UP","L65_UP","L67_UP","L66_UP"])
    resist=sum(out[x] for x in ["L51_DOWN","L52_DOWN","L53_DOWN","L59_DOWN","L11_FROM_HIGH","L65_DOWN","L61_DOWN","L67_DOWN","L66_DOWN"])
    return out,vals,support,resist

def envelope_proxy(bars,idx):
    if idx<7:return None,None
    lo=hi=0.0
    for k in range(3):
        b=bars[idx-k-1];dot=typ(b)
        a=halfproj(b[3],dot);c=halfproj(b[2],dot)
        lo+=min(a,c);hi+=max(a,c)
    return lo/3.0,hi/3.0

def env_pos(bars,idx):
    eb,et=envelope_proxy(bars,idx)
    pl=static_dot(bars,idx)
    if eb is None or pl is None:return "UNKNOWN"
    px=bars[idx-1][4]
    if px>et:return "ABOVE_ET"
    if px>=pl:return "PL_TO_ET"
    if px>=eb:return "EB_TO_PL"
    return "BELOW_EB"

def energy(bars,idx,vals):
    eb,et=envelope_proxy(bars,idx);pl=static_dot(bars,idx)
    pos=env_pos(bars,idx)
    z={"ns":None,"nr":None,"fs":None}
    if eb is None or pl is None:return z
    if pos=="ABOVE_ET":
        z["ns"]=(min(et,pl),max(et,pl))
        rr=[vals[x] for x in ("L11_FROM_HIGH","L52_DOWN","L59_DOWN") if x in vals]
        if rr:z["nr"]=(min(rr),max(rr))
    elif pos=="PL_TO_ET":
        z["ns"]=(min(pl,eb),max(pl,eb));z["nr"]=(et,et)
    elif pos=="EB_TO_PL":
        z["ns"]=(eb,eb);z["nr"]=(min(pl,et),max(pl,et))
    elif pos=="BELOW_EB":
        ss=[vals[x] for x in ("L52_UP","L59_UP") if x in vals]
        if ss:z["fs"]=(min(ss),max(ss))
        z["nr"]=(min(eb,pl),max(eb,pl))
    return z

def live_open(bars,idx):
    if idx<3:return None
    o=bars[idx][1]
    return (o+typ(bars[idx-1])+typ(bars[idx-2]))/3.0

def live_prev_path(h1,idx,m5,m5t,point,risk):
    # Reconstruct the H1 that closed exactly at current event time.
    if idx<5:return {"n":0,"status":"NONE"}
    start=h1[idx-1][0];end=h1[idx][0]
    a=bisect.bisect_left(m5t,start);b=bisect.bisect_left(m5t,end)
    bars=[x for x in m5[a:b] if start<=x[0]<end]
    if not bars:return {"n":0,"status":"NONE"}
    static_prev=static_dot(h1,idx-1)
    t1=typ(h1[idx-2]);t2=typ(h1[idx-3])
    hi=-math.inf;lo=math.inf;live=[];refresh=False
    for x in bars:
        hi=max(hi,x[2]);lo=min(lo,x[3]);px=x[4]
        cur=(hi+lo+px)/3.0
        lp=(cur+t1+t2)/3.0
        live.append(lp)
        if min(static_prev,lp)<=px<=max(static_prev,lp):refresh=True
    next_static=static_dot(h1,idx)
    err=abs(live[-1]-next_static)/point if point>0 and next_static is not None else None
    cross=min(live)<=static_prev<=max(live)
    push=txtdir(sgn(live[-1]-live[0],point*.1))
    return {
      "n":len(live),"status":"FULL12" if len(live)==12 else "PARTIAL",
      "static":static_prev,"start":live[0],"end":live[-1],"min":min(live),"max":max(live),
      "push":push,"cross":cross,"refresh":refresh,
      "range_r":(max(live)-min(live))/risk if risk>0 else None,"err":err
    }

def zone_text(z,which):
    if z is None:return ""
    return z[0] if which==0 else z[1]

def rel_zone(price,z,point):
    if z is None:return "NONE"
    if z[0]-point*.1<=price<=z[1]+point*.1:return "INSIDE"
    return "BELOW" if price<z[0] else "ABOVE"

def fmt(v,n=10):
    if v is None:return ""
    try:x=float(v)
    except (TypeError,ValueError):return ""
    if not math.isfinite(x):return ""
    return f"{x:.{n}f}"

def cluster(n):
    return "0" if n==0 else "1" if n==1 else "2+"

def primary_signal(h1,idx,h4,hidx,point,refresh,sup,res,dotted_up,dotted_dn,ex_up,ex_dn,blockstrong):
    d=three_trend(h1,idx,point);hd=three_trend(h4,hidx,point)
    if d>0 and refresh and hd>0:return "TREND_REFRESH_UP"
    if d<0 and refresh and hd<0:return "TREND_REFRESH_DOWN"
    st=state(h1,idx,point)
    if st=="CONGESTION_ENTRANCE_UP":return st
    if st=="CONGESTION_ENTRANCE_DOWN":return st
    if dotted_up:return "DOTTED_EVIDENCE_UP"
    if dotted_dn:return "DOTTED_EVIDENCE_DOWN"
    if ex_up:return "EXHAUSTION_UP"
    if ex_dn:return "EXHAUSTION_DOWN"
    if blockstrong:return "BLOCK_STRONG"
    return "NONE"

def process_event(sym,row,h1,h4,m5,h1t,h4t,m5t,point,digits):
    et=int(row["ENTRY_TIME"])
    j=bisect.bisect_left(h1t,et)
    if j>=len(h1t) or h1t[j]!=et or j<8:
        raise RuntimeError(f"{sym}: H1 causal index unavailable {et}")
    hi=bisect.bisect_right(h4t,et)-1
    if hi<8: raise RuntimeError(f"{sym}: H4 causal index unavailable {et}")

    side=1 if row["SIDE"]=="LONG" else -1
    entry=float(row["ENTRY_REFERENCE"]);sl=float(row["INITIAL_SL"])
    risk=abs(entry-sl)
    if risk<=point*.5:raise RuntimeError(f"{sym}: invalid risk {row['SIGNAL_ID']}")

    pl=static_dot(h1,j);lop=live_open(h1,j)
    refresh=(min(pl,lop)<=h1[j][1]<=max(pl,lop))
    lf,vals,sup,res=line_features(h1,j,point)
    eb,etp=envelope_proxy(h1,j);ep=env_pos(h1,j);ez=energy(h1,j,vals)
    blo,bhi=sorted((static_dot(h1,j-2),static_dot(h1,j-3)))
    f0=static_dot(h1,j);f1=static_dot(h1,j-1);dd=f0-f1
    flo,fhi=sorted((f0+2*dd,f0+3*dd))
    hpl=static_dot(h4,hi)
    blockstrong=(hpl is not None and blo-10*point<=hpl<=bhi+10*point and (sup+res)>0)

    st=state(h1,j,point);hst=state(h4,hi,point)
    hd=three_trend(h4,hi,point)
    h1d=three_trend(h1,j,point)
    aligned=h1d!=0 and h1d==hd
    losing=losing_push(h1,j,point)
    entrance=st.startswith("CONGESTION_ENTRANCE")
    dotted_up=(hd!=0 and res>=2 and losing and entrance)
    dotted_dn=(hd!=0 and sup>=2 and losing and entrance)
    px1=h1[j-1][4]
    atf=flo<=px1<=fhi
    ex_up=(atf or losing) and (hd!=1 or losing_push(h4,hi,point))
    ex_dn=(atf or losing) and (hd!=-1 or losing_push(h4,hi,point))
    p_up=(hd==1 and (pl_push(h1,j,1) or pl_push(h4,hi,1)))
    p_dn=(hd==-1 and (pl_push(h1,j,-1) or pl_push(h4,hi,-1)))
    ps=primary_signal(h1,j,h4,hi,point,refresh,sup,res,dotted_up,dotted_dn,ex_up,ex_dn,blockstrong)

    lp=live_prev_path(h1,j,m5,m5t,point,risk)
    side_pl=(pl-entry)*side/risk
    side_live=(lop-entry)*side/risk
    blockrel=rel_zone(entry,(blo,bhi),point)

    out={
      "SYMBOL":sym,"SIDE":row["SIDE"],"SIGNAL_ID":row["SIGNAL_ID"],"ENTRY_TIME":et,
      "OUTCOME":row["OUTCOME"],"LEVEL_R":row["LEVEL_R"],
      "ENTRY_REFERENCE":fmt(entry,digits),"INITIAL_SL":fmt(sl,digits),"INITIAL_RISK":fmt(risk,digits),
      "H1_STATIC_PLDOT":fmt(pl,digits),"H1_LIVE_OPEN":fmt(lop,digits),
      "H1_REFRESH_AT_OPEN":"Y" if refresh else "N",
      "H1_PLDOT_SIDE_R":fmt(side_pl,8),"H1_LIVE_SIDE_R":fmt(side_live,8),
      "H1_DOT_DIR":txtdir(dot_dir(h1,j,point)),"H1_DOT_DISTANCE_MODE":distance_mode(h1,j,point),
      "H1_DOT_IN_RANGE":"Y" if dot_in_prev_range(h1,j) else "N","H1_MCLINE":fmt(mcline(h1,j),digits),
      "H1_STATE":st,"H4_STATE":hst,"H4_DOT_DIR":txtdir(dot_dir(h4,hi,point)),
      "HTP_ALIGNED":"Y" if aligned else "N",
      "SUPPORT_LINES":sup,"RESIST_LINES":res,"SUPPORT_CLUSTER":cluster(sup),"RESIST_CLUSTER":cluster(res),
      "ENV_EB":fmt(eb,digits),"ENV_ET":fmt(etp,digits),"ENV_POS":ep,
      "NEAR_SUPPORT_LOW":fmt(zone_text(ez["ns"],0),digits),"NEAR_SUPPORT_HIGH":fmt(zone_text(ez["ns"],1),digits),
      "NEAR_RESIST_LOW":fmt(zone_text(ez["nr"],0),digits),"NEAR_RESIST_HIGH":fmt(zone_text(ez["nr"],1),digits),
      "FAR_SUPPORT_LOW":fmt(zone_text(ez["fs"],0),digits),"FAR_SUPPORT_HIGH":fmt(zone_text(ez["fs"],1),digits),
      "BLOCK_LOW":fmt(blo,digits),"BLOCK_HIGH":fmt(bhi,digits),"BLOCK_REL":blockrel,
      "BLOCK_STRONG":"Y" if blockstrong else "N","DOTS_FWD_LOW":fmt(flo,digits),"DOTS_FWD_HIGH":fmt(fhi,digits),
      "POWER_UP":"Y" if p_up else "N","POWER_DOWN":"Y" if p_dn else "N",
      "EXHAUST_UP":"Y" if ex_up else "N","EXHAUST_DOWN":"Y" if ex_dn else "N",
      "DOTTED_UP":"Y" if dotted_up else "N","DOTTED_DOWN":"Y" if dotted_dn else "N",
      "PRIMARY_SIGNAL":ps,
      "LIVE_PREV_N":lp.get("n",0),"LIVE_PATH_STATUS":lp.get("status","NONE"),
      "LIVE_PREV_STATIC":fmt(lp.get("static"),digits),"LIVE_PREV_START":fmt(lp.get("start"),digits),
      "LIVE_PREV_END":fmt(lp.get("end"),digits),"LIVE_PREV_MIN":fmt(lp.get("min"),digits),
      "LIVE_PREV_MAX":fmt(lp.get("max"),digits),"LIVE_PREV_PUSH":lp.get("push","NONE"),
      "LIVE_PREV_CROSS_STATIC":"Y" if lp.get("cross") else "N",
      "LIVE_PREV_REFRESH_TOUCH":"Y" if lp.get("refresh") else "N",
      "LIVE_PREV_RANGE_R":fmt(lp.get("range_r"),8),"LIVE_ENDPOINT_ERROR_POINTS":fmt(lp.get("err"),4),
      "CLOSED_51_STATUS":"SOURCE_GAP","CLOSED_59_STATUS":"SOURCE_GAP","JAWS_59_STATUS":"SOURCE_GAP",
      "ENV_STATUS":"RECOVERED_PROXY"
    }
    for n in LINE_NAMES:out[n]="Y" if lf[n] else "N"
    return out

def symbols(root):
    return sorted({p.name[:-len("_FACTORY02_LIFECYCLE.csv")] for p in Path(root).rglob("*_FACTORY02_LIFECYCLE.csv")},key=lambda x:(x.casefold(),x))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--short-root",type=Path,required=True)
    ap.add_argument("--long-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    syms=sorted(set(symbols(a.short_root))|set(symbols(a.long_root)),key=lambda x:(x.casefold(),x))
    rows=[];errors=[];counts=Counter()
    for sym in syms:
        try:
            h1p=one(a.data_root,f"{sym}_H1.bin",f"{sym} H1")
            h4p=one(a.data_root,f"{sym}_H4.bin",f"{sym} H4")
            m5p=one(a.data_root,f"{sym}_M5.bin",f"{sym} M5")
            h1h,h1=read_xfbar(h1p)
            h4h,h4=read_xfbar(h4p)
            m5h,m5=read_xfbar(m5p)
            h1t=[x[0] for x in h1];h4t=[x[0] for x in h4];m5t=[x[0] for x in m5]
            point=h1h["point"];digits=h1h["digits"]
            for root,side in ((a.short_root,"SHORT"),(a.long_root,"LONG")):
                hits=list(Path(root).rglob(f"{sym}_FACTORY02_LIFECYCLE.csv"))
                if not hits:continue
                if len(hits)!=1:raise RuntimeError(f"{sym}: duplicate lifecycle in {root}")
                for r in read_csv(hits[0]):
                    if r["SIDE"]!=side:raise RuntimeError(f"{sym}: side mismatch {side}")
                    if r["OUTCOME"] not in ("TP","SL") or not r.get("LEVEL_R"):continue
                    rows.append(process_event(sym,r,h1,h4,m5,h1t,h4t,m5t,point,digits))
                    counts[side]+=1
        except Exception as e:
            errors.append({"symbol":sym,"error":str(e)})
    rows.sort(key=lambda r:(int(r["ENTRY_TIME"]),r["SYMBOL"].casefold(),r["SIDE"],r["SIGNAL_ID"]))

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D17.csv",rows)
    (a.out/"D17_ERR.json").write_text(json.dumps(errors,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    live=Counter(r["LIVE_PATH_STATUS"] for r in rows)
    summary={
      "block":"D17","status":"PASS" if rows and not errors else "FAIL",
      "symbols":len(syms),"events":len(rows),"long":counts["LONG"],"short":counts["SHORT"],
      "live_path_status":dict(live),"errors":len(errors),
      "causality":{
        "features_cutoff":"ENTRY_TIME",
        "h1_live_path":"only M5 bars with previous_H1_open <= m5_time < ENTRY_TIME",
        "current_live_point":"H1 open price plus two prior H1 typicals",
        "future_m5_used":False
      },
      "source_gaps":["Closed 5/1","Closed 5/9","Jaws 5/9"],
      "envelope_status":"RECOVERED_PROXY",
      "trading_rule_changes":False
    }
    (a.out/"D17.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("D17",summary["status"],"events",len(rows),"LONG",counts["LONG"],"SHORT",counts["SHORT"],"errors",len(errors))
    if errors:raise SystemExit(2)

if __name__=="__main__":
    main()
