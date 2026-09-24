#!/usr/bin/env python3
import argparse,csv,json,math
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

FIELDS=["DIMENSION","SIDE","BIN","N","TP","SL","TP_RATE","MEAN_R","POSITIVE_MEAN_R"]

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";")
        w.writeheader(); w.writerows(rows)

def rr_bin(x):
    if x<1.00: return "0.75-1.00"
    if x<1.25: return "1.00-1.25"
    if x<1.50: return "1.25-1.50"
    return "1.50-1.75"

def spread_risk_bin(x):
    if x<0.01: return "<1%"
    if x<0.02: return "1-2%"
    if x<0.05: return "2-5%"
    return ">=5%"

def risk_pct_bin(x):
    if x<0.0025: return "<0.25%"
    if x<0.0050: return "0.25-0.50%"
    if x<0.0100: return "0.50-1.00%"
    return ">=1.00%"

def utc6_bin(hour):
    if hour<6: return "00-05"
    if hour<12: return "06-11"
    if hour<18: return "12-17"
    return "18-23"

def weekday_bin(ts):
    return ("MON","TUE","WED","THU","FRI","SAT","SUN")[datetime.fromtimestamp(ts,tz=timezone.utc).weekday()]

def load_train(root,expected_side):
    train=[]
    files=sorted(Path(root).rglob("*_FACTORY02_LIFECYCLE.csv"))
    seen=set()
    series_total=series_eligible=0
    for lp in files:
        sym=lp.name[:-len("_FACTORY02_LIFECYCLE.csv")]
        if sym in seen: raise SystemExit(f"duplicate lifecycle symbol {expected_side} {sym}")
        seen.add(sym); series_total+=1
        sp=lp.parent/"replay01"/f"{sym}_REPLAY_SIGNALS.csv"
        jp=lp.parent/"replay01"/f"{sym}_REPLAY_SUMMARY.json"
        if not sp.exists() or not jp.exists():
            raise SystemExit(f"missing replay evidence for {sym}")
        summary=json.loads(jp.read_text(encoding="utf-8"))
        point=float(summary["data"]["M5"]["point"])
        signals={r["SIGNAL_ID"]:r for r in read_csv(sp)}
        life=read_csv(lp)
        joined=[]
        for r in life:
            if r["SIDE"]!=expected_side:
                raise SystemExit(f"unexpected side for {sym}: {r['SIDE']}")
            if r["OUTCOME"] not in ("TP","SL") or r.get("LEVEL_R") in ("",None):
                continue
            sig=signals.get(r["SIGNAL_ID"])
            if sig is None: raise SystemExit(f"signal join failure {sym} {r['SIGNAL_ID']}")
            entry=float(sig["ENTRY_REFERENCE"]); stop=float(sig["STOP_PRICE"])
            risk=abs(entry-stop)
            if entry<=0 or risk<=0 or point<=0: raise SystemExit(f"invalid geometry {sym} {r['SIGNAL_ID']}")
            used_sp=max(0,int(float(sig["USED_SPREAD_POINTS"])))
            joined.append({
                "symbol":sym,"side":expected_side,"entry_time":int(r["ENTRY_TIME"]),
                "outcome":r["OUTCOME"],"r":float(r["LEVEL_R"]),"rr":float(sig["RR"]),
                "risk_pct":risk/entry,"spread_risk":(used_sp*point)/risk
            })
        joined.sort(key=lambda x:x["entry_time"])
        n=len(joined)
        if n<30: continue
        series_eligible+=1
        test_n=max(10,math.ceil(n*0.30))
        train.extend(joined[:n-test_n])
    return train,series_total,series_eligible

def add(agg,dim,side,bin_name,row):
    k=(dim,side,bin_name)
    x=agg[k]
    x["N"]+=1
    x[row["outcome"]]+=1
    x["R_SUM"]+=row["r"]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--short-root",type=Path,required=True)
    ap.add_argument("--long-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    short,short_total,short_eligible=load_train(a.short_root,"SHORT")
    long,long_total,long_eligible=load_train(a.long_root,"LONG")
    rows=short+long
    agg=defaultdict(lambda:{"N":0,"TP":0,"SL":0,"R_SUM":0.0})

    for r in rows:
        dt=datetime.fromtimestamp(r["entry_time"],tz=timezone.utc)
        dims={
            "RR":rr_bin(r["rr"]),
            "SPREAD_RISK":spread_risk_bin(r["spread_risk"]),
            "RISK_PCT":risk_pct_bin(r["risk_pct"]),
            "UTC_6H":utc6_bin(dt.hour),
            "WEEKDAY":weekday_bin(r["entry_time"])
        }
        for dim,b in dims.items():
            add(agg,dim,r["side"],b,r)
            add(agg,dim,"BOTH",b,r)

    out=[]
    positive_ge500=[]
    for (dim,side,b),x in sorted(agg.items()):
        n=x["N"]; rate=x["TP"]/n if n else None; mean=x["R_SUM"]/n if n else None
        row={"DIMENSION":dim,"SIDE":side,"BIN":b,"N":n,"TP":x["TP"],"SL":x["SL"],
             "TP_RATE":f"{rate:.8f}","MEAN_R":f"{mean:.8f}",
             "POSITIVE_MEAN_R":"YES" if mean>0 else "NO"}
        out.append(row)
        if side=="BOTH" and n>=500 and mean>0:
            positive_ge500.append({"dimension":dim,"bin":b,"n":n,"mean_r":mean,"tp_rate":rate})

    summary={
        "block":"DRUMMOND TRAIN-ONLY FEATURE DIAGNOSIS 09",
        "status":"PASS",
        "dataset_id":"DRUMMOND_CANONICAL_8E9A1D784E3893D9",
        "population":{
            "short_series_total":short_total,"short_series_eligible":short_eligible,
            "long_series_total":long_total,"long_series_eligible":long_eligible,
            "short_train_resolved":len(short),"long_train_resolved":len(long),
            "combined_train_resolved":len(rows)
        },
        "features":{
            "RR":"fixed bins 0.75-1.00/1.00-1.25/1.25-1.50/1.50-1.75",
            "SPREAD_RISK":"used spread price divided by initial structural risk",
            "RISK_PCT":"initial structural risk divided by entry price",
            "UTC_6H":"four fixed UTC six-hour windows",
            "WEEKDAY":"UTC weekday"
        },
        "leakage_guard":{
            "test_rows_used":False,
            "post_entry_features_used":False,
            "forbidden_as_predictors":["TRAIL_UPDATES","M5_BARS","CLOSE_TIME","OUTCOME_PATH"],
            "selection":"none; diagnostic table only"
        },
        "positive_both_side_bins_n_ge_500":positive_ge500,
        "next_required_gate":"Freeze any proposed entry-observable bin rule before evaluating it on TEST."
    }
    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"FACTORY09_TRAIN_FEATURE_BINS.csv",out)
    (a.out/"FACTORY09_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=[
        "DRUMMOND TRAIN-ONLY FEATURE DIAGNOSIS 09","STATUS: PASS",
        f"DATASET: {summary['dataset_id']}",
        f"SHORT ELIGIBLE SERIES/TRAIN RESOLVED: {short_eligible}/{len(short)}",
        f"LONG ELIGIBLE SERIES/TRAIN RESOLVED: {long_eligible}/{len(long)}",
        f"COMBINED TRAIN RESOLVED: {len(rows)}",
        "TEST ROWS USED: NO","POST-ENTRY FEATURES USED: NO",
        f"POSITIVE BOTH-SIDE BINS N>=500: {positive_ge500}",
        "SELECTION: NOT PERFORMED",
        "NEXT: FREEZE FEATURE RULE, THEN TEST IT"
    ]
    (a.out/"FACTORY09_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
