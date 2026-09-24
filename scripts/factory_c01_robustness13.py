#!/usr/bin/env python3
import argparse,csv,json,math
from collections import defaultdict
from pathlib import Path
import random

YEAR_FIELDS=["SPLIT","YEAR","N","TP","SL","TP_RATE","MEAN_R"]
SYMBOL_FIELDS=["SPLIT","SYMBOL","N","TP","SL","TP_RATE","MEAN_R"]

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";")
        w.writeheader(); w.writerows(rows)

def stats(rows):
    n=len(rows); tp=sum(r["OUTCOME"]=="TP" for r in rows); sl=sum(r["OUTCOME"]=="SL" for r in rows)
    mean=sum(float(r["LEVEL_R"]) for r in rows)/n if n else None
    rate=tp/(tp+sl) if tp+sl else None
    return {"n":n,"tp":tp,"sl":sl,"tp_rate":rate,"mean_r":mean}

def by_symbol(rows):
    d=defaultdict(list)
    for r in rows:d[r["SYMBOL"]].append(r)
    out=[]
    for sym,rr in sorted(d.items()):
        s=stats(rr); out.append({"SYMBOL":sym,**s,"sum_r":sum(float(x["LEVEL_R"]) for x in rr)})
    return out

def concentration(rows):
    sy=by_symbol(rows); n=len(rows)
    counts=sorted((x["n"] for x in sy),reverse=True)
    top1=counts[0]/n if n else None
    top5=sum(counts[:5])/n if n else None
    hhi=sum((x["n"]/n)**2 for x in sy) if n else None
    equal_weight=sum(x["mean_r"] for x in sy)/len(sy) if sy else None
    total=sum(float(r["LEVEL_R"]) for r in rows)
    loo=[]
    for x in sy:
        if n-x["n"]>0: loo.append((total-x["sum_r"])/(n-x["n"]))
    return {
        "symbols":len(sy),"top1_share":top1,"top5_share":top5,"symbol_hhi":hhi,
        "equal_weight_symbol_mean_r":equal_weight,
        "leave_one_symbol_out_min_mean_r":min(loo) if loo else None,
        "leave_one_symbol_out_max_mean_r":max(loo) if loo else None
    }

def cluster_bootstrap(rows,reps=20000,seed=1701):
    d=defaultdict(list)
    for r in rows:d[r["SYMBOL"]].append(float(r["LEVEL_R"]))
    groups=[v for _,v in sorted(d.items())]
    rng=random.Random(seed)
    vals=[]
    m=len(groups)
    for _ in range(reps):
        total=0.0;n=0
        for _j in range(m):
            g=groups[rng.randrange(m)]
            total+=sum(g);n+=len(g)
        vals.append(total/n)
    vals.sort()
    def q(p):
        pos=p*(len(vals)-1);lo=int(math.floor(pos));hi=int(math.ceil(pos))
        if lo==hi:return vals[lo]
        f=pos-lo;return vals[lo]*(1-f)+vals[hi]*f
    return {"reps":reps,"seed":seed,"p025":q(.025),"median":q(.5),"p975":q(.975)}

def yearly(rows):
    from datetime import datetime,timezone
    d=defaultdict(list)
    for r in rows:
        y=datetime.fromtimestamp(int(r["ENTRY_TIME"]),tz=timezone.utc).year
        d[y].append(r)
    out=[]
    for y,rr in sorted(d.items()):
        s=stats(rr);out.append({"YEAR":y,**s})
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--train-features",type=Path,required=True)
    ap.add_argument("--test-matches",type=Path,required=True)
    ap.add_argument("--frozen",type=Path,required=True)
    ap.add_argument("--expected-sha",required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    frozen=json.loads(a.frozen.read_text(encoding="utf-8"))
    if frozen.get("canonical_sha256")!=a.expected_sha:
        raise SystemExit("frozen SHA mismatch")
    cands=frozen["candidates"]
    c01=[c for c in cands if c["dimension"]=="ENTRY_PLDOT_R" and c["side"]=="LONG" and c["bin"]=="<0"]
    if len(c01)!=1: raise SystemExit("C01 contract not uniquely found")

    train=[r for r in read_csv(a.train_features) if r["SIDE"]=="LONG" and float(r["ENTRY_PLDOT_R"])<0.0]
    test=[r for r in read_csv(a.test_matches) if r["CANDIDATE_ID"]=="C01"]
    if len(train)!=624 or len(test)!=102:
        raise SystemExit(f"C01 population mismatch TRAIN/TEST={len(train)}/{len(test)}")

    tr=stats(train); te=stats(test)
    trc=concentration(train); tec=concentration(test)
    trb=cluster_bootstrap(train); teb=cluster_bootstrap(test)
    tr_y=yearly(train); te_y=yearly(test)
    tr_s=by_symbol(train); te_s=by_symbol(test)

    year_rows=[]
    for split,yy in (("TRAIN",tr_y),("TEST",te_y)):
        for x in yy:
            year_rows.append({"SPLIT":split,"YEAR":x["YEAR"],"N":x["n"],"TP":x["tp"],"SL":x["sl"],
                              "TP_RATE":f"{x['tp_rate']:.8f}","MEAN_R":f"{x['mean_r']:.8f}"})
    symbol_rows=[]
    for split,ss in (("TRAIN",tr_s),("TEST",te_s)):
        for x in ss:
            symbol_rows.append({"SPLIT":split,"SYMBOL":x["SYMBOL"],"N":x["n"],"TP":x["tp"],"SL":x["sl"],
                                "TP_RATE":f"{x['tp_rate']:.8f}","MEAN_R":f"{x['mean_r']:.8f}"})

    summary={
        "block":"DRUMMOND C01 ROBUSTNESS AUDIT 13","status":"PASS",
        "dataset_id":frozen["dataset_id"],"frozen_candidate_sha256":a.expected_sha,
        "rule":{"side":"LONG","dimension":"ENTRY_PLDOT_R","condition":"< 0","modified":False},
        "train":{**tr,**trc,"cluster_bootstrap_mean_r_95":trb},
        "test":{**te,**tec,"cluster_bootstrap_mean_r_95":teb},
        "yearly":{
            "train_years":len(tr_y),"test_years":len(te_y),
            "test_positive_years":sum(x["mean_r"]>0 for x in te_y),
            "test_nonpositive_years":sum(x["mean_r"]<=0 for x in te_y)
        },
        "robustness_flags":{
            "train_mean_positive":tr["mean_r"]>0,
            "test_mean_positive":te["mean_r"]>0,
            "test_equal_weight_symbol_mean_positive":tec["equal_weight_symbol_mean_r"]>0,
            "test_leave_one_symbol_out_min_positive":tec["leave_one_symbol_out_min_mean_r"]>0,
            "test_cluster_bootstrap_p025_positive":teb["p025"]>0
        },
        "production_promotion":"NO",
        "production_note":"C01 is a surviving historical candidate, not a final production proof. Future/new immutable data remains the pristine confirmation set."
    }
    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"FACTORY13_YEARLY.csv",YEAR_FIELDS,year_rows)
    write_csv(a.out/"FACTORY13_SYMBOLS.csv",SYMBOL_FIELDS,symbol_rows)
    (a.out/"FACTORY13_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=[
        "DRUMMOND C01 ROBUSTNESS AUDIT 13","STATUS: PASS",
        f"FROZEN SHA256: {a.expected_sha}",
        f"TRAIN N={tr['n']} MEAN_R={tr['mean_r']:.8f} SYMBOLS={trc['symbols']}",
        f"TEST N={te['n']} MEAN_R={te['mean_r']:.8f} SYMBOLS={tec['symbols']}",
        f"TEST TOP1/TOP5 SHARE={tec['top1_share']:.6f}/{tec['top5_share']:.6f}",
        f"TEST EQUAL-WEIGHT SYMBOL MEAN_R={tec['equal_weight_symbol_mean_r']:.8f}",
        f"TEST LOO MIN/MAX MEAN_R={tec['leave_one_symbol_out_min_mean_r']:.8f}/{tec['leave_one_symbol_out_max_mean_r']:.8f}",
        f"TEST CLUSTER BOOTSTRAP 95%={teb['p025']:.8f}..{teb['p975']:.8f}",
        f"TEST POSITIVE/NONPOSITIVE YEARS={summary['yearly']['test_positive_years']}/{summary['yearly']['test_nonpositive_years']}",
        "RULE MODIFIED: NO","PRODUCTION PROMOTION: NO"
    ]
    (a.out/"FACTORY13_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
