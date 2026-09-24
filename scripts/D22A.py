#!/usr/bin/env python3
import argparse,csv,json,statistics
from collections import Counter
from pathlib import Path

FIELDS=[
 "SYMBOL","STATUS","H1_M5_MATCHES","H1_M5_MED_RATIO","H1_M5_MED_POINT_DIFF","H1_M5_P95_POINT_DIFF","H1_M5_MAX_POINT_DIFF",
 "H4_H1_MATCHES","H4_H1_MED_RATIO","H4_H1_MED_POINT_DIFF","H4_H1_P95_POINT_DIFF","H4_H1_MAX_POINT_DIFF",
 "H1_POINT","M5_POINT","H4_POINT","H1_DIGITS","M5_DIGITS","H4_DIGITS","REASON"
]

def read_csv(p):
    with Path(p).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(p,rows):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";");w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    csvs=sorted(a.root.rglob("D22.csv"))
    sums=sorted(a.root.rglob("D22.json"))
    if len(csvs)!=7 or len(sums)!=7:
        raise SystemExit(f"D22A expected 7 shards, got csv={len(csvs)} json={len(sums)}")

    rows=[];seen=set();skips=0
    for p in sums:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s.get("status")!="PASS" or int(s.get("errors",0))!=0:
            raise SystemExit(f"bad D22 shard {p}")
        skips+=int(s.get("skipped_missing_tf",0))
    for p in csvs:
        for r in read_csv(p):
            sym=r["SYMBOL"]
            if sym in seen: raise SystemExit(f"duplicate symbol {sym}")
            seen.add(sym);rows.append(r)
    rows.sort(key=lambda r:(r["SYMBOL"].casefold(),r["SYMBOL"]))
    write_csv(a.out/"D22.csv",rows)

    bad=[r for r in rows if r["STATUS"]!="PASS"]
    reasons=Counter()
    for r in bad:
        for x in (r["REASON"] or "").split("|"):
            if x: reasons[x]+=1

    ratio_bad=[]
    for r in bad:
        try:
            a1=float(r["H1_M5_MED_RATIO"]) if r["H1_M5_MED_RATIO"] else None
            a2=float(r["H4_H1_MED_RATIO"]) if r["H4_H1_MED_RATIO"] else None
        except: a1=a2=None
        ratio_bad.append({"symbol":r["SYMBOL"],"h1_m5_ratio":a1,"h4_h1_ratio":a2,"reason":r["REASON"]})

    summary={
      "block":"D22","status":"PASS","dataset_id":"DRUMMOND_CANONICAL_8E9A1D784E3893D9",
      "checked":len(rows),"passed":len(rows)-len(bad),"failed":len(bad),
      "skipped_missing_tf":skips,"reason_counts":dict(sorted(reasons.items())),
      "failed_symbols":ratio_bad,
      "outcomes_used":False,
      "selection_or_optimization_performed":False,
      "next_gate":"D23 must exclude or normalize only by D22 data-integrity evidence, never by trading outcome."
    }
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/"D22.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=[
      "D22 XTF DATA AUDIT","STATUS: PASS",
      f"CHECKED/PASS/FAIL/SKIP: {len(rows)}/{len(rows)-len(bad)}/{len(bad)}/{skips}",
      "OUTCOMES USED: NO",
      "SELECTION/OPTIMIZATION: NO",
      "REASONS: "+json.dumps(dict(sorted(reasons.items())),ensure_ascii=False)
    ]
    for r in bad[:50]:
        lines.append(f"FAIL {r['SYMBOL']} H1/M5={r['H1_M5_MED_RATIO']} H4/H1={r['H4_H1_MED_RATIO']} {r['REASON']}")
    (a.out/"D22.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
