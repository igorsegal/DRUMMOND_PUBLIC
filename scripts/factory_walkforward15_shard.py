#!/usr/bin/env python3
import argparse,bisect,csv,json,math
from pathlib import Path

from drummond_replay01 import read_xfbar,S

FIELDS=[
    "SYMBOL","SIGNAL_ID","ENTRY_TIME","OUTCOME","LEVEL_R",
    "ENTRY_REFERENCE","STOP_PRICE","DECISION_PLDOT","ENTRY_PLDOT_R",
    "SERIES_RESOLVED_N","ELIGIBLE30"
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

def symbols(root):
    out=[]
    for p in Path(root).rglob("*_FACTORY02_LIFECYCLE.csv"):
        out.append(p.name[:-len("_FACTORY02_LIFECYCLE.csv")])
    if len(out)!=len(set(out)):
        raise RuntimeError("duplicate lifecycle symbol")
    return sorted(out,key=lambda x:(x.casefold(),x))

def process_symbol(sym,data_root,long_root):
    life=one(long_root,f"{sym}_FACTORY02_LIFECYCLE.csv",f"{sym} lifecycle")
    sigf=one(long_root,f"{sym}_REPLAY_SIGNALS.csv",f"{sym} signals")
    h1p=one(data_root,f"{sym}_H1.bin",f"{sym} H1")

    sig={r["SIGNAL_ID"]:r for r in read_csv(sigf)}
    resolved=[]
    for r in read_csv(life):
        if r["SIDE"]!="LONG":
            raise RuntimeError(f"{sym}: non-LONG row in LONG_ONLY evidence")
        if r["OUTCOME"] in ("TP","SL") and r.get("LEVEL_R") not in ("",None):
            resolved.append(r)
    resolved.sort(key=lambda r:int(r["ENTRY_TIME"]))
    n=len(resolved)

    h,h1=read_xfbar(h1p)
    if h["symbol"]!=sym or h["period_seconds"]!=3600:
        raise RuntimeError(f"{sym}: H1 contract mismatch")
    times=[b[0] for b in h1]
    point=h["point"];digits=h["digits"]
    out=[]
    for r in resolved:
        sid=r["SIGNAL_ID"]
        s=sig.get(sid)
        if s is None:
            raise RuntimeError(f"{sym}: signal join missing {sid}")
        et=int(r["ENTRY_TIME"])
        j=bisect.bisect_left(times,et)
        if j>=len(times) or times[j]!=et:
            raise RuntimeError(f"{sym}: H1 entry time not found {et}")
        ds=S(h1,j,point,digits)
        if ds.n()<6 or ds.bar(1)[0]>=et:
            raise RuntimeError(f"{sym}: causal H1 state unavailable {sid}")
        dot=ds.dot(1)
        entry=float(s["ENTRY_REFERENCE"])
        stop=float(s["STOP_PRICE"])
        risk=abs(entry-stop)
        if dot<=0 or entry<=0 or risk<=0:
            raise RuntimeError(f"{sym}: invalid C01 geometry {sid}")
        feature=(entry-dot)/risk
        if feature>=0.0:
            continue
        out.append({
            "SYMBOL":sym,"SIGNAL_ID":sid,"ENTRY_TIME":et,
            "OUTCOME":r["OUTCOME"],"LEVEL_R":f"{float(r['LEVEL_R']):.8f}",
            "ENTRY_REFERENCE":f"{entry:.10f}","STOP_PRICE":f"{stop:.10f}",
            "DECISION_PLDOT":f"{dot:.10f}","ENTRY_PLDOT_R":f"{feature:.10f}",
            "SERIES_RESOLVED_N":n,"ELIGIBLE30":"YES" if n>=30 else "NO"
        })
    return out,n

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--long-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    rows=[];resolved_total=0;eligible_symbols=0
    syms=symbols(a.long_root)
    for sym in syms:
        rr,n=process_symbol(sym,a.data_root,a.long_root)
        rows.extend(rr);resolved_total+=n
        if n>=30: eligible_symbols+=1
    rows.sort(key=lambda r:(int(r["ENTRY_TIME"]),r["SYMBOL"].casefold(),r["SIGNAL_ID"]))

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"FACTORY15_C01_EVENTS.csv",rows)
    summary={
        "block":"DRUMMOND C01 WALK-FORWARD 15 SHARD",
        "status":"PASS",
        "processed_symbols":len(syms),
        "eligible30_symbols":eligible_symbols,
        "resolved_long_population":resolved_total,
        "c01_events":len(rows),
        "rule":"LONG base signal AND ENTRY_PLDOT_R < 0",
        "rule_modified":False,
        "future_data_required":False
    }
    (a.out/"FACTORY15_SHARD_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("DRUMMOND C01 WALK-FORWARD 15 SHARD")
    print("STATUS: PASS")
    print("SYMBOLS:",len(syms))
    print("RESOLVED LONG:",resolved_total)
    print("C01 EVENTS:",len(rows))

if __name__=="__main__":
    main()
