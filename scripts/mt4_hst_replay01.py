#!/usr/bin/env python3
import argparse,bisect,csv,json,math,os,struct,sys,tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from drummond_replay01 import S,evaluate,DIR_SHORT,DIR_BOTH,DIR_LONG,side_text,writecsv

HST_HEADER=struct.Struct("<i64s12siiii13i")
HST_REC=struct.Struct("<qddddqiq")

def zstr(b):
    return b.split(b"\0",1)[0].decode("ascii","ignore")

def read_hst_header(path):
    with Path(path).open("rb") as f:
        b=f.read(HST_HEADER.size)
    if len(b)!=HST_HEADER.size:
        raise ValueError(f"{path}: short HST header")
    x=HST_HEADER.unpack(b)
    version=x[0]
    if version not in (400,401):
        raise ValueError(f"{path}: unsupported HST version {version}")
    symbol=zstr(x[2]); period=x[3]; digits=x[4]
    if not symbol or period<=0 or digits<0:
        raise ValueError(f"{path}: invalid HST metadata")
    return {"path":str(path),"version":version,"symbol":symbol,"period":period,"digits":digits,
            "point":10.0**(-digits),"header_bytes":HST_HEADER.size,"file_bytes":Path(path).stat().st_size}

def read_hst(path):
    h=read_hst_header(path)
    if h["version"]!=401:
        raise ValueError(f"{path}: HST v400 is not supported for equivalence replay")
    data=Path(path).read_bytes()
    body=data[HST_HEADER.size:]
    if len(body)%HST_REC.size:
        raise ValueError(f"{path}: HST body is not a multiple of 60 bytes")
    raw=[HST_REC.unpack_from(body,i) for i in range(0,len(body),HST_REC.size)]
    def score(order):
        ok=0
        for r in raw[:min(500,len(raw))]:
            t,o,a,b,c,tv,sp,rv=r
            hi,lo=(a,b) if order=="ohlc" else (b,a)
            if all(math.isfinite(v) for v in (o,hi,lo,c)) and hi>=max(o,c) and lo<=min(o,c):
                ok+=1
        return ok
    # Official v401 is open,low,high,close. Auto-detect protects against non-standard writers.
    official=score("olhc"); alternate=score("ohlc")
    use_official=official>=alternate
    bars=[];prev=None
    for r in raw:
        t,o,a,b,c,tv,sp,rv=r
        hi,lo=(b,a) if use_official else (a,b)
        if prev is not None and t<=prev:
            raise ValueError(f"{path}: non-monotonic HST time")
        if not all(math.isfinite(v) for v in (o,hi,lo,c)):
            raise ValueError(f"{path}: non-finite HST OHLC")
        if hi<max(o,c) or lo>min(o,c):
            raise ValueError(f"{path}: invalid HST OHLC envelope at {t}")
        bars.append((int(t),float(o),float(hi),float(lo),float(c),int(tv),int(sp),int(rv)))
        prev=t
    h["bar_count"]=len(bars)
    h["first_time"]=bars[0][0] if bars else 0
    h["last_time"]=bars[-1][0] if bars else 0
    h["record_order"]="open,low,high,close" if use_official else "open,high,low,close"
    return h,bars

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def choose_pair(root,symbol,watcher):
    root=Path(root)
    rows=read_csv(watcher)
    full=[r for r in rows if r.get("SYMBOL")==symbol and r.get("STATUS")=="QUEUED" and r.get("ENTRY_REFERENCE")]
    decision=[int(r["DECISION_TIME"]) for r in rows if r.get("SYMBOL")==symbol and r.get("DECISION_TIME")]
    groups={}
    for p in root.rglob("*.hst"):
        try:h=read_hst_header(p)
        except Exception:continue
        if h["symbol"]!=symbol or h["period"] not in (60,240):continue
        groups.setdefault(str(p.parent),{})[h["period"]]=p
    candidates=[]
    for parent,g in groups.items():
        if 60 not in g or 240 not in g:continue
        try:
            h1h,h1=read_hst(g[60]); h4h,h4=read_hst(g[240])
        except Exception:
            continue
        ht={b[0] for b in h1}
        overlap=sum(1 for t in decision if t in ht)
        times=[b[0] for b in h1]
        diffs=[]
        for r in full[:100]:
            st=int(r["SERVER_TIME"]); i=bisect.bisect_right(times,st)-1
            if i<0:continue
            bid=h1[i][1]
            diffs.append(abs(bid-float(r["ENTRY_REFERENCE"])))
        mae=sum(diffs)/len(diffs) if diffs else 1e99
        newest=max(g[60].stat().st_mtime,g[240].stat().st_mtime)
        candidates.append((overlap,-mae,newest,parent,g[60],g[240],mae,len(h1),len(h4)))
    if not candidates:
        raise RuntimeError(f"No {symbol} H1/H4 HST pair found under {root}")
    candidates.sort(reverse=True)
    x=candidates[0]
    return {"parent":x[3],"h1":str(x[4]),"h4":str(x[5]),"decision_overlap":x[0],
            "entry_mae":x[6],"h1_bars":x[7],"h4_bars":x[8],"candidate_count":len(candidates)}

def replay_hst(h1_path,h4_path,watcher_path,out_dir,direction="SHORT_ONLY",rr_min=.75,rr_max=1.75,buffer_points=1,spread_points=20):
    h1h,h1=read_hst(h1_path); h4h,h4=read_hst(h4_path)
    if h1h["symbol"]!=h4h["symbol"]:raise ValueError("HST symbol mismatch")
    if h1h["period"]!=60 or h4h["period"]!=240:raise ValueError("HST timeframe mismatch")
    if h1h["digits"]!=h4h["digits"]:raise ValueError("HST digits mismatch")
    point=h1h["point"];digits=h1h["digits"];symbol=h1h["symbol"]
    mode={"BOTH":DIR_BOTH,"SHORT_ONLY":DIR_SHORT,"LONG_ONLY":DIR_LONG}[direction]
    src=[r for r in read_csv(watcher_path) if r.get("SYMBOL")==symbol]
    h1t=[b[0] for b in h1]; h4t=[b[0] for b in h4]
    audit=[];signals=[];mapping_errors=[]
    seen=set()
    for row in src:
        dt=int(row["DECISION_TIME"]); st=int(row["SERVER_TIME"])
        if dt in seen:continue
        seen.add(dt)
        ci=bisect.bisect_right(h1t,st)-1
        if ci<1 or h1[ci-1][0]!=dt:
            di=bisect.bisect_left(h1t,dt)
            if di>=len(h1t) or h1t[di]!=dt or di+1>=len(h1):
                mapping_errors.append({"decision_time":dt,"server_time":st,"reason":"H1_DECISION_NOT_FOUND"})
                continue
            ci=di+1
        hc=bisect.bisect_right(h4t,st)-1
        if hc<1:
            mapping_errors.append({"decision_time":dt,"server_time":st,"reason":"H4_CONTEXT_NOT_FOUND"})
            continue
        ds=S(h1,ci,point,digits);hs=S(h4,hc,point,digits)
        bid=h1[ci][1];ask=bid+max(0,spread_points)*point
        full,p,reason,g=evaluate(symbol,ds,hs,bid,ask,dt,mode,rr_min,rr_max,buffer_points)
        sid="";status="NO_TRADE"
        if full:
            sid=f"{symbol}_{dt}_{'L' if p['side']==1 else 'S'}";status="QUEUED"
            signals.append({"SIGNAL_ID":sid,"CREATED_AT":st,"SYMBOL":symbol,"DECISION_TIME":dt,
                "SIDE":side_text(p["side"]),"ENTRY_REFERENCE":f"{p['entry']:.{digits}f}",
                "STOP_PRICE":f"{p['stop']:.{digits}f}","TARGET_PRICE":f"{p['target']:.{digits}f}",
                "RR":f"{p['rr']:.6f}","SIGNAL_NAME":"CONSERVATIVE_TREND_PLDOT_REFRESH_HTP_ALIGNED",
                "DECISION_TF":60,"HTP_TF":240})
        audit.append({"SERVER_TIME":st,"SYMBOL":symbol,"DECISION_TIME":dt,"STATUS":status,"REASON":reason,
            "GATES_PASSED":g,"GATES_TOTAL":12,"MATCH_PCT":f"{100*g/12:.2f}",
            "SIDE":side_text(p["side"]),"ENTRY_REFERENCE":f"{p['entry']:.{digits}f}",
            "STOP_PRICE":f"{p['stop']:.{digits}f}","TARGET_PRICE":f"{p['target']:.{digits}f}",
            "RR":f"{p['rr']:.6f}","SIGNAL_ID":sid})
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    af=["SERVER_TIME","SYMBOL","DECISION_TIME","STATUS","REASON","GATES_PASSED","GATES_TOTAL","MATCH_PCT","SIDE","ENTRY_REFERENCE","STOP_PRICE","TARGET_PRICE","RR","SIGNAL_ID"]
    sf=["SIGNAL_ID","CREATED_AT","SYMBOL","DECISION_TIME","SIDE","ENTRY_REFERENCE","STOP_PRICE","TARGET_PRICE","RR","SIGNAL_NAME","DECISION_TF","HTP_TF"]
    writecsv(out/"XAUUSD_HST_REPLAY_AUDIT.csv",af,audit)
    writecsv(out/"XAUUSD_HST_REPLAY_SIGNALS.csv",sf,signals)
    summary={"status":"PASS" if not mapping_errors else "FAIL","symbol":symbol,
      "h1":h1h,"h4":h4h,"source_watcher_rows":len(src),"replayed_decisions":len(audit),
      "signals":len(signals),"mapping_errors":mapping_errors[:100],"mapping_error_count":len(mapping_errors),
      "parameters":{"direction":direction,"rr_min":rr_min,"rr_max_exclusive":rr_max,
                    "buffer_points":buffer_points,"spread_points":spread_points}}
    (out/"XAUUSD_HST_REPLAY_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"HST REPLAY decisions={len(audit)} signals={len(signals)} mapping_errors={len(mapping_errors)}")
    return summary

def selftest():
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"XAUUSD60.hst"
        hdr=HST_HEADER.pack(401,b"(C) MetaQuotes Software Corp.".ljust(64,b"\0"),
            b"XAUUSD".ljust(12,b"\0"),60,2,0,0,*([0]*13))
        rows=[]
        for i in range(30):
            t=1700000000+i*3600;o=1900+i*.1;lo=o-.5;hi=o+.8;c=o+.2
            rows.append(HST_REC.pack(t,o,lo,hi,c,100+i,20,0))
        p.write_bytes(hdr+b"".join(rows))
        h,b=read_hst(p)
        assert h["version"]==401 and h["symbol"]=="XAUUSD" and h["period"]==60
        assert h["bar_count"]==30 and h["record_order"]=="open,low,high,close"
        assert abs(b[0][2]-1900.8)<1e-9 and abs(b[0][3]-1899.5)<1e-9
    print("MT4 HST BRIDGE SELFTEST PASS")

def main():
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    f=sub.add_parser("find")
    f.add_argument("--terminal-root",type=Path,required=True);f.add_argument("--symbol",default="XAUUSD");f.add_argument("--watcher",type=Path,required=True)
    r=sub.add_parser("replay")
    r.add_argument("--h1",type=Path,required=True);r.add_argument("--h4",type=Path,required=True);r.add_argument("--watcher",type=Path,required=True);r.add_argument("--out",type=Path,required=True)
    r.add_argument("--spread-points",type=int,default=20)
    a=ap.parse_args()
    if a.cmd=="selftest": selftest();return
    if a.cmd=="find":
        print(json.dumps(choose_pair(a.terminal_root,a.symbol,a.watcher),ensure_ascii=False,indent=2));return
    s=replay_hst(a.h1,a.h4,a.watcher,a.out,spread_points=a.spread_points)
    raise SystemExit(0 if s["status"]=="PASS" else 2)

if __name__=="__main__":main()
