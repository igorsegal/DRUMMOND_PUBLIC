#!/usr/bin/env python3
import argparse,csv,hashlib,json,math
from collections import defaultdict
from pathlib import Path

TABLE_FIELDS=["DIMENSION","SIDE","BIN","N","TP","SL","TP_RATE","MEAN_R","CANDIDATE"]

SPECS={
 "ENTRY_PLDOT_R":[(-math.inf,0.0,"<0"),(0.0,0.10,"0-0.10"),(0.10,0.25,"0.10-0.25"),(0.25,0.50,"0.25-0.50"),(0.50,math.inf,">=0.50")],
 "H1_PLDOT_SLOPE_R":[(-math.inf,0.0,"<0"),(0.0,0.10,"0-0.10"),(0.10,0.20,"0.10-0.20"),(0.20,0.40,"0.20-0.40"),(0.40,math.inf,">=0.40")],
 "H4_ENTRY_PLDOT_R":[(-math.inf,0.0,"<0"),(0.0,0.50,"0-0.50"),(0.50,1.00,"0.50-1.00"),(1.00,2.00,"1.00-2.00"),(2.00,math.inf,">=2.00")],
 "H4_PLDOT_SLOPE_R":[(-math.inf,0.0,"<0"),(0.0,0.20,"0-0.20"),(0.20,0.50,"0.20-0.50"),(0.50,1.00,"0.50-1.00"),(1.00,math.inf,">=1.00")],
 "REFRESH_PENETRATION_R":[(-math.inf,0.05,"<0.05"),(0.05,0.10,"0.05-0.10"),(0.10,0.20,"0.10-0.20"),(0.20,0.35,"0.20-0.35"),(0.35,math.inf,">=0.35")],
 "REFRESH_RECLAIM_R":[(-math.inf,0.05,"<0.05"),(0.05,0.10,"0.05-0.10"),(0.10,0.25,"0.10-0.25"),(0.25,0.50,"0.25-0.50"),(0.50,math.inf,">=0.50")],
 "H1_RANGE_R":[(-math.inf,0.40,"<0.40"),(0.40,0.60,"0.40-0.60"),(0.60,0.80,"0.60-0.80"),(0.80,1.00,"0.80-1.00"),(1.00,math.inf,">=1.00")],
 "H1_BODY_R":[(-math.inf,-0.25,"<-0.25"),(-0.25,0.0,"-0.25-0"),(0.0,0.25,"0-0.25"),(0.25,0.50,"0.25-0.50"),(0.50,math.inf,">=0.50")],
 "SPREAD_RISK":[(-math.inf,0.01,"<1%"),(0.01,0.02,"1-2%"),(0.02,0.05,"2-5%"),(0.05,0.10,"5-10%"),(0.10,0.25,"10-25%"),(0.25,math.inf,">=25%")],
 "INITIAL_RISK_PCT":[(-math.inf,0.0025,"<0.25%"),(0.0025,0.0050,"0.25-0.50%"),(0.0050,0.0100,"0.50-1.00%"),(0.0100,0.0200,"1.00-2.00%"),(0.0200,math.inf,">=2.00%")],
 "RR":[(0.75,1.00,"0.75-1.00"),(1.00,1.25,"1.00-1.25"),(1.25,1.50,"1.25-1.50"),(1.50,1.7500001,"1.50-1.75")]
}

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def bin_of(value,bins):
    for lo,hi,label in bins:
        if value>=lo and value<hi:
            return label,lo,hi
    raise ValueError(f"value outside frozen bins: {value}")

def keyobj(dim,side,label,lo=None,hi=None,stop=None,target=None):
    o={"dimension":dim,"side":side,"bin":label}
    if lo is not None:
        o["lower_inclusive"]=None if math.isinf(lo) and lo<0 else lo
        o["upper_exclusive"]=None if math.isinf(hi) and hi>0 else hi
    if stop is not None: o["stop_source"]=stop
    if target is not None: o["target_source"]=target
    return o

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--features",type=Path,required=True)
    ap.add_argument("--summary",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    src=json.loads(a.summary.read_text(encoding="utf-8"))
    if src.get("status")!="PASS" or src.get("block")!="DRUMMOND STRUCTURAL CONTEXT 10 AGGREGATE":
        raise SystemExit("Factory 10 source is not PASS")
    if src["leakage_guard"]["test_rows_used"] or src["leakage_guard"]["post_entry_features_used"]:
        raise SystemExit("Factory 10 leakage guard is not clean")

    rows=read_csv(a.features)
    if len(rows)!=92266: raise SystemExit(f"expected 92266 TRAIN rows, got {len(rows)}")

    agg=defaultdict(lambda:{"N":0,"TP":0,"SL":0,"RSUM":0.0,"meta":None})
    for r in rows:
        side=r["SIDE"]; outcome=r["OUTCOME"]; rv=float(r["LEVEL_R"])
        if side not in ("SHORT","LONG") or outcome not in ("TP","SL"):
            raise SystemExit("bad TRAIN structural row")
        for dim,bins in SPECS.items():
            label,lo,hi=bin_of(float(r[dim]),bins)
            for scope in (side,"BOTH"):
                k=(dim,scope,label)
                x=agg[k]; x["N"]+=1; x[outcome]+=1; x["RSUM"]+=rv
                x["meta"]=keyobj(dim,scope,label,lo,hi)
        label=f"{r['STOP_SOURCE']}->{r['TARGET_SOURCE']}"
        for scope in (side,"BOTH"):
            k=("SOURCE_PAIR",scope,label)
            x=agg[k]; x["N"]+=1; x[outcome]+=1; x["RSUM"]+=rv
            x["meta"]=keyobj("SOURCE_PAIR",scope,label,stop=r["STOP_SOURCE"],target=r["TARGET_SOURCE"])

    table=[]; candidates=[]
    for k,x in sorted(agg.items()):
        n=x["N"]; mean=x["RSUM"]/n; rate=x["TP"]/n
        cand=n>=500 and mean>0.0
        table.append({"DIMENSION":k[0],"SIDE":k[1],"BIN":k[2],"N":n,"TP":x["TP"],"SL":x["SL"],
                      "TP_RATE":f"{rate:.8f}","MEAN_R":f"{mean:.8f}","CANDIDATE":"YES" if cand else "NO"})
        if cand:
            c=dict(x["meta"])
            c.update({"train_n":n,"train_tp":x["TP"],"train_sl":x["SL"],
                      "train_tp_rate":rate,"train_mean_r":mean})
            candidates.append(c)

    candidates.sort(key=lambda x:(x["dimension"],x["side"],x["bin"]))
    frozen={
        "block":"DRUMMOND STRUCTURAL DIAGNOSIS 11 FROZEN CANDIDATES",
        "dataset_id":src["dataset_id"],
        "selection_source":"TRAIN only",
        "selection_rule":"N >= 500 and TRAIN mean R > 0",
        "test_rows_used":False,
        "candidate_count":len(candidates),
        "candidates":candidates
    }
    canonical=json.dumps(frozen,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    digest=hashlib.sha256(canonical).hexdigest()
    frozen["canonical_sha256"]=digest

    a.out.mkdir(parents=True,exist_ok=True)
    with (a.out/"FACTORY11_TRAIN_BINS.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=TABLE_FIELDS,delimiter=";"); w.writeheader(); w.writerows(table)
    (a.out/"FACTORY11_FROZEN_CANDIDATES.json").write_text(json.dumps(frozen,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    summary={
        "block":"DRUMMOND STRUCTURAL DIAGNOSIS 11",
        "status":"PASS","dataset_id":src["dataset_id"],
        "train_rows":len(rows),"test_rows_used":False,
        "binning":"fixed ex-ante domain bins plus exact structural source pair",
        "selection_rule":"N >= 500 and TRAIN mean R > 0",
        "candidate_count":len(candidates),"frozen_candidate_sha256":digest,
        "candidates":candidates,
        "next_required_gate":"Apply this exact frozen candidate JSON to chronological TEST only; do not alter rules after viewing TEST."
    }
    (a.out/"FACTORY11_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["DRUMMOND STRUCTURAL DIAGNOSIS 11","STATUS: PASS",f"TRAIN ROWS: {len(rows)}",
           "TEST ROWS USED: NO",f"CANDIDATES: {len(candidates)}",f"FROZEN SHA256: {digest}"]
    for c in candidates:
        lines.append(f"CANDIDATE: {c['side']} {c['dimension']} {c['bin']} N={c['train_n']} MEAN_R={c['train_mean_r']:.8f}")
    lines.append("NEXT: FROZEN TEST VALIDATION")
    (a.out/"FACTORY11_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
