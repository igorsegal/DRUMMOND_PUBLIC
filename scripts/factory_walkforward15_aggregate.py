#!/usr/bin/env python3
import argparse,bisect,csv,json,statistics
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

EVENT_FIELDS=[
    "SYMBOL","SIGNAL_ID","ENTRY_TIME","OUTCOME","LEVEL_R",
    "ENTRY_REFERENCE","STOP_PRICE","DECISION_PLDOT","ENTRY_PLDOT_R",
    "SERIES_RESOLVED_N","ELIGIBLE30"
]
FOLD_FIELDS=[
    "SCHEME","FOLD","IS_START","IS_END","OOS_START","OOS_END",
    "IS_N","IS_TP","IS_SL","IS_TP_RATE","IS_MEAN_R","IS_SYMBOLS",
    "OOS_N","OOS_TP","OOS_SL","OOS_TP_RATE","OOS_MEAN_R","OOS_SYMBOLS",
    "IS_SIGN","OOS_SIGN","TRANSITION"
]
SCHEME_FIELDS=[
    "SCHEME","IS_HALFMONTHS","OOS_HALFMONTHS","FOLDS","OOS_NONEMPTY",
    "OOS_N_TOTAL","OOS_TP","OOS_SL","OOS_TP_RATE","POOLED_OOS_MEAN_R",
    "MEDIAN_FOLD_OOS_MEAN_R","POSITIVE_OOS_FOLDS","NONPOSITIVE_OOS_FOLDS",
    "POSITIVE_OOS_FOLD_RATE","N10_FOLDS","N10_POSITIVE","N10_POSITIVE_RATE",
    "N20_FOLDS","N20_POSITIVE","N20_POSITIVE_RATE",
    "WORST_OOS_MEAN_R","BEST_OOS_MEAN_R","WORST_N10_OOS_MEAN_R","BEST_N10_OOS_MEAN_R",
    "IS_POS_OOS_POS","IS_POS_OOS_NONPOS","IS_NONPOS_OOS_POS","IS_NONPOS_OOS_NONPOS"
]

SCHEMES=[
    ("1M_IS__2W_OOS",2,1),
    ("2M_IS__1M_OOS",4,2),
    ("3M_IS__1.5M_OOS",6,3),
    ("4M_IS__2M_OOS",8,4),
    ("5M_IS__2.5M_OOS",10,5),
    ("6M_IS__3M_OOS",12,6),
]

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";")
        w.writeheader();w.writerows(rows)

def next_half(dt):
    if dt.day==1:
        return datetime(dt.year,dt.month,16,tzinfo=timezone.utc)
    if dt.month==12:
        return datetime(dt.year+1,1,1,tzinfo=timezone.utc)
    return datetime(dt.year,dt.month+1,1,tzinfo=timezone.utc)

def iso(ts):
    return datetime.fromtimestamp(ts,tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def metric(rows):
    n=len(rows)
    if not n:
        return {"n":0,"tp":0,"sl":0,"rate":None,"mean":None,"symbols":0}
    tp=sum(r["OUTCOME"]=="TP" for r in rows)
    sl=sum(r["OUTCOME"]=="SL" for r in rows)
    return {
        "n":n,"tp":tp,"sl":sl,
        "rate":tp/(tp+sl) if tp+sl else None,
        "mean":sum(float(r["LEVEL_R"]) for r in rows)/n,
        "symbols":len({r["SYMBOL"] for r in rows})
    }

def fmt(x):
    return "" if x is None else f"{x:.8f}"

def sign(x):
    if x is None:return "EMPTY"
    return "POS" if x>0 else "NONPOS"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--artifact-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    csvs=sorted(a.artifact_root.rglob("FACTORY15_C01_EVENTS.csv"))
    sums=sorted(a.artifact_root.rglob("FACTORY15_SHARD_SUMMARY.json"))
    if len(csvs)!=7 or len(sums)!=7:
        raise SystemExit(f"expected 7 shard outputs, got csv={len(csvs)} summary={len(sums)}")

    rows=[];seen=set();resolved_total=0;processed_total=0
    for p in csvs:
        for r in read_csv(p):
            key=r["SIGNAL_ID"]
            if key in seen: raise SystemExit(f"duplicate C01 signal {key}")
            seen.add(key);rows.append(r)
    for p in sums:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s.get("status")!="PASS" or s.get("rule_modified"):
            raise SystemExit(f"bad shard summary {p}")
        resolved_total+=int(s["resolved_long_population"])
        processed_total+=int(s["processed_symbols"])
    if resolved_total!=74012:
        raise SystemExit(f"resolved LONG population mismatch: {resolved_total}")

    rows.sort(key=lambda r:(int(r["ENTRY_TIME"]),r["SYMBOL"].casefold(),r["SIGNAL_ID"]))
    if not rows: raise SystemExit("no C01 events")

    min_ts=int(rows[0]["ENTRY_TIME"]);max_ts=int(rows[-1]["ENTRY_TIME"])
    min_year=datetime.fromtimestamp(min_ts,tz=timezone.utc).year
    anchor=datetime(min_year,1,1,tzinfo=timezone.utc)
    bounds=[anchor]
    while int(bounds[-1].timestamp())<=max_ts:
        bounds.append(next_half(bounds[-1]))
    bt=[int(x.timestamp()) for x in bounds]
    periods=len(bt)-1

    by_period=defaultdict(list)
    for r in rows:
        idx=bisect.bisect_right(bt,int(r["ENTRY_TIME"]))-1
        if idx<0 or idx>=periods:
            raise SystemExit("event outside half-month grid")
        by_period[idx].append(r)

    folds=[];scheme_rows=[];scheme_json={}
    for name,is_u,oos_u in SCHEMES:
        local=[];fold_no=0
        start=0
        while start+is_u+oos_u<=periods:
            is_end=start+is_u;oos_end=is_end+oos_u
            ir=[];orr=[]
            for k in range(start,is_end):ir.extend(by_period.get(k,[]))
            for k in range(is_end,oos_end):orr.extend(by_period.get(k,[]))
            im=metric(ir);om=metric(orr)
            is_s=sign(im["mean"]);oos_s=sign(om["mean"])
            transition=f"{is_s}->{oos_s}"
            fold_no+=1
            rec={
                "SCHEME":name,"FOLD":fold_no,
                "IS_START":bounds[start].strftime("%Y-%m-%d"),
                "IS_END":bounds[is_end].strftime("%Y-%m-%d"),
                "OOS_START":bounds[is_end].strftime("%Y-%m-%d"),
                "OOS_END":bounds[oos_end].strftime("%Y-%m-%d"),
                "IS_N":im["n"],"IS_TP":im["tp"],"IS_SL":im["sl"],
                "IS_TP_RATE":fmt(im["rate"]),"IS_MEAN_R":fmt(im["mean"]),"IS_SYMBOLS":im["symbols"],
                "OOS_N":om["n"],"OOS_TP":om["tp"],"OOS_SL":om["sl"],
                "OOS_TP_RATE":fmt(om["rate"]),"OOS_MEAN_R":fmt(om["mean"]),"OOS_SYMBOLS":om["symbols"],
                "IS_SIGN":is_s,"OOS_SIGN":oos_s,"TRANSITION":transition
            }
            folds.append(rec);local.append((rec,orr))
            start+=oos_u

        nonempty=[x for x,_ in local if int(x["OOS_N"])>0]
        oos_means=[float(x["OOS_MEAN_R"]) for x in nonempty]
        pooled_rows=[]
        for rec,rr in local:
            pooled_rows.extend(rr)
        pm=metric(pooled_rows)
        pos=sum(float(x["OOS_MEAN_R"])>0 for x in nonempty)
        n10=[x for x in nonempty if int(x["OOS_N"])>=10]
        n20=[x for x in nonempty if int(x["OOS_N"])>=20]
        trans=Counter(x["TRANSITION"] for x in nonempty if x["IS_SIGN"]!="EMPTY")
        sr={
            "SCHEME":name,"IS_HALFMONTHS":is_u,"OOS_HALFMONTHS":oos_u,
            "FOLDS":len(local),"OOS_NONEMPTY":len(nonempty),
            "OOS_N_TOTAL":pm["n"],"OOS_TP":pm["tp"],"OOS_SL":pm["sl"],
            "OOS_TP_RATE":fmt(pm["rate"]),"POOLED_OOS_MEAN_R":fmt(pm["mean"]),
            "MEDIAN_FOLD_OOS_MEAN_R":fmt(statistics.median(oos_means) if oos_means else None),
            "POSITIVE_OOS_FOLDS":pos,"NONPOSITIVE_OOS_FOLDS":len(nonempty)-pos,
            "POSITIVE_OOS_FOLD_RATE":fmt(pos/len(nonempty) if nonempty else None),
            "N10_FOLDS":len(n10),"N10_POSITIVE":sum(float(x["OOS_MEAN_R"])>0 for x in n10),
            "N10_POSITIVE_RATE":fmt(sum(float(x["OOS_MEAN_R"])>0 for x in n10)/len(n10) if n10 else None),
            "N20_FOLDS":len(n20),"N20_POSITIVE":sum(float(x["OOS_MEAN_R"])>0 for x in n20),
            "N20_POSITIVE_RATE":fmt(sum(float(x["OOS_MEAN_R"])>0 for x in n20)/len(n20) if n20 else None),
            "WORST_OOS_MEAN_R":fmt(min(oos_means) if oos_means else None),
            "BEST_OOS_MEAN_R":fmt(max(oos_means) if oos_means else None),
            "WORST_N10_OOS_MEAN_R":fmt(min(float(x["OOS_MEAN_R"]) for x in n10) if n10 else None),
            "BEST_N10_OOS_MEAN_R":fmt(max(float(x["OOS_MEAN_R"]) for x in n10) if n10 else None),
            "IS_POS_OOS_POS":trans["POS->POS"],
            "IS_POS_OOS_NONPOS":trans["POS->NONPOS"],
            "IS_NONPOS_OOS_POS":trans["NONPOS->POS"],
            "IS_NONPOS_OOS_NONPOS":trans["NONPOS->NONPOS"],
        }
        scheme_rows.append(sr)
        scheme_json[name]=sr

    full=metric(rows)
    eligible=[r for r in rows if r["ELIGIBLE30"]=="YES"]
    elig=metric(eligible)
    summary={
        "block":"DRUMMOND C01 MULTI-WINDOW WALK-FORWARD ATLAS 15",
        "status":"PASS",
        "dataset_id":"DRUMMOND_CANONICAL_8E9A1D784E3893D9",
        "frozen_candidate_sha256":"a9a00478647d73e147ee0c7e7a063adc5b0fe96b97d403b81af49b3937a57b3e",
        "rule":"LONG base signal AND ENTRY_PLDOT_R < 0",
        "rule_modified":False,
        "window_definition":{
            "unit":"calendar half-month",
            "first_half":"day 1 through day 15",
            "second_half":"day 16 through next month day 1",
            "anchor_utc":anchor.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "oos_overlap_within_scheme":False,
            "step":"exactly one OOS window",
            "is_oos_ratio":"2:1 for all six schemes"
        },
        "history":{
            "resolved_long_population":resolved_total,
            "c01_events":full["n"],"c01_symbols":full["symbols"],
            "c01_tp":full["tp"],"c01_sl":full["sl"],"c01_tp_rate":full["rate"],"c01_mean_r":full["mean"],
            "eligible30_c01_events":elig["n"],"eligible30_c01_symbols":elig["symbols"],
            "first_event_utc":iso(min_ts),"last_event_utc":iso(max_ts),
            "halfmonth_periods":periods
        },
        "schemes":scheme_json,
        "interpretation":{
            "is_refits_rule":False,
            "is_purpose":"measure immediately preceding historical regime for the already frozen C01 rule",
            "oos_purpose":"measure subsequent non-overlapping persistence of the same frozen C01 rule",
            "selection_or_optimization_performed":False,
            "future_wait_required":False
        }
    }

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"FACTORY15_C01_EVENTS.csv",EVENT_FIELDS,rows)
    write_csv(a.out/"FACTORY15_FOLDS.csv",FOLD_FIELDS,folds)
    write_csv(a.out/"FACTORY15_SCHEMES.csv",SCHEME_FIELDS,scheme_rows)
    (a.out/"FACTORY15_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=[
        "DRUMMOND C01 MULTI-WINDOW WALK-FORWARD ATLAS 15","STATUS: PASS",
        f"HISTORY: {summary['history']['first_event_utc']} -> {summary['history']['last_event_utc']}",
        f"C01 EVENTS/SYMBOLS: {full['n']}/{full['symbols']}",
        f"FULL C01 MEAN_R: {full['mean']:.8f}",
        "WINDOW UNIT: CALENDAR HALF-MONTH; OOS NON-OVERLAPPING WITHIN EACH SCHEME",
        "RULE MODIFIED: NO"
    ]
    for s in scheme_rows:
        lines.append(
            f"{s['SCHEME']}: folds={s['FOLDS']} oosN={s['OOS_N_TOTAL']} "
            f"meanR={s['POOLED_OOS_MEAN_R']} positive={s['POSITIVE_OOS_FOLDS']}/{s['OOS_NONEMPTY']} "
            f"N10positive={s['N10_POSITIVE']}/{s['N10_FOLDS']}"
        )
    (a.out/"FACTORY15_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
