#!/usr/bin/env python3
import argparse,bisect,csv,json,math
from collections import Counter,defaultdict
from pathlib import Path

from drummond_replay01 import read_xfbar,S,SIDE_LONG,SIDE_SHORT
from factory_structural10 import unique_file,read_csv,sources

FIELDS=["CANDIDATE_ID","DIMENSION","BIN","SYMBOL","SIDE","SIGNAL_ID","ENTRY_TIME","OUTCOME","LEVEL_R","FEATURE_VALUE"]

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";")
        w.writeheader(); w.writerows(rows)

def side_symbols(root):
    syms=[]
    for p in Path(root).rglob("*_FACTORY02_LIFECYCLE.csv"):
        syms.append(p.name[:-len("_FACTORY02_LIFECYCLE.csv")])
    if len(syms)!=len(set(syms)):
        raise RuntimeError("duplicate lifecycle symbols in artifact")
    return sorted(syms,key=lambda x:(x.casefold(),x))

def feature_rows(sym,side_text,data_root,artifact_root,buffer_points):
    life=unique_file(artifact_root,f"{sym}_FACTORY02_LIFECYCLE.csv",f"{sym} lifecycle")
    sigf=unique_file(artifact_root,f"{sym}_REPLAY_SIGNALS.csv",f"{sym} replay signals")
    h1p=unique_file(data_root,f"{sym}_H1.bin",f"{sym} H1")
    h4p=unique_file(data_root,f"{sym}_H4.bin",f"{sym} H4")
    signals={r["SIGNAL_ID"]:r for r in read_csv(sigf)}
    resolved=[]
    for r in read_csv(life):
        if r["SIDE"]!=side_text:
            raise RuntimeError(f"{sym}: expected {side_text}, got {r['SIDE']}")
        if r["OUTCOME"] in ("TP","SL") and r.get("LEVEL_R") not in ("",None):
            resolved.append(r)
    resolved.sort(key=lambda r:int(r["ENTRY_TIME"]))
    n=len(resolved)
    if n<30:
        return [],{"resolved":n,"test":0,"eligible":False}
    test_n=max(10,math.ceil(n*0.30))
    test=resolved[n-test_n:]

    h1h,h1=read_xfbar(h1p); h4h,h4=read_xfbar(h4p)
    h1t=[b[0] for b in h1]; h4t=[b[0] for b in h4]
    point=h1h["point"]; digits=h1h["digits"]
    side=SIDE_LONG if side_text=="LONG" else SIDE_SHORT
    sign=1.0 if side==SIDE_LONG else -1.0
    out=[]; future=0

    for r in test:
        sig=signals.get(r["SIGNAL_ID"])
        if sig is None: raise RuntimeError(f"{sym}: missing signal {r['SIGNAL_ID']}")
        et=int(r["ENTRY_TIME"])
        j=bisect.bisect_left(h1t,et)
        if j>=len(h1t) or h1t[j]!=et: raise RuntimeError(f"{sym}: H1 entry time missing {et}")
        hc=bisect.bisect_right(h4t,et)-1
        if hc<0: raise RuntimeError(f"{sym}: H4 state missing {et}")
        ds=S(h1,j,point,digits); hs=S(h4,hc,point,digits)
        if ds.bar(1)[0]>=et or hs.bar(1)[0]>=et:
            future+=1; continue

        entry=float(sig["ENTRY_REFERENCE"]); stop=float(sig["STOP_PRICE"]); target=float(sig["TARGET_PRICE"])
        risk=abs(entry-stop)
        if entry<=0 or risk<=0: raise RuntimeError(f"{sym}: invalid risk geometry")
        stop_src,target_src=sources(ds,hs,side,entry,point,digits,buffer_points,stop,target)
        d1,d2=ds.dot(1),ds.dot(2); h41,h42=hs.dot(1),hs.dot(2)
        if min(d1,d2,h41,h42)<=0: raise RuntimeError(f"{sym}: PLDot unavailable")
        b=ds.bar(1); low,high,close,open_=b[3],b[2],b[4],b[1]
        if side==SIDE_LONG:
            penetration=max(0.0,d1-low)/risk; reclaim=max(0.0,close-d1)/risk
        else:
            penetration=max(0.0,high-d1)/risk; reclaim=max(0.0,d1-close)/risk
        used_spread=max(0,int(float(sig["USED_SPREAD_POINTS"])))
        values={
            "RR":float(sig["RR"]),
            "STOP_SOURCE":stop_src,"TARGET_SOURCE":target_src,
            "SOURCE_PAIR":f"{stop_src}->{target_src}",
            "ENTRY_PLDOT_R":sign*(entry-d1)/risk,
            "H1_PLDOT_SLOPE_R":sign*(d1-d2)/risk,
            "H4_ENTRY_PLDOT_R":sign*(entry-h41)/risk,
            "H4_PLDOT_SLOPE_R":sign*(h41-h42)/risk,
            "REFRESH_PENETRATION_R":penetration,
            "REFRESH_RECLAIM_R":reclaim,
            "H1_RANGE_R":(high-low)/risk,
            "H1_BODY_R":sign*(close-open_)/risk,
            "SPREAD_RISK":(used_spread*point)/risk,
            "INITIAL_RISK_PCT":risk/entry
        }
        out.append({"symbol":sym,"side":side_text,"signal_id":r["SIGNAL_ID"],"entry_time":et,
                    "outcome":r["OUTCOME"],"r":float(r["LEVEL_R"]),"values":values})
    if future: raise RuntimeError(f"{sym}: future guard violations={future}")
    return out,{"resolved":n,"test":len(out),"eligible":True}

def matches(row,c):
    if row["side"]!=c["side"]: return False,None
    dim=c["dimension"]
    if dim=="SOURCE_PAIR":
        val=row["values"]["SOURCE_PAIR"]
        return val==c["bin"],val
    if dim not in row["values"]:
        raise RuntimeError(f"unsupported frozen dimension {dim}")
    val=float(row["values"][dim])
    lo=c.get("lower_inclusive"); hi=c.get("upper_exclusive")
    if lo is not None and val<float(lo): return False,val
    if hi is not None and val>=float(hi): return False,val
    return True,val

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--short-root",type=Path,required=True)
    ap.add_argument("--long-root",type=Path,required=True)
    ap.add_argument("--candidates",type=Path,required=True)
    ap.add_argument("--expected-sha",required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--buffer-points",type=int,default=1)
    a=ap.parse_args()

    frozen=json.loads(a.candidates.read_text(encoding="utf-8"))
    if frozen.get("canonical_sha256")!=a.expected_sha:
        raise SystemExit("frozen candidate SHA mismatch")
    if frozen.get("test_rows_used") or frozen.get("selection_source")!="TRAIN only":
        raise SystemExit("candidate freeze contract invalid")
    candidates=frozen["candidates"]
    if len(candidates)!=2: raise SystemExit(f"expected 2 frozen candidates, got {len(candidates)}")
    tagged=[(f"C{i+1:02d}",c) for i,c in enumerate(candidates)]

    matches_out=[]; stats=Counter(); candidate_counts=Counter()
    for side_text,root in (("SHORT",a.short_root),("LONG",a.long_root)):
        for sym in side_symbols(root):
            rows,st=feature_rows(sym,side_text,a.data_root,root,a.buffer_points)
            stats[f"{side_text}_resolved"]+=st["resolved"]
            stats[f"{side_text}_test"]+=st["test"]
            stats[f"{side_text}_eligible_series"]+=1 if st["eligible"] else 0
            for row in rows:
                for cid,c in tagged:
                    ok,val=matches(row,c)
                    if not ok: continue
                    candidate_counts[cid]+=1
                    matches_out.append({
                        "CANDIDATE_ID":cid,"DIMENSION":c["dimension"],"BIN":c["bin"],
                        "SYMBOL":row["symbol"],"SIDE":row["side"],"SIGNAL_ID":row["signal_id"],
                        "ENTRY_TIME":row["entry_time"],"OUTCOME":row["outcome"],
                        "LEVEL_R":f"{row['r']:.8f}",
                        "FEATURE_VALUE":str(val) if isinstance(val,str) else f"{val:.10f}"
                    })

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"FACTORY12_TEST_MATCHES.csv",matches_out)
    summary={
        "block":"DRUMMOND FROZEN STRUCTURAL TEST 12 SHARD",
        "status":"PASS","frozen_candidate_sha256":a.expected_sha,
        "counts":{
            "short_test":stats["SHORT_test"],"long_test":stats["LONG_test"],
            "short_resolved":stats["SHORT_resolved"],"long_resolved":stats["LONG_resolved"],
            "short_eligible_series":stats["SHORT_eligible_series"],"long_eligible_series":stats["LONG_eligible_series"],
            "candidate_matches":dict(sorted(candidate_counts.items()))
        },
        "guards":{
            "candidate_rules_modified":False,
            "features_causal_at_signal_creation":True,
            "post_entry_features_used":False
        }
    }
    (a.out/"FACTORY12_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("DRUMMOND FROZEN STRUCTURAL TEST 12 SHARD")
    print("STATUS: PASS")
    print(f"SHORT/LONG TEST: {stats['SHORT_test']}/{stats['LONG_test']}")
    print(f"CANDIDATE MATCHES: {dict(sorted(candidate_counts.items()))}")

if __name__=="__main__":
    main()
