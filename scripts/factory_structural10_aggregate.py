#!/usr/bin/env python3
import argparse,csv,json
from collections import Counter
from pathlib import Path

FIELDS=[
    "SYMBOL","SIDE","SIGNAL_ID","ENTRY_TIME","OUTCOME","LEVEL_R","RR",
    "STOP_SOURCE","TARGET_SOURCE",
    "ENTRY_PLDOT_R","H1_PLDOT_SLOPE_R",
    "H4_ENTRY_PLDOT_R","H4_PLDOT_SLOPE_R",
    "REFRESH_PENETRATION_R","REFRESH_RECLAIM_R",
    "H1_RANGE_R","H1_BODY_R","SPREAD_RISK","INITIAL_RISK_PCT"
]

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";")
        w.writeheader(); w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--artifact-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    csvs=sorted(a.artifact_root.rglob("FACTORY10_TRAIN_STRUCTURAL_FEATURES.csv"))
    sums=sorted(a.artifact_root.rglob("FACTORY10_SUMMARY.json"))
    if len(csvs)!=7 or len(sums)!=7:
        raise SystemExit(f"expected 7 shard CSV/summary files, got csv={len(csvs)} summary={len(sums)}")

    rows=[]; seen=set(); side=Counter(); combos=Counter()
    eligible=Counter(); resolved=Counter()
    for p in csvs:
        for r in read_csv(p):
            key=(r["SIDE"],r["SIGNAL_ID"])
            if key in seen:
                raise SystemExit(f"duplicate structural row {key}")
            seen.add(key)
            if r["SIDE"] not in ("SHORT","LONG"):
                raise SystemExit(f"bad side {r['SIDE']}")
            if r["STOP_SOURCE"] not in ("L51","L52","L59") or r["TARGET_SOURCE"] not in ("L51","L52","L59"):
                raise SystemExit(f"bad structural source {key}")
            if r["OUTCOME"] not in ("TP","SL"):
                raise SystemExit(f"non-resolved TRAIN row {key}")
            rows.append(r)
            side[r["SIDE"]]+=1
            combos[(r["SIDE"],r["STOP_SOURCE"],r["TARGET_SOURCE"])]+=1

    for p in sums:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s.get("status")!="PASS":
            raise SystemExit(f"shard summary not PASS: {p}")
        g=s["leakage_guard"]
        if g.get("test_rows_used") or g.get("post_entry_features_used") or g.get("production_signal_identity_modified"):
            raise SystemExit(f"leakage/identity guard failed: {p}")
        if not g.get("all_market_features_observable_at_signal_creation"):
            raise SystemExit(f"causal feature guard failed: {p}")
        c=s["counts"]
        eligible["SHORT"]+=int(c["short_eligible_series"])
        eligible["LONG"]+=int(c["long_eligible_series"])
        resolved["SHORT"]+=int(c["short_resolved"])
        resolved["LONG"]+=int(c["long_resolved"])

    rows.sort(key=lambda r:(r["SYMBOL"].casefold(),r["SYMBOL"],r["SIDE"],int(r["ENTRY_TIME"]),r["SIGNAL_ID"]))
    if side["SHORT"]!=42030 or side["LONG"]!=50236:
        raise SystemExit(f"TRAIN row count mismatch SHORT/LONG={side['SHORT']}/{side['LONG']}")
    if eligible["SHORT"]!=355 or eligible["LONG"]!=406:
        raise SystemExit(f"eligible series mismatch SHORT/LONG={eligible['SHORT']}/{eligible['LONG']}")

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"FACTORY10_TRAIN_STRUCTURAL_FEATURES.csv",rows)

    combo_rows=[
        {"side":k[0],"stop_source":k[1],"target_source":k[2],"n":v}
        for k,v in sorted(combos.items())
    ]
    summary={
        "block":"DRUMMOND STRUCTURAL CONTEXT 10 AGGREGATE",
        "status":"PASS",
        "dataset_id":"DRUMMOND_CANONICAL_8E9A1D784E3893D9",
        "counts":{
            "shards":7,"rows":len(rows),
            "short_train":side["SHORT"],"long_train":side["LONG"],
            "short_eligible_series":eligible["SHORT"],"long_eligible_series":eligible["LONG"],
            "short_resolved_population":resolved["SHORT"],"long_resolved_population":resolved["LONG"]
        },
        "leakage_guard":{
            "test_rows_used":False,
            "post_entry_features_used":False,
            "all_market_features_observable_at_signal_creation":True,
            "production_signal_identity_modified":False
        },
        "source_combinations":combo_rows,
        "selection":"NONE",
        "next_required_gate":"TRAIN-only structural diagnosis and frozen rule definition before TEST."
    }
    (a.out/"FACTORY10_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=[
        "DRUMMOND STRUCTURAL CONTEXT 10 AGGREGATE","STATUS: PASS",
        f"SHARDS: 7/7",f"ROWS: {len(rows)}",
        f"SHORT TRAIN: {side['SHORT']}",f"LONG TRAIN: {side['LONG']}",
        f"ELIGIBLE SERIES SHORT/LONG: {eligible['SHORT']}/{eligible['LONG']}",
        "TEST ROWS USED: NO","POST-ENTRY FEATURES USED: NO",
        "PRODUCTION SIGNAL IDENTITY MODIFIED: NO","SELECTION: NONE"
    ]
    (a.out/"FACTORY10_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
