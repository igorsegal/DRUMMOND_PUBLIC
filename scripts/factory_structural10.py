#!/usr/bin/env python3
import argparse,bisect,csv,json,math
from collections import Counter
from pathlib import Path

from drummond_replay01 import (
    read_xfbar,S,SIDE_LONG,SIDE_SHORT,
    L51U,L51D,L52U,L52D,L59U,L59D,norm
)

FIELDS=[
    "SYMBOL","SIDE","SIGNAL_ID","ENTRY_TIME","OUTCOME","LEVEL_R","RR",
    "STOP_SOURCE","TARGET_SOURCE",
    "ENTRY_PLDOT_R","H1_PLDOT_SLOPE_R",
    "H4_ENTRY_PLDOT_R","H4_PLDOT_SLOPE_R",
    "REFRESH_PENETRATION_R","REFRESH_RECLAIM_R",
    "H1_RANGE_R","H1_BODY_R","SPREAD_RISK",
    "INITIAL_RISK_PCT"
]

SRC={L51U:"L51",L51D:"L51",L52U:"L52",L52D:"L52",L59U:"L59",L59D:"L59"}

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";")
        w.writeheader(); w.writerows(rows)

def unique_file(root,pattern,desc):
    hits=list(Path(root).rglob(pattern))
    if len(hits)!=1:
        raise RuntimeError(f"{desc}: expected 1 match for {pattern}, got {len(hits)}")
    return hits[0]

def line_choice(state,ids,side,entry,kind):
    vals=[]
    for i in ids:
        x=state.line(i)
        if x is None: continue
        if kind=="target":
            ok=(side==SIDE_LONG and x>entry) or (side==SIDE_SHORT and x<entry)
        else:
            ok=(side==SIDE_LONG and x<entry) or (side==SIDE_SHORT and x>entry)
        if ok: vals.append((x,i))
    if not vals: return None,None
    if side==SIDE_LONG:
        x,i=min(vals,key=lambda z:z[0])
    else:
        x,i=max(vals,key=lambda z:z[0])
    return x,i

def sources(ds,hs,side,entry,point,digits,buffer_points,actual_stop,actual_target):
    target_ids=(L51D,L52D,L59D) if side==SIDE_LONG else (L51U,L52U,L59U)
    stop_ids=(L51U,L52U,L59U) if side==SIDE_LONG else (L51D,L52D,L59D)
    tx,ti=line_choice(hs,target_ids,side,entry,"target")
    sx,si=line_choice(ds,stop_ids,side,entry,"stop")
    if tx is None or sx is None:
        raise RuntimeError("structural source unexpectedly unavailable")
    expected_target=norm(tx,digits)
    expected_stop=norm(sx + (-1 if side==SIDE_LONG else 1)*max(1,buffer_points)*point,digits)
    tol=max(point*0.11,1e-10)
    if abs(expected_target-actual_target)>tol:
        raise RuntimeError(f"target geometry mismatch expected={expected_target} actual={actual_target}")
    if abs(expected_stop-actual_stop)>tol:
        raise RuntimeError(f"stop geometry mismatch expected={expected_stop} actual={actual_stop}")
    return SRC[si],SRC[ti]

def enrich(sym,side_text,data_root,artifact_root,buffer_points):
    life=unique_file(artifact_root,f"{sym}_FACTORY02_LIFECYCLE.csv",f"{sym} lifecycle")
    sigf=unique_file(artifact_root,f"{sym}_REPLAY_SIGNALS.csv",f"{sym} replay signals")
    h1p=unique_file(data_root,f"{sym}_H1.bin",f"{sym} H1")
    h4p=unique_file(data_root,f"{sym}_H4.bin",f"{sym} H4")

    signals={r["SIGNAL_ID"]:r for r in read_csv(sigf)}
    life_rows=read_csv(life)
    resolved=[]
    for r in life_rows:
        if r["SIDE"]!=side_text:
            raise RuntimeError(f"{sym}: expected {side_text}, got {r['SIDE']}")
        if r["OUTCOME"] not in ("TP","SL") or r.get("LEVEL_R") in ("",None):
            continue
        resolved.append(r)
    resolved.sort(key=lambda r:int(r["ENTRY_TIME"]))
    n=len(resolved)
    if n<30:
        return [],{"resolved":n,"train":0,"eligible":False}

    test_n=max(10,math.ceil(n*0.30))
    train=resolved[:n-test_n]

    h1h,h1=read_xfbar(h1p)
    h4h,h4=read_xfbar(h4p)
    if h1h["symbol"]!=sym or h4h["symbol"]!=sym:
        raise RuntimeError(f"{sym}: BIN symbol mismatch")
    if h1h["period_seconds"]!=3600 or h4h["period_seconds"]!=14400:
        raise RuntimeError(f"{sym}: timeframe mismatch")
    if h1h["digits"]!=h4h["digits"] or abs(h1h["point"]-h4h["point"])>1e-15:
        raise RuntimeError(f"{sym}: H1/H4 contract mismatch")

    h1t=[b[0] for b in h1]; h4t=[b[0] for b in h4]
    point=h1h["point"]; digits=h1h["digits"]
    side=SIDE_LONG if side_text=="LONG" else SIDE_SHORT
    sign=1.0 if side==SIDE_LONG else -1.0
    out=[]
    future_guard=0

    for r in train:
        sid=r["SIGNAL_ID"]
        sig=signals.get(sid)
        if sig is None: raise RuntimeError(f"{sym}: signal join missing {sid}")
        et=int(r["ENTRY_TIME"])
        j=bisect.bisect_left(h1t,et)
        if j>=len(h1t) or h1t[j]!=et:
            raise RuntimeError(f"{sym}: H1 entry time not found {et}")
        hc=bisect.bisect_right(h4t,et)-1
        if hc<0: raise RuntimeError(f"{sym}: no H4 state at {et}")
        ds=S(h1,j,point,digits); hs=S(h4,hc,point,digits)
        if ds.n()<6 or hs.n()<6:
            raise RuntimeError(f"{sym}: insufficient state history")

        if ds.bar(1)[0]>=et or hs.bar(1)[0]>=et:
            future_guard+=1
            continue

        entry=float(sig["ENTRY_REFERENCE"])
        stop=float(sig["STOP_PRICE"])
        target=float(sig["TARGET_PRICE"])
        risk=abs(entry-stop)
        if risk<=0 or entry<=0:
            raise RuntimeError(f"{sym}: invalid risk geometry {sid}")

        stop_src,target_src=sources(ds,hs,side,entry,point,digits,buffer_points,stop,target)

        d1=ds.dot(1); d2=ds.dot(2)
        h41=hs.dot(1); h42=hs.dot(2)
        if min(d1,d2,h41,h42)<=0:
            raise RuntimeError(f"{sym}: PLDot unavailable for accepted signal {sid}")

        b=ds.bar(1)
        low,high,close,open_=b[3],b[2],b[4],b[1]
        if side==SIDE_LONG:
            penetration=max(0.0,d1-low)/risk
            reclaim=max(0.0,close-d1)/risk
        else:
            penetration=max(0.0,high-d1)/risk
            reclaim=max(0.0,d1-close)/risk

        used_spread=max(0,int(float(sig["USED_SPREAD_POINTS"])))
        row={
            "SYMBOL":sym,"SIDE":side_text,"SIGNAL_ID":sid,"ENTRY_TIME":et,
            "OUTCOME":r["OUTCOME"],"LEVEL_R":f"{float(r['LEVEL_R']):.8f}",
            "RR":f"{float(sig['RR']):.8f}",
            "STOP_SOURCE":stop_src,"TARGET_SOURCE":target_src,
            "ENTRY_PLDOT_R":f"{sign*(entry-d1)/risk:.8f}",
            "H1_PLDOT_SLOPE_R":f"{sign*(d1-d2)/risk:.8f}",
            "H4_ENTRY_PLDOT_R":f"{sign*(entry-h41)/risk:.8f}",
            "H4_PLDOT_SLOPE_R":f"{sign*(h41-h42)/risk:.8f}",
            "REFRESH_PENETRATION_R":f"{penetration:.8f}",
            "REFRESH_RECLAIM_R":f"{reclaim:.8f}",
            "H1_RANGE_R":f"{(high-low)/risk:.8f}",
            "H1_BODY_R":f"{sign*(close-open_)/risk:.8f}",
            "SPREAD_RISK":f"{(used_spread*point)/risk:.8f}",
            "INITIAL_RISK_PCT":f"{risk/entry:.10f}"
        }
        out.append(row)

    if future_guard:
        raise RuntimeError(f"{sym}: future guard violations={future_guard}")
    return out,{"resolved":n,"train":len(out),"eligible":True}

def side_symbols(root):
    syms=[]
    for p in Path(root).rglob("*_FACTORY02_LIFECYCLE.csv"):
        syms.append(p.name[:-len("_FACTORY02_LIFECYCLE.csv")])
    if len(syms)!=len(set(syms)):
        raise RuntimeError("duplicate lifecycle symbols in artifact")
    return sorted(syms,key=lambda x:(x.casefold(),x))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--short-root",type=Path,required=True)
    ap.add_argument("--long-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--buffer-points",type=int,default=1)
    a=ap.parse_args()

    rows=[]; stats=Counter(); combo=Counter()
    for side_text,root in (("SHORT",a.short_root),("LONG",a.long_root)):
        for sym in side_symbols(root):
            try:
                rr,st=enrich(sym,side_text,a.data_root,root,a.buffer_points)
            except Exception as e:
                raise SystemExit(f"{side_text} {sym}: {e}")
            stats[f"{side_text}_resolved"]+=st["resolved"]
            stats[f"{side_text}_train"]+=st["train"]
            stats[f"{side_text}_eligible_series"]+=1 if st["eligible"] else 0
            rows.extend(rr)
            for x in rr:
                combo[(x["SIDE"],x["STOP_SOURCE"],x["TARGET_SOURCE"])]+=1

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"FACTORY10_TRAIN_STRUCTURAL_FEATURES.csv",rows)
    combos=[
        {"side":k[0],"stop_source":k[1],"target_source":k[2],"n":v}
        for k,v in sorted(combo.items())
    ]
    summary={
        "block":"DRUMMOND STRUCTURAL CONTEXT 10",
        "status":"PASS",
        "dataset_id":"DRUMMOND_CANONICAL_8E9A1D784E3893D9",
        "scope":"TRAIN-only structural feature enrichment; no TEST rows are emitted or evaluated.",
        "counts":{
            "rows":len(rows),
            "short_train":stats["SHORT_train"],
            "long_train":stats["LONG_train"],
            "short_resolved":stats["SHORT_resolved"],
            "long_resolved":stats["LONG_resolved"],
            "short_eligible_series":stats["SHORT_eligible_series"],
            "long_eligible_series":stats["LONG_eligible_series"]
        },
        "features":[
            "STOP_SOURCE","TARGET_SOURCE","ENTRY_PLDOT_R","H1_PLDOT_SLOPE_R",
            "H4_ENTRY_PLDOT_R","H4_PLDOT_SLOPE_R","REFRESH_PENETRATION_R",
            "REFRESH_RECLAIM_R","H1_RANGE_R","H1_BODY_R","SPREAD_RISK","INITIAL_RISK_PCT"
        ],
        "leakage_guard":{
            "test_rows_used":False,
            "test_outcomes_read_for_feature_selection":False,
            "post_entry_features_used":False,
            "all_market_features_observable_at_signal_creation":True,
            "production_signal_identity_modified":False
        },
        "source_combinations":combos,
        "selection":"NONE",
        "next_required_gate":"Analyze TRAIN-only structural bins/rules, freeze a rule, then validate on TEST in a separate block."
    }
    (a.out/"FACTORY10_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=[
        "DRUMMOND STRUCTURAL CONTEXT 10","STATUS: PASS",
        f"ROWS: {len(rows)}",
        f"SHORT TRAIN: {stats['SHORT_train']}",
        f"LONG TRAIN: {stats['LONG_train']}",
        f"SHORT/LONG ELIGIBLE SERIES: {stats['SHORT_eligible_series']}/{stats['LONG_eligible_series']}",
        "TEST ROWS USED: NO","POST-ENTRY FEATURES USED: NO",
        "PRODUCTION SIGNAL IDENTITY MODIFIED: NO",
        "SELECTION: NONE"
    ]
    (a.out/"FACTORY10_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
