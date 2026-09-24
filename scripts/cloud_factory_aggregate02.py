#!/usr/bin/env python3
import argparse,csv,json
from pathlib import Path

FIELDS=["SYMBOL","STATUS","DECISIONS","SIGNALS","TP","SL","AMBIGUOUS","OPEN_AT_DATA_END","SIGNAL_SHA256","ERROR","SHARD"]

def read_semicolon(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_semicolon(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";")
        w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--artifact-root",type=Path,required=True,
                    help="Root produced by actions/download-artifact for shard artifacts")
    ap.add_argument("--manifest",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    m=json.loads(a.manifest.read_text(encoding="utf-8"))
    wanted={s["symbol"]:s for s in m["symbol_status"]}
    rows_by_symbol={}
    shard_summaries=[]

    for p in sorted(a.artifact_root.rglob("FACTORY01_SYMBOLS.csv")):
        shard=p.parent.parent.name
        rows=read_semicolon(p)
        summary_path=p.parent/"FACTORY01_SUMMARY.json"
        if summary_path.exists():
            s=json.loads(summary_path.read_text(encoding="utf-8"))
            shard_summaries.append({"shard":shard,**s.get("counts",{})})
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
    totals={"DECISIONS":0,"SIGNALS":0,"TP":0,"SL":0,"AMBIGUOUS":0,"OPEN_AT_DATA_END":0}
    skip_counts={}
    for sym in [s["symbol"] for s in m["symbol_status"]]:
        declared=wanted[sym]["status"]
        if sym in rows_by_symbol:
            r=rows_by_symbol[sym]
            if declared=="READY" and r["STATUS"]!="PROCESSED":
                raise SystemExit(f"READY symbol not processed: {sym} -> {r['STATUS']}")
            if r["STATUS"]=="PROCESSED":
                processed+=1
                for k in totals: totals[k]+=int(r[k] or 0)
            elif r["STATUS"]=="ERROR":
                errors+=1
            else:
                skip_counts[r["STATUS"]]=skip_counts.get(r["STATUS"],0)+1
            final.append({k:r.get(k,"") for k in FIELDS})
        else:
            # Symbols with no available files never appear in shard Factory output.
            if declared=="READY":
                raise SystemExit(f"READY symbol missing from shard results: {sym}")
            skip_counts[declared]=skip_counts.get(declared,0)+1
            final.append({"SYMBOL":sym,"STATUS":declared,"DECISIONS":"","SIGNALS":"","TP":"","SL":"",
                          "AMBIGUOUS":"","OPEN_AT_DATA_END":"","SIGNAL_SHA256":"","ERROR":"","SHARD":""})

    a.out.mkdir(parents=True,exist_ok=True)
    write_semicolon(a.out/"FACTORY02_SYMBOLS.csv",final)
    summary={
      "block":"CLOUD DATA BRIDGE SCALE 02 AGGREGATE",
      "status":"PASS" if errors==0 else "FAIL",
      "dataset_id":m["dataset_id"],
      "counts":{"selected_symbols":len(m["symbol_status"]),"processed":processed,"errors":errors,
                "shards_expected":len(m["shards"]),"shard_results":len(shard_summaries),
                "decisions":totals["DECISIONS"],"signals":totals["SIGNALS"],"TP":totals["TP"],
                "SL":totals["SL"],"AMBIGUOUS_SAME_M5":totals["AMBIGUOUS"],
                "OPEN_AT_DATA_END":totals["OPEN_AT_DATA_END"],"skips":skip_counts},
      "shards":shard_summaries
    }
    if len(shard_summaries)!=len(m["shards"]):
        summary["status"]="FAIL"
        summary["error"]="missing shard result artifacts"
    (a.out/"FACTORY02_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["CLOUD DATA BRIDGE SCALE 02 AGGREGATE",f"STATUS: {summary['status']}",
           f"DATASET: {m['dataset_id']}",f"SHARDS: {len(shard_summaries)}/{len(m['shards'])}",
           f"SELECTED: {len(m['symbol_status'])}",f"PROCESSED: {processed}",f"ERRORS: {errors}",
           f"SKIPS: {skip_counts}",f"DECISIONS: {totals['DECISIONS']}",f"SIGNALS: {totals['SIGNALS']}",
           f"TP/SL/AMBIGUOUS/OPEN: {totals['TP']}/{totals['SL']}/{totals['AMBIGUOUS']}/{totals['OPEN_AT_DATA_END']}"]
    (a.out/"FACTORY02_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
    raise SystemExit(0 if summary["status"]=="PASS" else 2)

if __name__=="__main__":
    main()
