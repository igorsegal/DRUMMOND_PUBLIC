#!/usr/bin/env python3
import argparse,bisect,csv,hashlib,json,math,struct
from collections import Counter
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
from datetime import datetime,timezone

HDR=struct.Struct("<8siiiidqqqi")
REC=struct.Struct("<qddddqiq")
MAGIC=b"XFBAR001"
SIDE_NONE,SIDE_LONG,SIDE_SHORT=0,1,-1
DIR_BOTH,DIR_SHORT,DIR_LONG=0,1,2
L51U,L51D,L52U,L52D,L59U,L59D=range(6)
SIGNAL_NAME="CONSERVATIVE_TREND_PLDOT_REFRESH_HTP_ALIGNED"

def norm(x,d):
    return float(Decimal(str(x)).quantize(Decimal(1).scaleb(-d),rounding=ROUND_HALF_UP))
def isot(ts): return datetime.fromtimestamp(ts,tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def side_text(s): return "LONG" if s==1 else "SHORT" if s==-1 else "NONE"

def read_xfbar(path):
    data=Path(path).read_bytes()
    if len(data)<HDR.size: raise ValueError(f"{path}: short header")
    magic,ver,rs,period,digits,point,n,first,last,slen=HDR.unpack_from(data,0)
    if magic!=MAGIC or ver!=1 or rs!=60: raise ValueError(f"{path}: bad XFBAR contract")
    off=HDR.size+slen
    if slen<=0 or off>len(data): raise ValueError(f"{path}: bad symbol length")
    symbol=data[HDR.size:off].decode("utf-8")
    if len(data)!=off+n*rs: raise ValueError(f"{path}: file size mismatch")
    bars=[]; prev=None
    for i in range(n):
        r=REC.unpack_from(data,off+i*rs)
        t,o,h,l,c,tv,sp,rv=r
        if prev is not None and t<=prev: raise ValueError(f"{path}: non-monotonic time")
        if not all(math.isfinite(v) for v in (o,h,l,c)): raise ValueError(f"{path}: non-finite OHLC")
        if h<max(o,c) or l>min(o,c): raise ValueError(f"{path}: bad OHLC envelope")
        bars.append(r); prev=t
    if bars and (bars[0][0]!=first or bars[-1][0]!=last): raise ValueError(f"{path}: header time mismatch")
    head={"path":str(path),"symbol":symbol,"version":ver,"record_size":rs,"period_seconds":period,
          "digits":digits,"point":point,"bar_count":n,"first_time":first,"last_time":last,
          "header_bytes":off,"file_bytes":len(data)}
    return head,bars

class S:
    def __init__(self,bars,cur,point,digits): self.b=bars; self.c=cur; self.point=point; self.digits=digits
    def n(self): return self.c+1
    def bar(self,shift): return self.b[self.c-shift]
    def typ(self,shift):
        b=self.bar(shift); h,l,c=b[2],b[3],b[4]
        return (h+l+c)/3.0 if h>0 and l>0 and c>0 else 0.0
    def dot(self,shift):
        if self.n()<shift+5:return 0.0
        a=[self.typ(shift+i) for i in (1,2,3)]
        return sum(a)/3.0 if min(a)>0 else 0.0
    def side(self,shift):
        d=self.dot(shift); c=self.bar(shift)[4]
        if d<=0 or c<=0:return 0
        e=self.point*0.1
        return 1 if c>d+e else -1 if c<d-e else 0
    def trend(self):
        z=0
        for sh in (1,2,3):
            q=self.side(sh)
            if q==0:return 0
            if z==0:z=q
            elif z!=q:return 0
        return z
    def refresh(self,d):
        dot=self.dot(1); b=self.bar(1)
        if dot<=0:return False
        return b[3]<=dot and b[4]>dot if d>0 else b[2]>=dot and b[4]<dot if d<0 else False
    def line(self,i):
        if self.n()<6:return None
        b1,b2=self.bar(1),self.bar(2)
        h1,h2,l1,l2,c1=b1[2],b2[2],b1[3],b2[3],b1[4]
        if i==L51U:
            if not h1<h2:return None
            x=2*h1-h2
            if not x<c1:return None
        elif i==L51D:
            if not l1>l2:return None
            x=2*l1-l2
            if not x>c1:return None
        elif i==L52U:
            if not l1<l2:return None
            x=2*l1-l2
        elif i==L52D:
            if not h1>h2:return None
            x=2*h1-h2
        elif i==L59U:x=2*l1-h2
        elif i==L59D:x=2*h1-l2
        else:return None
        return norm(x,self.digits) if x>0 else None

def target(s,side,entry):
    ids=(L51D,L52D,L59D) if side==SIDE_LONG else (L51U,L52U,L59U)
    vals=[]
    for i in ids:
        x=s.line(i)
        if x is not None and ((side==SIDE_LONG and x>entry) or (side==SIDE_SHORT and x<entry)): vals.append(x)
    if not vals:return None
    return norm(min(vals) if side==SIDE_LONG else max(vals),s.digits)

def stop(s,side,entry,buf):
    ids=(L51U,L52U,L59U) if side==SIDE_LONG else (L51D,L52D,L59D)
    vals=[]
    for i in ids:
        x=s.line(i)
        if x is not None and ((side==SIDE_LONG and x<entry) or (side==SIDE_SHORT and x>entry)): vals.append(x)
    if not vals:return None
    x=min(vals) if side==SIDE_LONG else max(vals)
    x += (-1 if side==SIDE_LONG else 1)*max(1,buf)*s.point
    return norm(x,s.digits)

def allowed(side,mode):
    return mode==DIR_BOTH or mode==DIR_SHORT and side==SIDE_SHORT or mode==DIR_LONG and side==SIDE_LONG

def evaluate(sym,ds,hs,bid,ask,decision_time,mode,rrmin,rrmax,buf):
    plan={"symbol":sym,"decision_time":0,"side":0,"trend":0,"htp":0,"dot":0.0,"entry":0.0,"stop":0.0,"target":0.0,"rr":0.0}
    g=0
    if ds.n()<20:return False,plan,"NO_DECISION_HISTORY",g
    g+=1
    if hs.n()<20:return False,plan,"NO_HTP_HISTORY",g
    g+=1
    tr=ds.trend()
    if tr==0:return False,plan,"NO_DECISION_TREND",g
    g+=1
    ht=hs.trend()
    if ht==0:return False,plan,"NO_HTP_TREND",g
    g+=1
    if ht!=tr:return False,plan,"HTP_DIRECTION_CONFLICT",g
    g+=1
    if not ds.refresh(tr):return False,plan,"NO_PLDOT_REFRESH",g
    g+=1
    entry=ask if tr>0 else bid
    if entry<=0:return False,plan,"NO_EXECUTION_QUOTE",g
    g+=1
    side=SIDE_LONG if tr>0 else SIDE_SHORT
    tp=target(hs,side,entry)
    if tp is None:return False,plan,"NO_HTP_TARGET",g
    g+=1
    sl=stop(ds,side,entry,buf)
    if sl is None:return False,plan,"NO_STRUCTURAL_PROTECTION",g
    g+=1
    if side==SIDE_LONG and not(sl<entry<tp):return False,plan,"INVALID_LONG_GEOMETRY",g
    if side==SIDE_SHORT and not(tp<entry<sl):return False,plan,"INVALID_SHORT_GEOMETRY",g
    g+=1
    if not allowed(side,mode):
        return False,plan,"DIRECTION_GATE_LONG_BLOCKED" if side==SIDE_LONG else "DIRECTION_GATE_SHORT_BLOCKED",g
    g+=1
    risk,reward=abs(entry-sl),abs(tp-entry)
    rr=reward/risk if risk>0 else -1
    if rr<0 or not math.isfinite(rr):return False,plan,"RR_GATE_INVALID",g
    if rr<rrmin:return False,plan,"RR_GATE_BELOW_MIN",g
    if rrmax>0 and rr>=rrmax:return False,plan,"RR_GATE_AT_OR_ABOVE_MAX",g
    g+=1
    plan.update(decision_time=decision_time,side=side,trend=tr,htp=ht,dot=ds.dot(1),
                entry=norm(entry,ds.digits),stop=sl,target=tp,rr=rr)
    return True,plan,"FULL_PASS",g

def align(parent,m5,factor,point):
    idx={b[0]:i for i,b in enumerate(m5)}; checked=matched=skipped_gap=0; tol=max(point*0.1,1e-9)
    for p in parent:
        i=idx.get(p[0])
        if i is None or i+factor>len(m5):continue
        g=m5[i:i+factor]
        if any(g[k][0]!=p[0]+k*300 for k in range(factor)):
            skipped_gap+=1
            continue
        a=(g[0][1],max(x[2] for x in g),min(x[3] for x in g),g[-1][4])
        e=(p[1],p[2],p[3],p[4]); checked+=1
        if all(abs(x-y)<=tol for x,y in zip(a,e)):matched+=1
    return {"checked":checked,"matched":matched,"mismatched":checked-matched,"skipped_market_gaps":skipped_gap,"match_ratio":matched/checked if checked else 0.0}

def outcome(p,start,m5,point,end_time=0):
    last_i=start-1
    for i in range(start,len(m5)):
        b=m5[i]
        if end_time>0 and b[0]>end_time: break
        last_i=i
        sp=max(0,b[6])*point
        lo,hi=(b[3],b[2]) if p["side"]==SIDE_LONG else (b[3]+sp,b[2]+sp)
        hs=lo<=p["stop"]<=hi; ht=lo<=p["target"]<=hi
        if hs and ht:return "AMBIGUOUS_SAME_M5",b[0],i-start
        if hs:return "SL",b[0],i-start
        if ht:return "TP",b[0],i-start
    terminal_time=m5[last_i][0] if last_i>=start else (end_time if end_time>0 else m5[-1][0])
    bars_seen=max(0,last_i-start+1)
    return "OPEN_AT_DATA_END",terminal_time,bars_seen

def writecsv(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";");w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--fixture",type=Path,default=Path("data/fixtures/XAUUSD"))
    ap.add_argument("--symbol",default="XAUUSD")
    ap.add_argument("--out",type=Path,default=Path("results/latest/replay01"))
    ap.add_argument("--direction",choices=("BOTH","SHORT_ONLY","LONG_ONLY"),default="SHORT_ONLY")
    ap.add_argument("--rr-min",type=float,default=.75);ap.add_argument("--rr-max",type=float,default=1.75)
    ap.add_argument("--buffer-points",type=int,default=1)
    ap.add_argument("--quote-source",choices=("m5","h1"),default="m5",
                    help="m5 keeps Replay 01 execution clock; h1 matches MT4 Open prices signal testing")
    ap.add_argument("--fixed-spread-points",type=int,default=None,
                    help="Use a fixed spread for MT4 equivalence instead of the historical M5 spread")
    ap.add_argument("--start-time",type=int,default=0,
                    help="Optional inclusive Unix timestamp lower bound for reproducible replay slices")
    ap.add_argument("--end-time",type=int,default=0,
                    help="Optional inclusive Unix timestamp upper bound for reproducible replay slices")
    a=ap.parse_args()
    mode={"BOTH":DIR_BOTH,"SHORT_ONLY":DIR_SHORT,"LONG_ONLY":DIR_LONG}[a.direction]
    sym=a.symbol
    hm,m5=read_xfbar(a.fixture/f"{sym}_M5.bin"); h1h,h1=read_xfbar(a.fixture/f"{sym}_H1.bin"); h4h,h4=read_xfbar(a.fixture/f"{sym}_H4.bin")
    for h in (hm,h1h,h4h):
        if h["symbol"]!=sym:raise ValueError("symbol mismatch")
    if (hm["period_seconds"],h1h["period_seconds"],h4h["period_seconds"])!=(300,3600,14400):raise ValueError("timeframe mismatch")
    if not(hm["digits"]==h1h["digits"]==h4h["digits"]):raise ValueError("digits mismatch")
    if not(abs(hm["point"]-h1h["point"])<1e-15 and abs(h1h["point"]-h4h["point"])<1e-15):raise ValueError("point mismatch")
    m5idx={b[0]:i for i,b in enumerate(m5)}; h4t=[b[0] for b in h4]
    al1,al4=align(h1,m5,12,hm["point"]),align(h4,m5,48,hm["point"])
    audit=[];signals=[];outs=[];reasons=Counter();future=missing=0
    start=max(hm["first_time"],h1[min(20,len(h1)-1)][0],h4[min(20,len(h4)-1)][0])
    end=min(hm["last_time"],h1h["last_time"],h4h["last_time"])
    if a.start_time>0: start=max(start,a.start_time)
    if a.end_time>0: end=min(end,a.end_time)
    if end<start: raise ValueError(f"invalid replay slice: start={start} end={end}")
    for j in range(1,len(h1)):
        et=h1[j][0]
        if et<start or et>end:continue
        mi=m5idx.get(et)
        if a.quote_source=="m5" and mi is None:
            missing+=1
            continue
        hc=bisect.bisect_right(h4t,et)-1
        if hc<0:continue
        ds,hs=S(h1,j,h1h["point"],h1h["digits"]),S(h4,hc,h4h["point"],h4h["digits"])
        q=m5[mi] if mi is not None else None
        if a.fixed_spread_points is None:
            used_spread=max(0,q[6]) if q is not None else 0
        else:
            used_spread=max(0,a.fixed_spread_points)
        bid=q[1] if a.quote_source=="m5" else h1[j][1]
        ask=bid+used_spread*hm["point"];dt=h1[j-1][0]
        if ds.bar(1)[0]>=et or (hs.n()>=2 and hs.bar(1)[0]>=et):future+=1
        if a.quote_source=="m5" and (q is None or q[0]!=et):future+=1
        full,p,r,g=evaluate(sym,ds,hs,bid,ask,dt,mode,a.rr_min,a.rr_max,a.buffer_points);reasons[r]+=1
        sid="";status="NO_TRADE"
        if full:
            sid=f"{sym}_{p['decision_time']}_{'L' if p['side']==1 else 'S'}";status="QUEUED"
            signals.append({"SIGNAL_ID":sid,"CREATED_AT":et,"SYMBOL":sym,"DECISION_TIME":p["decision_time"],"SIDE":side_text(p["side"]),
             "ENTRY_REFERENCE":f"{p['entry']:.{h1h['digits']}f}","STOP_PRICE":f"{p['stop']:.{h1h['digits']}f}","TARGET_PRICE":f"{p['target']:.{h1h['digits']}f}",
             "RR":f"{p['rr']:.6f}","SIGNAL_NAME":SIGNAL_NAME,"DECISION_TF":60,"HTP_TF":240,"EVAL_TIME":et,
             "M5_SPREAD_POINTS":q[6] if q is not None else "","USED_SPREAD_POINTS":used_spread})
            if mi is not None:
                o,ot,n=outcome(p,mi,m5,hm["point"],end)
            else:
                o,ot,n="NO_M5_ENTRY_BAR",0,-1
            outs.append({"SIGNAL_ID":sid,"SIDE":side_text(p["side"]),"ENTRY_TIME":et,"ENTRY_REFERENCE":f"{p['entry']:.{h1h['digits']}f}",
             "STOP_PRICE":f"{p['stop']:.{h1h['digits']}f}","TARGET_PRICE":f"{p['target']:.{h1h['digits']}f}","OUTCOME_STATIC":o,"OUTCOME_TIME":ot,"M5_BARS_TO_OUTCOME":n})
        audit.append({"EVAL_TIME":et,"DECISION_TIME":dt,"STATUS":status,"REASON":r,"GATES_PASSED":g,"GATES_TOTAL":12,"MATCH_PCT":f"{100*g/12:.2f}",
         "SIDE":side_text(p["side"]),"ENTRY_REFERENCE":f"{p['entry']:.{h1h['digits']}f}","STOP_PRICE":f"{p['stop']:.{h1h['digits']}f}",
         "TARGET_PRICE":f"{p['target']:.{h1h['digits']}f}","RR":f"{p['rr']:.6f}","SIGNAL_ID":sid,"H4_CURRENT_OPEN":h4[hc][0],"M5_QUOTE_TIME":q[0] if q is not None else 0})
    a.out.mkdir(parents=True,exist_ok=True)
    writecsv(a.out/f"{sym}_REPLAY_AUDIT.csv",list(audit[0].keys()) if audit else ["EVAL_TIME"],audit)
    sf=["SIGNAL_ID","CREATED_AT","SYMBOL","DECISION_TIME","SIDE","ENTRY_REFERENCE","STOP_PRICE","TARGET_PRICE","RR","SIGNAL_NAME","DECISION_TF","HTP_TF","EVAL_TIME","M5_SPREAD_POINTS","USED_SPREAD_POINTS"]
    of=["SIGNAL_ID","SIDE","ENTRY_TIME","ENTRY_REFERENCE","STOP_PRICE","TARGET_PRICE","OUTCOME_STATIC","OUTCOME_TIME","M5_BARS_TO_OUTCOME"]
    writecsv(a.out/f"{sym}_REPLAY_SIGNALS.csv",sf,signals);writecsv(a.out/f"{sym}_REPLAY_OUTCOMES.csv",of,outs)
    hh=hashlib.sha256()
    for r in signals:hh.update(("|".join(str(r[k]) for k in ("SIGNAL_ID","DECISION_TIME","SIDE","ENTRY_REFERENCE","STOP_PRICE","TARGET_PRICE","RR"))+"\n").encode())
    oc=Counter(x["OUTCOME_STATIC"] for x in outs)
    summary={"replay":"DRUMMOND REPLAY 01","status":"PASS" if future==0 else "FAIL","symbol":sym,
     "scope":"Watcher signal replay + static SL/TP M5 market outcome; broker/margin/order/trailing emulation is not included",
     "parameters":{"execution_tf_seconds":300,"decision_tf_seconds":3600,"htp_tf_seconds":14400,"direction_mode":a.direction,
     "rr_min":a.rr_min,"rr_max_exclusive":a.rr_max,"protection_buffer_points":a.buffer_points,
     "quote_source":a.quote_source,
     "spread_mode":"historical_m5" if a.fixed_spread_points is None else "fixed",
     "fixed_spread_points":a.fixed_spread_points,"requested_start_time":a.start_time,"requested_end_time":a.end_time},
     "data":{"M5":hm,"H1":h1h,"H4":h4h},"contract":{"magic":"XFBAR001","version":1,"fixed_header_bytes":HDR.size,"record_size":60,
     "note":f"Supplied field sizes sum to 60 fixed bytes; symbol bytes are appended before records."},
     "common_period":{"start":start,"start_iso":isot(start),"end":end,"end_iso":isot(end)},
     "alignment":{"H1_from_M5":al1,"H4_from_M5":al4},
     "counts":{"decisions":len(audit),"signals":len(signals),"quote_missing_h1_opens":missing,"future_guard_violations":future,"reasons":dict(sorted(reasons.items())),"static_outcomes":dict(sorted(oc.items()))},
     "signal_sha256":hh.hexdigest()}
    (a.out/f"{sym}_REPLAY_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["DRUMMOND REPLAY 01",f"STATUS: {summary['status']}",f"SYMBOL: {sym}",f"COMMON PERIOD: {isot(start)} -> {isot(end)}",
     f"M5 BARS: {hm['bar_count']}",f"H1 BARS: {h1h['bar_count']}",f"H4 BARS: {h4h['bar_count']}",f"DECISIONS: {len(audit)}",f"SIGNALS: {len(signals)}",
     f"FUTURE GUARD VIOLATIONS: {future}",f"H1<-M5 ALIGNMENT: {al1['matched']}/{al1['checked']} ({al1['match_ratio']:.6f})",
     f"H4<-M5 ALIGNMENT: {al4['matched']}/{al4['checked']} ({al4['match_ratio']:.6f})",f"SIGNAL SHA256: {hh.hexdigest()}","",
     "SCOPE: Watcher gates are replayed causally; M5 outcome is static SL/TP first-touch. Broker/margin/slippage/trailing remain for MT4 equivalence."]
    (a.out/f"{sym}_REPLAY_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines[:13]))
    if future:raise SystemExit("DRUMMOND REPLAY 01 FAIL: future guard violation")
    print("DRUMMOND REPLAY 01 PASS")

if __name__=="__main__":main()
