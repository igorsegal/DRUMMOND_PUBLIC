#!/usr/bin/env python3
import argparse,json
from collections import Counter,defaultdict
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    js=sorted(a.root.rglob("D25.json"))
    if len(js)!=7:
        raise SystemExit(f"D25A expected 7 shard summaries, got {len(js)}")

    total_symbols=total_trades=total_states=0
    skips=Counter();trans=Counter()
    acc=defaultdict(lambda:{
        "n":0,"sum_r":0.0,"pyr":0,"max_r":None,"min_r":None,
        "positive_shards":0,"entry_states":Counter(),"shards":[]
    })
    for p in js:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s.get("status")!="PASS" or int(s.get("errors",0))!=0:
            raise SystemExit(f"bad D25 shard {p}")
        c=s.get("contract",{})
        if not c.get("continuous_state_machine"):raise SystemExit("D25 no state machine")
        if c.get("exhaust_standalone_entry"):raise SystemExit("D25 exhaust standalone entry violation")
        if c.get("factory02_lifecycle_used"):raise SystemExit("D25 Factory02 contamination")
        if c.get("further_out")!="5/2+5/9 only":raise SystemExit("D25 Further Out contract mismatch")
        if c.get("selection_or_optimization"):raise SystemExit("D25 optimization violation")

        total_symbols+=int(s["symbols"])
        total_trades+=int(s["trades"])
        total_states+=int(s["state_rows"])
        skips.update({k:int(v) for k,v in s.get("skips",{}).items()})
        trans.update({k:int(v) for k,v in s.get("state_transitions",{}).items()})

        for k,v in s["stats"].items():
            x=acc[k]
            n=int(v["n"]);sm=float(v.get("sum_r",0.0))
            x["n"]+=n;x["sum_r"]+=sm
            x["pyr"]+=int(v.get("pyramided",0))
            if v.get("mean_r") is not None and float(v["mean_r"])>0:x["positive_shards"]+=1
            mx=v.get("max_r");mn=v.get("min_r")
            if mx is not None:x["max_r"]=float(mx) if x["max_r"] is None else max(x["max_r"],float(mx))
            if mn is not None:x["min_r"]=float(mn) if x["min_r"] is None else min(x["min_r"],float(mn))
            x["entry_states"].update({a:int(b) for a,b in v.get("entry_states",{}).items()})
            x["shards"].append({
                "n":n,"mean_r":v.get("mean_r"),"median_r":v.get("median_r"),
                "positive_rate":v.get("positive_rate"),"pyramided":v.get("pyramided",0)
            })

    stats={}
    for k,x in sorted(acc.items()):
        stats[k]={
            "n":x["n"],
            "mean_r":x["sum_r"]/x["n"] if x["n"] else None,
            "positive_shards":x["positive_shards"],
            "max_r":x["max_r"],"min_r":x["min_r"],
            "pyramided":x["pyr"],
            "entry_states":dict(x["entry_states"]),
            "shards":x["shards"]
        }

    out={
        "block":"D25","status":"PASS","dataset_id":"DRUMMOND_CANONICAL_8E9A1D784E3893D9",
        "symbols":total_symbols,"trades":total_trades,"state_rows":total_states,
        "skips":dict(skips),"stats":stats,"state_transitions":dict(trans),
        "contract":{
            "continuous_state_machine":True,
            "exhaust_standalone_entry":False,
            "factory02_lifecycle_used":False,
            "further_out":"5/2+5/9 only",
            "live_pldot_refresh_entry_and_pyramid":True,
            "pyramid_caps":[0,1,2],
            "flow_variants":[1,2,3],
            "modes":["STRICT","PROXY"],
            "selection_or_optimization":False
        },
        "promotion_allowed":False
    }
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/"D25.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
        "D25 FULL DRUMMOND STATE MACHINE",
        "STATUS: PASS",
        f"SYMBOLS: {total_symbols}",
        f"TRADES: {total_trades}",
        f"STATE_ROWS: {total_states}",
        "EXHAUST STANDALONE ENTRY: NO",
        "FACTORY02: NO",
        "FURTHER OUT: 5/2+5/9",
        "SELECTION/OPTIMIZATION: NO"
    ]
    for k,v in stats.items():
        mr="NA" if v["mean_r"] is None else f"{v['mean_r']:.8f}"
        lines.append(
            f"{k}: N={v['n']} MEAN_R={mr} POS_SHARDS={v['positive_shards']}/7 "
            f"PYRAMIDED={v['pyramided']} MAX_R={v['max_r']} MIN_R={v['min_r']}"
        )
    (a.out/"D25.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
