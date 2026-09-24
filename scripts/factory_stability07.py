#!/usr/bin/env python3
import argparse,csv,json,math
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

SIDE_FIELDS=[
    "SYMBOL","SIDE","TOTAL_SIGNALS","RESOLVED","TRAIN_N","TEST_N","SPLIT_TIME","SPLIT_UTC",
    "TRAIN_TP","TRAIN_SL","TEST_TP","TEST_SL","TRAIN_TP_RATE","TEST_TP_RATE",
    "TRAIN_MEAN_R","TEST_MEAN_R","FULL_MEAN_R","STABILITY_CLASS","ELIGIBLE"
]
YEAR_FIELDS=["SYMBOL","SIDE","YEAR","RESOLVED","TP","SL","TP_RATE","MEAN_R"]
SYMBOL_FIELDS=[
    "SYMBOL","TOTAL_SIGNALS","RESOLVED","TRAIN_N","TEST_N","SPLIT_TIME","SPLIT_UTC",
    "TRAIN_TP","TRAIN_SL","TEST_TP","TEST_SL","TRAIN_TP_RATE","TEST_TP_RATE",
    "TRAIN_MEAN_R","TEST_MEAN_R","FULL_MEAN_R","STABILITY_CLASS","ELIGIBLE"
]

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";")
        w.writeheader(); w.writerows(rows)

def fmt(x):
    return "" if x is None else f"{x:.8f}"

def utc_text(ts):
    return datetime.fromtimestamp(ts,tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else ""

def load_root(root,expected_side):
    by_symbol={}
    duplicate_guard=set()
    files=sorted(Path(root).rglob("*_FACTORY02_LIFECYCLE.csv"))
    for p in files:
        sym=p.name[:-len("_FACTORY02_LIFECYCLE.csv")]
        if sym in by_symbol:
            raise SystemExit(f"duplicate lifecycle file for {expected_side} {sym}")
        rows=read_csv(p)
        recs=[]
        for r in rows:
            side=r["SIDE"]
            if side!=expected_side:
                raise SystemExit(f"unexpected side in {p}: expected {expected_side}, got {side}")
            sid=r["SIGNAL_ID"]
            key=(expected_side,sym,sid)
            if key in duplicate_guard:
                raise SystemExit(f"duplicate signal id: {key}")
            duplicate_guard.add(key)
            et=int(r["ENTRY_TIME"])
            out=r["OUTCOME"]
            rv=float(r["LEVEL_R"]) if r.get("LEVEL_R") not in ("",None) else None
            recs.append({"entry_time":et,"outcome":out,"r":rv})
        by_symbol[sym]=recs
    return by_symbol

def metrics(records):
    resolved=[r for r in records if r["outcome"] in ("TP","SL") and r["r"] is not None]
    resolved.sort(key=lambda x:x["entry_time"])
    n=len(resolved)
    eligible=n>=30
    if n==0:
        return {"resolved":resolved,"eligible":False,"train":[],"test":[],"split_time":0,
                "train_mean":None,"test_mean":None,"full_mean":None,"class":"NO_RESOLVED"}
    if eligible:
        test_n=max(10,math.ceil(n*0.30))
        train_n=n-test_n
        train=resolved[:train_n]; test=resolved[train_n:]
        split_time=test[0]["entry_time"]
    else:
        train=[]; test=[]; split_time=0
    full_mean=sum(r["r"] for r in resolved)/n
    if eligible:
        tr=sum(r["r"] for r in train)/len(train)
        te=sum(r["r"] for r in test)/len(test)
        if tr>0 and te>0: cls="TRAIN_POS_TEST_POS"
        elif tr>0: cls="TRAIN_POS_TEST_NONPOS"
        elif te>0: cls="TRAIN_NONPOS_TEST_POS"
        else: cls="TRAIN_NONPOS_TEST_NONPOS"
    else:
        tr=te=None; cls="INSUFFICIENT_RESOLVED"
    return {"resolved":resolved,"eligible":eligible,"train":train,"test":test,"split_time":split_time,
            "train_mean":tr,"test_mean":te,"full_mean":full_mean,"class":cls}

def ts_stats(rows):
    if not rows: return (0,0,None,None)
    tp=sum(1 for r in rows if r["outcome"]=="TP")
    sl=sum(1 for r in rows if r["outcome"]=="SL")
    rate=tp/(tp+sl) if tp+sl else None
    mean=sum(r["r"] for r in rows)/len(rows)
    return tp,sl,rate,mean

def make_split_row(sym,side,total_signals,m):
    tr_tp,tr_sl,tr_rate,_=ts_stats(m["train"])
    te_tp,te_sl,te_rate,_=ts_stats(m["test"])
    return {
        "SYMBOL":sym,"SIDE":side,"TOTAL_SIGNALS":total_signals,"RESOLVED":len(m["resolved"]),
        "TRAIN_N":len(m["train"]),"TEST_N":len(m["test"]),"SPLIT_TIME":m["split_time"],
        "SPLIT_UTC":utc_text(m["split_time"]),"TRAIN_TP":tr_tp,"TRAIN_SL":tr_sl,"TEST_TP":te_tp,"TEST_SL":te_sl,
        "TRAIN_TP_RATE":fmt(tr_rate),"TEST_TP_RATE":fmt(te_rate),"TRAIN_MEAN_R":fmt(m["train_mean"]),
        "TEST_MEAN_R":fmt(m["test_mean"]),"FULL_MEAN_R":fmt(m["full_mean"]),
        "STABILITY_CLASS":m["class"],"ELIGIBLE":"YES" if m["eligible"] else "NO"
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--short-root",type=Path,required=True)
    ap.add_argument("--long-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    short=load_root(a.short_root,"SHORT")
    long=load_root(a.long_root,"LONG")
    symbols=sorted(set(short)|set(long),key=lambda x:(x.casefold(),x))
    if len(symbols)!=522:
        raise SystemExit(f"expected 522 processed symbols, got {len(symbols)}")

    side_rows=[]; year_rows=[]; symbol_rows=[]
    side_classes={"SHORT":Counter(),"LONG":Counter()}
    symbol_classes=Counter()
    counts=Counter()

    for sym in symbols:
        all_records=[]
        total_signals=0
        for side,src in [("SHORT",short),("LONG",long)]:
            recs=src.get(sym,[])
            total_signals+=len(recs); all_records.extend(recs)
            counts[f"{side.lower()}_signals"]+=len(recs)
            counts[f"{side.lower()}_resolved"]+=sum(1 for r in recs if r["outcome"] in ("TP","SL") and r["r"] is not None)
            m=metrics(recs)
            side_rows.append(make_split_row(sym,side,len(recs),m))
            side_classes[side][m["class"]]+=1

            by_year=defaultdict(list)
            for r in m["resolved"]:
                y=datetime.fromtimestamp(r["entry_time"],tz=timezone.utc).year
                by_year[y].append(r)
            for y in sorted(by_year):
                rr=by_year[y]
                tp,sl,rate,mean=ts_stats(rr)
                year_rows.append({"SYMBOL":sym,"SIDE":side,"YEAR":y,"RESOLVED":len(rr),"TP":tp,"SL":sl,
                                  "TP_RATE":fmt(rate),"MEAN_R":fmt(mean)})

        all_records.sort(key=lambda x:x["entry_time"])
        cm=metrics(all_records)
        row=make_split_row(sym,"BOTH",total_signals,cm)
        symbol_rows.append({k:row[k] for k in SYMBOL_FIELDS})
        symbol_classes[cm["class"]]+=1

    counts["combined_signals"]=counts["short_signals"]+counts["long_signals"]
    counts["combined_resolved"]=counts["short_resolved"]+counts["long_resolved"]
    if counts["short_signals"]!=63891 or counts["long_signals"]!=74202:
        raise SystemExit(f"input signal count mismatch: short={counts['short_signals']} long={counts['long_signals']}")
    if counts["short_resolved"]!=63721 or counts["long_resolved"]!=74012:
        raise SystemExit(f"input resolved count mismatch: short={counts['short_resolved']} long={counts['long_resolved']}")

    summary={
        "block":"DRUMMOND TEMPORAL STABILITY 07",
        "status":"PASS",
        "dataset_id":"DRUMMOND_CANONICAL_8E9A1D784E3893D9",
        "method":{
            "population":"resolved TP/SL lifecycle outcomes with numeric LEVEL_R",
            "split":"per series chronological 70/30, with latest ceil(30%) as TEST and minimum 10 TEST observations",
            "eligibility":"at least 30 resolved observations in the series",
            "selection":"none; descriptive stability audit only"
        },
        "counts":dict(counts),
        "side_classes":{k:dict(sorted(v.items())) for k,v in side_classes.items()},
        "combined_symbol_classes":dict(sorted(symbol_classes.items())),
        "files":{"side_split_rows":len(side_rows),"year_rows":len(year_rows),"symbol_split_rows":len(symbol_rows)}
    }
    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"FACTORY07_SIDE_SPLIT.csv",SIDE_FIELDS,side_rows)
    write_csv(a.out/"FACTORY07_YEARLY.csv",YEAR_FIELDS,year_rows)
    write_csv(a.out/"FACTORY07_SYMBOL_SPLIT.csv",SYMBOL_FIELDS,symbol_rows)
    (a.out/"FACTORY07_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=[
        "DRUMMOND TEMPORAL STABILITY 07","STATUS: PASS",f"DATASET: {summary['dataset_id']}",
        f"SHORT SIGNALS/RESOLVED: {counts['short_signals']}/{counts['short_resolved']}",
        f"LONG SIGNALS/RESOLVED: {counts['long_signals']}/{counts['long_resolved']}",
        f"COMBINED SIGNALS/RESOLVED: {counts['combined_signals']}/{counts['combined_resolved']}",
        f"SHORT CLASSES: {summary['side_classes']['SHORT']}",f"LONG CLASSES: {summary['side_classes']['LONG']}",
        f"COMBINED SYMBOL CLASSES: {summary['combined_symbol_classes']}",
        "SELECTION: NOT PERFORMED","NEXT: DEFINE TRAIN-ONLY EDGE RULES, THEN READ TEST AS OOS"
    ]
    (a.out/"FACTORY07_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
