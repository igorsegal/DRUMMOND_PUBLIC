#!/usr/bin/env python3
import argparse,json
from collections import defaultdict
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    js=sorted(a.root.rglob("D24.json"))
    if len(js)!=7:raise SystemExit(f"D24A expected 7 shard summaries, got {len(js)}")
    total_symbols=total_trades=0;skips=defaultdict(int);acc=defaultdict(lambda:{"n":0,"sum_r":0.0,"max_r":None,"min_r":None,"shards":[]})
    for p in js:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s.get("status")!="PASS" or int(s.get("errors",0))!=0:raise SystemExit(f"bad shard {p}")
        if s.get("factory02_lifecycle_used"):raise SystemExit("Factory02 contamination")
        total_symbols+=int(s["symbols"]);total_trades+=int(s["trades"])
        for k,v in s.get("skips",{}).items():skips[k]+=int(v)
        for k,v in s["stats"].items():
            x=acc[k];n=int(v["n"]);x["n"]+=n;x["sum_r"]+=float(v.get("sum_r",0.0))
            mx=v.get("max_r");mn=v.get("min_r")
            if mx is not None:x["max_r"]=mx if x["max_r"] is None else max(x["max_r"],mx)
            if mn is not None:x["min_r"]=mn if x["min_r"] is None else min(x["min_r"],mn)
            x["shards"].append({
              "n":n,"mean_r":v.get("mean_r"),"trimmed_1pct_mean_r":v.get("trimmed_1pct_mean_r"),
              "equal_weight_symbol_mean_r":v.get("equal_weight_symbol_mean_r"),"max_r":mx
            })
    stats={}
    for k,x in sorted(acc.items()):
        stats[k]={
          "n":x["n"],"mean_r":x["sum_r"]/x["n"] if x["n"] else None,
          "min_r":x["min_r"],"max_r":x["max_r"],
          "positive_shard_means":sum((z["mean_r"] or 0)>0 for z in x["shards"]),
          "positive_shard_trimmed":sum((z["trimmed_1pct_mean_r"] or 0)>0 for z in x["shards"]),
          "positive_shard_eqsym":sum((z["equal_weight_symbol_mean_r"] or 0)>0 for z in x["shards"]),
          "shards":x["shards"]
        }
    out={
      "block":"D24","status":"PASS","dataset_id":"DRUMMOND_CANONICAL_8E9A1D784E3893D9",
      "symbols":total_symbols,"trades":total_trades,"skips":dict(skips),"stats":stats,
      "factory02_lifecycle_used":False,"selection_or_optimization_performed":False,
      "comparison_policy":"STRICT and PROXY are both reported; no winner selected.",
      "pyramiding":"OFF"
    }
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/"D24.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["D24 CORRECTED NATIVE DRUMMOND","STATUS: PASS",f"SYMBOLS: {total_symbols}",f"TRADES: {total_trades}","FACTORY02: NO","SELECTION: NO"]
    for k,v in stats.items():
        lines.append(f"{k}: N={v['n']} MEAN_R={v['mean_r']:.8f} MAX_R={v['max_r']:.4f} POS_SHARDS={v['positive_shard_means']}/7 TRIM+={v['positive_shard_trimmed']}/7 EQSYM+={v['positive_shard_eqsym']}/7")
    (a.out/"D24.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
