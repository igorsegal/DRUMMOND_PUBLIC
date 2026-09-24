#!/usr/bin/env python3
import argparse,csv,json
from pathlib import Path

FIELDS=["SYMBOL","STATUS","SIGNALS","TP","SL","AMBIGUOUS","OPEN","TRAIL_UPDATES",
        "TP_RATE_RESOLVED","MEAN_LEVEL_R","LIFECYCLE_SHA256","ERROR","SHARD"]

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";")
        w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--artifact-root",type=Path,required=True)
    ap.add_argument("--manifest",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    m=json.loads(a.manifest.read_text(encoding="utf-8"))
    wanted={s["symbol"]:s for s in m["symbol_status"]}
    order=[s["symbol"] for s in m["symbol_status"]]
    rows_by_symbol={}
    shard_summaries=[]

    for p in sorted(a.artifact_root.rglob("FACTORY02_SYMBOLS.csv")):
        shard=p.parent.parent.name
        rows=read_csv(p)
        sp=p.parent/"FACTORY02_SUMMARY.json"
        if sp.exists():
            s=json.loads(sp.read_text(encoding="utf-8"))
            shard_summaries.append({
                "shard":shard,
                "status":s.get("status"),
                **s.get("counts",{}),
                "tp_rate_resolved":s.get("tp_rate_resolved"),
                "mean_level_r_resolved":s.get("mean_level_r_resolved"),
            })
        for r in rows:
            sym=r["SYMBOL"]
            if sym in rows_by_symbol:
                raise SystemExit(f"duplicate symbol across shard results: {sym}")
            if sym not in wanted:
                raise SystemExit(f"unexpected symbol in shard results: {sym}")
            r["SHARD"]=shard
            rows_by_symbol[sym]=r

    final=[]
    processed=errors=0
    skips={}
    totals={"SIGNALS":0,"TP":0,"SL":0,"AMBIGUOUS":0,"OPEN":0,"TRAIL_UPDATES":0}
    weighted_r_sum=0.0
    weighted_r_n=0

    for sym in order:
        declared=wanted[sym]["status"]
        if sym in rows_by_symbol:
            r=rows_by_symbol[sym]
            status=r["STATUS"]
            if declared=="READY" and status!="PROCESSED":
                raise SystemExit(f"READY symbol not processed: {sym} -> {status}")
            if status=="PROCESSED":
                processed+=1
                for k in totals:
                    totals[k]+=int(r.get(k) or 0)
                resolved=int(r.get("TP") or 0)+int(r.get("SL") or 0)
                mr=r.get("MEAN_LEVEL_R","")
                if resolved>0 and mr not in ("",None):
                    weighted_r_sum+=float(mr)*resolved
                    weighted_r_n+=resolved
            elif status=="ERROR":
                errors+=1
            else:
                skips[status]=skips.get(status,0)+1
            final.append({k:r.get(k,"") for k in FIELDS})
        else:
            if declared=="READY":
                raise SystemExit(f"READY symbol missing from Factory 02 shard results: {sym}")
            skips[declared]=skips.get(declared,0)+1
            final.append({
                "SYMBOL":sym,"STATUS":declared,"SIGNALS":"","TP":"","SL":"","AMBIGUOUS":"",
                "OPEN":"","TRAIL_UPDATES":"","TP_RATE_RESOLVED":"","MEAN_LEVEL_R":"",
                "LIFECYCLE_SHA256":"","ERROR":"","SHARD":""
            })

    resolved=totals["TP"]+totals["SL"]
    tp_rate=totals["TP"]/resolved if resolved else None
    mean_r=weighted_r_sum/weighted_r_n if weighted_r_n else None

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"FACTORY05_SYMBOLS.csv",final)

    summary={
        "block":"CLOUD FACTORY 02 FULL 05 AGGREGATE",
        "status":"PASS" if errors==0 and len(shard_summaries)==len(m["shards"]) else "FAIL",
        "dataset_id":m["dataset_id"],
        "counts":{
            "selected_symbols":len(order),
            "processed":processed,
            "errors":errors,
            "shards_expected":len(m["shards"]),
            "shard_results":len(shard_summaries),
            "signals":totals["SIGNALS"],
            "TP":totals["TP"],
            "SL":totals["SL"],
            "AMBIGUOUS_SAME_M5":totals["AMBIGUOUS"],
            "OPEN_AT_DATA_END":totals["OPEN"],
            "trail_updates":totals["TRAIL_UPDATES"],
            "skips":skips,
        },
        "tp_rate_resolved":tp_rate,
        "mean_level_r_resolved":mean_r,
        "shards":shard_summaries,
        "policy":{
            "engine":"cloud_factory02.py",
            "missing_m5":"SKIP_NO_M5, never fail",
            "ambiguous_same_bar":"never guess winner",
            "broker_specific":"stop/freeze and OrderModify acceptance remain MT4 validation concerns"
        }
    }

    (a.out/"FACTORY05_SUMMARY.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
    )
    lines=[
        "CLOUD FACTORY 02 FULL 05 AGGREGATE",
        f"STATUS: {summary['status']}",
        f"DATASET: {m['dataset_id']}",
        f"SHARDS: {len(shard_summaries)}/{len(m['shards'])}",
        f"SELECTED: {len(order)}",
        f"PROCESSED: {processed}",
        f"ERRORS: {errors}",
        f"SKIPS: {skips}",
        f"SIGNALS: {totals['SIGNALS']}",
        f"TP/SL/AMBIGUOUS/OPEN: {totals['TP']}/{totals['SL']}/{totals['AMBIGUOUS']}/{totals['OPEN']}",
        f"TRAIL UPDATES: {totals['TRAIL_UPDATES']}",
        f"TP RATE RESOLVED: {tp_rate:.8f}" if tp_rate is not None else "TP RATE RESOLVED: N/A",
        f"MEAN LEVEL R RESOLVED: {mean_r:.8f}" if mean_r is not None else "MEAN LEVEL R RESOLVED: N/A",
    ]
    (a.out/"FACTORY05_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
    raise SystemExit(0 if summary["status"]=="PASS" else 2)

if __name__=="__main__":
    main()
