#!/usr/bin/env python3
import argparse,csv,json
from collections import Counter
from pathlib import Path

FIELDS=[
    "SYMBOL","SIDE","TRAIN_N","TEST_N","TRAIN_TP","TRAIN_SL","TEST_TP","TEST_SL",
    "TRAIN_TP_RATE","TEST_TP_RATE","TRAIN_MEAN_R","TEST_MEAN_R","TEST_RESULT"
]

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";")
        w.writeheader(); w.writerows(rows)

def weighted_mean(rows,mean_key,n_key):
    n=sum(int(r[n_key]) for r in rows)
    if n==0: return None
    return sum(float(r[mean_key])*int(r[n_key]) for r in rows)/n

def rate(rows,tp_key,sl_key):
    tp=sum(int(r[tp_key]) for r in rows)
    sl=sum(int(r[sl_key]) for r in rows)
    return (tp/(tp+sl) if tp+sl else None,tp,sl)

def stats(rows):
    tr_n=sum(int(r["TRAIN_N"]) for r in rows)
    te_n=sum(int(r["TEST_N"]) for r in rows)
    tr_mean=weighted_mean(rows,"TRAIN_MEAN_R","TRAIN_N")
    te_mean=weighted_mean(rows,"TEST_MEAN_R","TEST_N")
    tr_rate,tr_tp,tr_sl=rate(rows,"TRAIN_TP","TRAIN_SL")
    te_rate,te_tp,te_sl=rate(rows,"TEST_TP","TEST_SL")
    pos=sum(float(r["TEST_MEAN_R"])>0 for r in rows)
    return {
        "series":len(rows),"symbols":len({r["SYMBOL"] for r in rows}),
        "train_n":tr_n,"test_n":te_n,
        "train_mean_r":tr_mean,"test_mean_r":te_mean,
        "train_tp":tr_tp,"train_sl":tr_sl,"test_tp":te_tp,"test_sl":te_sl,
        "train_tp_rate":tr_rate,"test_tp_rate":te_rate,
        "test_positive_series":pos,"test_nonpositive_series":len(rows)-pos
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--side-split",type=Path,required=True)
    ap.add_argument("--stability-summary",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    src=json.loads(a.stability_summary.read_text(encoding="utf-8"))
    if src.get("status")!="PASS" or src.get("block")!="DRUMMOND TEMPORAL STABILITY 07":
        raise SystemExit("Factory 07 source is not PASS")
    rows=read_csv(a.side_split)

    # Frozen before TEST evaluation:
    # use only TRAIN/eligibility fields to define candidate series.
    selected=[
        r for r in rows
        if r["SIDE"] in ("SHORT","LONG")
        and r["ELIGIBLE"]=="YES"
        and int(r["TRAIN_N"])>=70
        and float(r["TRAIN_MEAN_R"])>0.0
    ]

    output=[]
    for r in selected:
        output.append({
            "SYMBOL":r["SYMBOL"],"SIDE":r["SIDE"],
            "TRAIN_N":r["TRAIN_N"],"TEST_N":r["TEST_N"],
            "TRAIN_TP":r["TRAIN_TP"],"TRAIN_SL":r["TRAIN_SL"],
            "TEST_TP":r["TEST_TP"],"TEST_SL":r["TEST_SL"],
            "TRAIN_TP_RATE":r["TRAIN_TP_RATE"],"TEST_TP_RATE":r["TEST_TP_RATE"],
            "TRAIN_MEAN_R":r["TRAIN_MEAN_R"],"TEST_MEAN_R":r["TEST_MEAN_R"],
            "TEST_RESULT":"POSITIVE" if float(r["TEST_MEAN_R"])>0 else "NONPOSITIVE"
        })

    by_side={side:[r for r in selected if r["SIDE"]==side] for side in ("SHORT","LONG")}
    all_stats=stats(selected)
    side_stats={side:stats(rr) for side,rr in by_side.items()}
    validation_pass=(all_stats["test_mean_r"] is not None and all_stats["test_mean_r"]>0)

    summary={
        "block":"DRUMMOND TRAIN-ONLY EDGE VALIDATION 08",
        "status":"PASS",
        "dataset_id":src["dataset_id"],
        "selection_rule":{
            "source":"Factory 07 side split",
            "uses_test_fields":False,
            "conditions":["ELIGIBLE == YES","TRAIN_N >= 70","TRAIN_MEAN_R > 0"],
            "rationale":"roughly >=100 resolved observations under the 70/30 split, positive TRAIN expectancy, no parameter optimization"
        },
        "candidate_pool":all_stats,
        "by_side":side_stats,
        "validation_result":"PASS" if validation_pass else "FAIL",
        "validation_criterion":"pooled candidate TEST mean R > 0",
        "limitations":[
            "Factory 07 already exposed aggregate TEST behavior, so this is a validation exercise, not a pristine never-seen final holdout.",
            "No symbol or side was selected using TEST fields in this block.",
            "A final production claim still requires future/unseen data or a new immutable dataset."
        ],
        "next_required_gate":"If validation fails, do not promote this train-positive rule. Move to feature/regime diagnosis using TRAIN only; reserve future data for final confirmation."
    }

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"FACTORY08_CANDIDATES.csv",output)
    (a.out/"FACTORY08_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=[
        "DRUMMOND TRAIN-ONLY EDGE VALIDATION 08",
        "STATUS: PASS",
        f"DATASET: {src['dataset_id']}",
        "SELECTION USES TEST: NO",
        "RULE: ELIGIBLE=YES; TRAIN_N>=70; TRAIN_MEAN_R>0",
        f"CANDIDATE SERIES: {all_stats['series']}",
        f"CANDIDATE SYMBOLS: {all_stats['symbols']}",
        f"SHORT/LONG SERIES: {side_stats['SHORT']['series']}/{side_stats['LONG']['series']}",
        f"TRAIN N / TEST N: {all_stats['train_n']} / {all_stats['test_n']}",
        f"TRAIN MEAN R: {all_stats['train_mean_r']:.8f}",
        f"TEST MEAN R: {all_stats['test_mean_r']:.8f}",
        f"TRAIN TP RATE: {all_stats['train_tp_rate']:.8f}",
        f"TEST TP RATE: {all_stats['test_tp_rate']:.8f}",
        f"TEST POSITIVE/NONPOSITIVE SERIES: {all_stats['test_positive_series']}/{all_stats['test_nonpositive_series']}",
        f"VALIDATION_RESULT: {summary['validation_result']}",
        "PRODUCTION PROMOTION: NO",
        "NEXT: TRAIN-ONLY FEATURE/REGIME DIAGNOSIS"
    ]
    (a.out/"FACTORY08_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
