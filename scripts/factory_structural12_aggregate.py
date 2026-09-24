#!/usr/bin/env python3
import argparse,csv,json
from collections import Counter,defaultdict
from pathlib import Path

FIELDS=["CANDIDATE_ID","DIMENSION","BIN","SYMBOL","SIDE","SIGNAL_ID","ENTRY_TIME","OUTCOME","LEVEL_R","FEATURE_VALUE"]

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
    ap.add_argument("--candidates",type=Path,required=True)
    ap.add_argument("--expected-sha",required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    frozen=json.loads(a.candidates.read_text(encoding="utf-8"))
    if frozen.get("canonical_sha256")!=a.expected_sha:
        raise SystemExit("aggregate frozen SHA mismatch")
    candidates=frozen["candidates"]
    if len(candidates)!=2: raise SystemExit("aggregate expected two frozen candidates")
    train={f"C{i+1:02d}":c for i,c in enumerate(candidates)}

    csvs=sorted(a.artifact_root.rglob("FACTORY12_TEST_MATCHES.csv"))
    sums=sorted(a.artifact_root.rglob("FACTORY12_SUMMARY.json"))
    if len(csvs)!=7 or len(sums)!=7:
        raise SystemExit(f"expected 7 shard files, got csv={len(csvs)} summary={len(sums)}")

    rows=[]; seen=set(); fulltest=Counter()
    for p in csvs:
        for r in read_csv(p):
            key=(r["CANDIDATE_ID"],r["SIDE"],r["SIGNAL_ID"])
            if key in seen: raise SystemExit(f"duplicate TEST match {key}")
            seen.add(key); rows.append(r)
    for p in sums:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s.get("status")!="PASS" or s.get("frozen_candidate_sha256")!=a.expected_sha:
            raise SystemExit(f"bad shard TEST summary {p}")
        g=s["guards"]
        if g.get("candidate_rules_modified") or g.get("post_entry_features_used") or not g.get("features_causal_at_signal_creation"):
            raise SystemExit(f"TEST guard failed {p}")
        c=s["counts"]
        for k in ("short_test","long_test","short_resolved","long_resolved","short_eligible_series","long_eligible_series"):
            fulltest[k]+=int(c[k])

    if fulltest["short_test"]!=18260 or fulltest["long_test"]!=21810:
        raise SystemExit(f"TEST population mismatch SHORT/LONG={fulltest['short_test']}/{fulltest['long_test']}")
    if fulltest["short_eligible_series"]!=355 or fulltest["long_eligible_series"]!=406:
        raise SystemExit("eligible series mismatch in TEST")

    by=defaultdict(list)
    for r in rows: by[r["CANDIDATE_ID"]].append(r)

    candidate_results=[]
    passed=0
    for cid,c in train.items():
        rr=by.get(cid,[])
        n=len(rr)
        tp=sum(r["OUTCOME"]=="TP" for r in rr)
        sl=sum(r["OUTCOME"]=="SL" for r in rr)
        mean=(sum(float(r["LEVEL_R"]) for r in rr)/n) if n else None
        rate=(tp/(tp+sl)) if tp+sl else None
        ok=mean is not None and mean>0.0
        if ok: passed+=1
        candidate_results.append({
            "candidate_id":cid,"dimension":c["dimension"],"side":c["side"],"bin":c["bin"],
            "train_n":c["train_n"],"train_mean_r":c["train_mean_r"],"train_tp_rate":c["train_tp_rate"],
            "test_n":n,"test_tp":tp,"test_sl":sl,"test_tp_rate":rate,"test_mean_r":mean,
            "validation":"PASS" if ok else "FAIL"
        })

    union={}
    for r in rows:
        key=(r["SIDE"],r["SIGNAL_ID"])
        union[key]=r
    un=list(union.values())
    un_n=len(un); un_tp=sum(r["OUTCOME"]=="TP" for r in un); un_sl=sum(r["OUTCOME"]=="SL" for r in un)
    un_mean=sum(float(r["LEVEL_R"]) for r in un)/un_n if un_n else None
    un_rate=un_tp/(un_tp+un_sl) if un_tp+un_sl else None

    rows.sort(key=lambda r:(r["CANDIDATE_ID"],r["SYMBOL"].casefold(),int(r["ENTRY_TIME"]),r["SIGNAL_ID"]))
    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"FACTORY12_TEST_MATCHES.csv",rows)

    summary={
        "block":"DRUMMOND FROZEN STRUCTURAL TEST 12",
        "status":"PASS",
        "dataset_id":frozen["dataset_id"],
        "frozen_candidate_sha256":a.expected_sha,
        "test_population":{
            "short_test":fulltest["short_test"],"long_test":fulltest["long_test"],
            "combined_test":fulltest["short_test"]+fulltest["long_test"],
            "short_eligible_series":fulltest["short_eligible_series"],
            "long_eligible_series":fulltest["long_eligible_series"]
        },
        "candidate_results":candidate_results,
        "candidates_passed":passed,
        "union":{"n":un_n,"tp":un_tp,"sl":un_sl,"tp_rate":un_rate,"mean_r":un_mean},
        "guards":{"candidate_rules_modified":False,"test_used_only_after_freeze":True},
        "production_promotion":"NO",
        "production_note":"This TEST was frozen after TRAIN rule definition, but earlier blocks exposed aggregate TEST behavior. A pristine future/new immutable dataset remains required for final production confirmation."
    }
    (a.out/"FACTORY12_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["DRUMMOND FROZEN STRUCTURAL TEST 12","STATUS: PASS",
           f"FROZEN SHA256: {a.expected_sha}",
           f"TEST POPULATION SHORT/LONG: {fulltest['short_test']}/{fulltest['long_test']}"]
    for r in candidate_results:
        lines.append(f"{r['candidate_id']} {r['side']} {r['dimension']} {r['bin']} TRAIN_R={r['train_mean_r']:.8f} TEST_N={r['test_n']} TEST_R={r['test_mean_r']:.8f} {r['validation']}")
    lines += [f"CANDIDATES PASSED: {passed}/{len(candidate_results)}",
              f"UNION TEST N={un_n} MEAN_R={un_mean:.8f}" if un_mean is not None else "UNION TEST N=0",
              "PRODUCTION PROMOTION: NO"]
    (a.out/"FACTORY12_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
