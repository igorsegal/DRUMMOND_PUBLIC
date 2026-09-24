#!/usr/bin/env python3
import argparse,csv,json,statistics
from collections import Counter,defaultdict
from pathlib import Path

FIELDS=[
 "SYMBOL","FAMILY","FLOW_N","SIDE","SETUP_TIME","ENTRY_TIME","ENTRY",
 "STOP0","TARGET0","TARGET_EXT","OUTCOME","EXIT_TIME","EXIT","R",
 "M5_BARS","TRAIL_UPDATES","TARGET_EXTENDED","FLOW_EXIT_STREAK","DETAIL"
]

def read_csv(p):
    with Path(p).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(p,rows):
    with Path(p).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";");w.writeheader();w.writerows(rows)

def pct(vals,q):
    if not vals:return None
    a=sorted(vals)
    if len(a)==1:return a[0]
    x=(len(a)-1)*q
    lo=int(x);hi=min(lo+1,len(a)-1);w=x-lo
    return a[lo]*(1-w)+a[hi]*w

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    csvs=sorted(a.root.rglob("D21.csv"))
    sums=sorted(a.root.rglob("D21.json"))
    if len(csvs)!=7 or len(sums)!=7:
        raise SystemExit(f"D21A expected 7 shards, got csv={len(csvs)} json={len(sums)}")
    rows=[];seen=set();symbols=0
    for p in sums:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s.get("status")!="PASS" or s.get("errors")!=0:
            raise SystemExit(f"bad D21 shard {p}")
        n=s.get("native_drummond",{})
        if any(n.get(k) for k in ("factory02_entries_used","factory02_stops_used","factory02_targets_used","factory02_trailing_used")):
            raise SystemExit("Factory02 contamination")
        symbols+=int(s["symbols"])
    for p in csvs:
        for r in read_csv(p):
            k=(r["SYMBOL"],r["FAMILY"],r["FLOW_N"],r["ENTRY_TIME"],r["SIDE"])
            if k in seen:
                # same timestamp may legitimately have distinct setup cycles only if family/flow differ;
                # within same family/flow/symbol duplicate is a contract violation.
                raise SystemExit(f"duplicate D21 trade {k}")
            seen.add(k);rows.append(r)
    rows.sort(key=lambda r:(r["FAMILY"],int(r["FLOW_N"]),int(r["ENTRY_TIME"]),r["SYMBOL"]))
    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D21.csv",rows)

    groups=defaultdict(list)
    for r in rows:groups[(r["FAMILY"],int(r["FLOW_N"]))].append(r)
    stats=[]
    for (fam,fn),rr in sorted(groups.items()):
        vals=[float(x["R"]) for x in rr]
        years=defaultdict(list)
        for x in rr:
            import datetime
            y=datetime.datetime.fromtimestamp(int(x["ENTRY_TIME"]),tz=datetime.timezone.utc).year
            years[y].append(float(x["R"]))
        yrmeans={str(y):sum(v)/len(v) for y,v in sorted(years.items())}
        bysym=defaultdict(list)
        for x in rr:bysym[x["SYMBOL"]].append(float(x["R"]))
        symmeans=[sum(v)/len(v) for v in bysym.values()]
        aa=sorted(vals)
        trim=max(0,int(len(aa)*0.01))
        trimmed=aa[trim:len(aa)-trim] if trim>0 and len(aa)>2*trim else aa
        posvals=sorted([v for v in vals if v>0],reverse=True)
        topn=max(1,int(len(vals)*0.01)) if vals else 0
        pos_sum=sum(posvals)
        top_share=(sum(posvals[:topn])/pos_sum) if pos_sum>0 and topn>0 else None
        stats.append({
          "family":fam,"flow_n":fn,"n":len(rr),
          "mean_r":sum(vals)/len(vals) if vals else None,
          "median_r":statistics.median(vals) if vals else None,
          "trimmed_1pct_mean_r":sum(trimmed)/len(trimmed) if trimmed else None,
          "p01_r":pct(vals,0.01),"p05_r":pct(vals,0.05),"p95_r":pct(vals,0.95),"p99_r":pct(vals,0.99),
          "min_r":min(vals) if vals else None,"max_r":max(vals) if vals else None,
          "equal_weight_symbol_mean_r":sum(symmeans)/len(symmeans) if symmeans else None,
          "symbols":len(symmeans),"top1pct_share_positive_r":top_share,
          "positive_rate":sum(v>0 for v in vals)/len(vals) if vals else None,
          "positive_years":sum(v>0 for v in yrmeans.values()),
          "nonpositive_years":sum(v<=0 for v in yrmeans.values()),
          "year_mean_r":yrmeans,
          "outcomes":dict(Counter(x["OUTCOME"] for x in rr)),
          "long_n":sum(x["SIDE"]=="LONG" for x in rr),
          "short_n":sum(x["SIDE"]=="SHORT" for x in rr),
          "extended_n":sum(x["TARGET_EXTENDED"]=="Y" for x in rr)
        })
    best=sorted([x for x in stats if x["mean_r"] is not None],key=lambda x:x["mean_r"],reverse=True)
    summary={
      "block":"D21","status":"PASS","dataset_id":"DRUMMOND_CANONICAL_8E9A1D784E3893D9",
      "symbols":symbols,"trades":len(rows),"stats":stats,
      "best_by_mean_r":best,
      "native_drummond_only":True,
      "factory02_lifecycle_used":False,
      "pyramiding":"OFF_IN_D21_BASELINE",
      "selection_or_optimization_performed":False,
      "promotion_allowed":False
    }
    (a.out/"D21.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["D21 NATIVE DRUMMOND","STATUS: PASS",f"SYMBOLS: {symbols}",f"TRADES: {len(rows)}","FACTORY02 LIFECYCLE: NO","SELECTION/OPTIMIZATION: NO"]
    for x in stats:
        lines.append(f"{x['family']} F{x['flow_n']}: N={x['n']} MEAN_R={x['mean_r']:.8f} MED={x['median_r']:.8f} TRIM1={x['trimmed_1pct_mean_r']:.8f} P99={x['p99_r']:.4f} MAX={x['max_r']:.4f} EQSYM={x['equal_weight_symbol_mean_r']:.8f} POS_RATE={x['positive_rate']:.6f} YEARS+/-={x['positive_years']}/{x['nonpositive_years']}")
    (a.out/"D21.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
