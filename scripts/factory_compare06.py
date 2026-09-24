#!/usr/bin/env python3
import argparse,csv,json
from pathlib import Path

OUT_FIELDS=[
    "SYMBOL","STATUS_SHORT","STATUS_LONG","SIGNALS_SHORT","SIGNALS_LONG",
    "RESOLVED_SHORT","RESOLVED_LONG","TP_RATE_SHORT","TP_RATE_LONG",
    "MEAN_R_SHORT","MEAN_R_LONG","COMBINED_SIGNALS","COMBINED_RESOLVED",
    "COMBINED_TP","COMBINED_SL","COMBINED_AMBIGUOUS","COMBINED_OPEN",
    "COMBINED_TRAIL_UPDATES","COMBINED_TP_RATE","COMBINED_MEAN_R","SIDE_CLASS"
]

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def fnum(x):
    return None if x in ("",None) else float(x)

def inum(x):
    return 0 if x in ("",None) else int(x)

def fmt(x):
    return "" if x is None else f"{x:.8f}"

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=OUT_FIELDS,delimiter=";")
        w.writeheader(); w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--short-csv",type=Path,required=True)
    ap.add_argument("--short-summary",type=Path,required=True)
    ap.add_argument("--long-csv",type=Path,required=True)
    ap.add_argument("--long-summary",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    ss=json.loads(a.short_summary.read_text(encoding="utf-8"))
    ls=json.loads(a.long_summary.read_text(encoding="utf-8"))
    if ss.get("status")!="PASS" or ls.get("status")!="PASS":
        raise SystemExit("input aggregate status is not PASS")
    if ss.get("dataset_id")!=ls.get("dataset_id"):
        raise SystemExit("dataset mismatch between SHORT and LONG")

    sr=read_csv(a.short_csv); lr=read_csv(a.long_csv)
    sm={r["SYMBOL"]:r for r in sr}; lm={r["SYMBOL"]:r for r in lr}
    if len(sm)!=len(sr) or len(lm)!=len(lr):
        raise SystemExit("duplicate symbol in input aggregate")
    if list(sm)!=list(lm):
        raise SystemExit("symbol ordering/set mismatch between SHORT and LONG")

    out=[]; classes={}
    totals={k:0 for k in ("signals","resolved","tp","sl","ambiguous","open","trail_updates")}
    weighted_r_sum=0.0; weighted_r_n=0; positive_combined=0
    evidence={"positive_ge_50":0,"positive_ge_100":0,"positive_ge_300":0,
              "both_positive_ge_50_each":0,"both_positive_ge_100_each":0}

    for sym in sm:
        s=sm[sym]; l=lm[sym]
        if s["STATUS"]!=l["STATUS"]:
            raise SystemExit(f"status mismatch {sym}: {s['STATUS']} vs {l['STATUS']}")
        status=s["STATUS"]
        row={k:"" for k in OUT_FIELDS}
        row["SYMBOL"]=sym; row["STATUS_SHORT"]=status; row["STATUS_LONG"]=status
        if status!="PROCESSED":
            row["SIDE_CLASS"]=status
            out.append(row)
            classes[status]=classes.get(status,0)+1
            continue

        ssig,lsig=inum(s["SIGNALS"]),inum(l["SIGNALS"])
        stp,ssl=inum(s["TP"]),inum(s["SL"])
        ltp,lsl=inum(l["TP"]),inum(l["SL"])
        srn,lrn=stp+ssl,ltp+lsl
        srmean,lrmean=fnum(s["MEAN_LEVEL_R"]),fnum(l["MEAN_LEVEL_R"])
        strp=fnum(s["TP_RATE_RESOLVED"]); ltrp=fnum(l["TP_RATE_RESOLVED"])
        ctp,csl=stp+ltp,ssl+lsl; cres=ctp+csl; csig=ssig+lsig
        camb=inum(s["AMBIGUOUS"])+inum(l["AMBIGUOUS"])
        copen=inum(s["OPEN"])+inum(l["OPEN"])
        ctrail=inum(s["TRAIL_UPDATES"])+inum(l["TRAIL_UPDATES"])
        ctp_rate=ctp/cres if cres else None

        mean_num=0.0; mean_den=0
        if srmean is not None and srn>0:
            mean_num+=srmean*srn; mean_den+=srn
        if lrmean is not None and lrn>0:
            mean_num+=lrmean*lrn; mean_den+=lrn
        cmean=mean_num/mean_den if mean_den else None

        if srmean is not None and lrmean is not None:
            if srmean>0 and lrmean>0: cls="BOTH_POSITIVE"
            elif srmean>0: cls="SHORT_POSITIVE_ONLY"
            elif lrmean>0: cls="LONG_POSITIVE_ONLY"
            else: cls="BOTH_NONPOSITIVE"
        elif srmean is not None:
            cls="SHORT_ONLY_OBSERVED_POSITIVE" if srmean>0 else "SHORT_ONLY_OBSERVED_NONPOSITIVE"
        elif lrmean is not None:
            cls="LONG_ONLY_OBSERVED_POSITIVE" if lrmean>0 else "LONG_ONLY_OBSERVED_NONPOSITIVE"
        else:
            cls="NO_RESOLVED_SIGNALS"
        classes[cls]=classes.get(cls,0)+1

        if cmean is not None and cmean>0:
            positive_combined+=1
            if cres>=50: evidence["positive_ge_50"]+=1
            if cres>=100: evidence["positive_ge_100"]+=1
            if cres>=300: evidence["positive_ge_300"]+=1
        if srmean is not None and lrmean is not None and srmean>0 and lrmean>0:
            if srn>=50 and lrn>=50: evidence["both_positive_ge_50_each"]+=1
            if srn>=100 and lrn>=100: evidence["both_positive_ge_100_each"]+=1

        totals["signals"]+=csig; totals["resolved"]+=cres; totals["tp"]+=ctp; totals["sl"]+=csl
        totals["ambiguous"]+=camb; totals["open"]+=copen; totals["trail_updates"]+=ctrail
        if cmean is not None and cres>0:
            weighted_r_sum+=cmean*cres; weighted_r_n+=cres

        row.update({
            "SIGNALS_SHORT":ssig,"SIGNALS_LONG":lsig,"RESOLVED_SHORT":srn,"RESOLVED_LONG":lrn,
            "TP_RATE_SHORT":fmt(strp),"TP_RATE_LONG":fmt(ltrp),"MEAN_R_SHORT":fmt(srmean),"MEAN_R_LONG":fmt(lrmean),
            "COMBINED_SIGNALS":csig,"COMBINED_RESOLVED":cres,"COMBINED_TP":ctp,"COMBINED_SL":csl,
            "COMBINED_AMBIGUOUS":camb,"COMBINED_OPEN":copen,"COMBINED_TRAIL_UPDATES":ctrail,
            "COMBINED_TP_RATE":fmt(ctp_rate),"COMBINED_MEAN_R":fmt(cmean),"SIDE_CLASS":cls
        })
        out.append(row)

    combined_tp_rate=totals["tp"]/totals["resolved"] if totals["resolved"] else None
    combined_mean_r=weighted_r_sum/weighted_r_n if weighted_r_n else None
    summary={
        "block":"DRUMMOND FACTORY SIDE COMPARE 06",
        "status":"PASS",
        "dataset_id":ss["dataset_id"],
        "inputs":{"short_block":"04 SHORT_ONLY","long_block":"05 LONG_ONLY"},
        "counts":{
            "symbols":len(out),
            "processed":sum(v for k,v in classes.items() if not k.startswith("SKIP_")),
            "classes":dict(sorted(classes.items())),
            "combined_positive_mean_r_symbols":positive_combined,
            **evidence, **totals,
        },
        "combined_tp_rate_resolved":combined_tp_rate,
        "combined_mean_level_r_resolved":combined_mean_r,
        "interpretation_policy":{
            "descriptive_only":True,
            "no_symbol_selection":True,
            "no_parameter_fitting":True,
            "next_required_gate":"time-split stability / out-of-sample validation before any inclusion decision"
        }
    }
    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"FACTORY06_SIDE_COMPARE.csv",out)
    (a.out/"FACTORY06_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=[
        "DRUMMOND FACTORY SIDE COMPARE 06","STATUS: PASS",f"DATASET: {ss['dataset_id']}",
        f"SYMBOLS: {len(out)}",f"PROCESSED: {summary['counts']['processed']}",
        f"SIDE CLASSES: {summary['counts']['classes']}",f"COMBINED SIGNALS: {totals['signals']}",
        f"COMBINED TP/SL/AMBIGUOUS/OPEN: {totals['tp']}/{totals['sl']}/{totals['ambiguous']}/{totals['open']}",
        f"COMBINED TRAIL UPDATES: {totals['trail_updates']}",
        f"COMBINED TP RATE RESOLVED: {combined_tp_rate:.8f}" if combined_tp_rate is not None else "COMBINED TP RATE RESOLVED: N/A",
        f"COMBINED MEAN LEVEL R RESOLVED: {combined_mean_r:.8f}" if combined_mean_r is not None else "COMBINED MEAN LEVEL R RESOLVED: N/A",
        f"POSITIVE COMBINED MEAN-R SYMBOLS: {positive_combined}",
        f"POSITIVE >=100 RESOLVED: {evidence['positive_ge_100']}",
        f"POSITIVE >=300 RESOLVED: {evidence['positive_ge_300']}",
        f"BOTH SIDES POSITIVE >=50 RESOLVED EACH: {evidence['both_positive_ge_50_each']}",
        "SELECTION: NOT PERFORMED","NEXT: TEMPORAL STABILITY / OUT-OF-SAMPLE GATE"
    ]
    (a.out/"FACTORY06_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
