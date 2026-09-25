#!/usr/bin/env python3
import argparse,csv,json
from collections import defaultdict
from pathlib import Path

MODELS=("BASE","PRICE","DRUMMOND","PRICE_DRUMMOND")
FIELDS=[
 "HORIZON","MODEL","TEST_N",
 "RET_MSE","RET_GAIN_VS_BASE","RET_GAIN_VS_PRICE",
 "DIR_ACC","DIR_DELTA_VS_BASE","DIR_DELTA_VS_PRICE",
 "ABS_MSE","ABS_GAIN_VS_BASE","ABS_GAIN_VS_PRICE",
 "SYMBOLS","RET_BETTER_THAN_PRICE","DIR_BETTER_THAN_PRICE","ABS_BETTER_THAN_PRICE"
]

def read_csv(p):
    with Path(p).open("r",encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f,delimiter=";"):
            yield r

def fmt(v,n=12):
    return "" if v is None else f"{v:.{n}f}"

def write_csv(p,rows):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";")
        w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    js=sorted(a.root.rglob("D33.json"))
    cs=sorted(a.root.rglob("D33.csv"))
    if len(js)!=7 or len(cs)!=7:
        raise SystemExit(f"D33A expected 7 shards: json={len(js)} csv={len(cs)}")

    seen=evaluated=train_total=test_total=0
    horizons=None
    for p in js:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s.get("status")!="PASS" or int(s.get("errors",0))!=0:
            raise SystemExit(f"bad D33 shard {p}")
        c=s.get("contract",{})
        checks=[
          "fixed_time_split_before_run","test_period_not_used_for_training",
          "feature_sets_frozen_before_run","models_frozen_before_run",
          "all_features_known_at_event_time"
        ]
        if not all(bool(c.get(k)) for k in checks):raise SystemExit("D33 contract violation")
        if any(bool(c.get(k)) for k in (
          "trading_entries_used","stops_targets_used","pnl_used","future_filter_used",
          "parameter_search","selection_or_optimization","lookahead"
        )):raise SystemExit("D33 contamination/optimization violation")
        seen+=int(s["symbols_seen"]);evaluated+=int(s["symbols_evaluated"])
        train_total+=int(s["train_records_across_horizons"])
        test_total+=int(s["test_records_across_horizons"])
        hh=tuple(int(x) for x in s["horizons_h1_bars"])
        if horizons is None:horizons=hh
        elif horizons!=hh:raise SystemExit("D33 horizon mismatch")

    agg=defaultdict(lambda:{"n":0,"sse_ret":0.0,"correct":0,"sse_abs":0.0})
    bysym={}
    for p in cs:
        for r in read_csv(p):
            h=int(r["HORIZON"]);m=r["MODEL"];sym=r["SYMBOL"];n=int(r["TEST_N"])
            z=agg[(h,m)]
            z["n"]+=n;z["sse_ret"]+=float(r["SSE_RET"]);z["correct"]+=int(r["CORRECT_DIR"]);z["sse_abs"]+=float(r["SSE_ABS"])
            bysym[(h,sym,m)]={
              "n":n,"sse_ret":float(r["SSE_RET"]),
              "correct":int(r["CORRECT_DIR"]),"sse_abs":float(r["SSE_ABS"])
            }

    rows=[];results=[]
    for h in horizons:
        base=agg[(h,"BASE")];price=agg[(h,"PRICE")]
        if not base["n"] or not price["n"]:raise SystemExit(f"missing baseline h{h}")
        bmse=base["sse_ret"]/base["n"];pmse=price["sse_ret"]/price["n"]
        bacc=base["correct"]/base["n"];pacc=price["correct"]/price["n"]
        bamse=base["sse_abs"]/base["n"];pamse=price["sse_abs"]/price["n"]

        syms=sorted({k[1] for k in bysym if k[0]==h})
        for m in MODELS:
            z=agg[(h,m)]
            mse=z["sse_ret"]/z["n"];acc=z["correct"]/z["n"];amse=z["sse_abs"]/z["n"]
            ret_b=dir_b=abs_b=valid=0
            for sym in syms:
                cur=bysym.get((h,sym,m));pr=bysym.get((h,sym,"PRICE"))
                if not cur or not pr or cur["n"]!=pr["n"] or cur["n"]<=0:continue
                valid+=1
                cm=cur["sse_ret"]/cur["n"];ppm=pr["sse_ret"]/pr["n"]
                ca=cur["correct"]/cur["n"];ppa=pr["correct"]/pr["n"]
                cam=cur["sse_abs"]/cur["n"];ppam=pr["sse_abs"]/pr["n"]
                if cm<ppm:ret_b+=1
                if ca>ppa:dir_b+=1
                if cam<ppam:abs_b+=1

            row={
              "HORIZON":h,"MODEL":m,"TEST_N":z["n"],
              "RET_MSE":fmt(mse),
              "RET_GAIN_VS_BASE":fmt(1-mse/bmse if bmse else None),
              "RET_GAIN_VS_PRICE":fmt(1-mse/pmse if pmse else None),
              "DIR_ACC":fmt(acc),
              "DIR_DELTA_VS_BASE":fmt(acc-bacc),
              "DIR_DELTA_VS_PRICE":fmt(acc-pacc),
              "ABS_MSE":fmt(amse),
              "ABS_GAIN_VS_BASE":fmt(1-amse/bamse if bamse else None),
              "ABS_GAIN_VS_PRICE":fmt(1-amse/pamse if pamse else None),
              "SYMBOLS":valid,
              "RET_BETTER_THAN_PRICE":ret_b,
              "DIR_BETTER_THAN_PRICE":dir_b,
              "ABS_BETTER_THAN_PRICE":abs_b
            }
            rows.append(row)
            results.append({k:(float(v) if k not in ("HORIZON","MODEL","TEST_N","SYMBOLS","RET_BETTER_THAN_PRICE","DIR_BETTER_THAN_PRICE","ABS_BETTER_THAN_PRICE") and v!="" else v) for k,v in row.items()})

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D33A.csv",rows)

    summary={
      "block":"D33","status":"PASS",
      "symbols_seen":seen,"symbols_evaluated":evaluated,
      "train_records_across_horizons":train_total,
      "test_records_across_horizons":test_total,
      "split":{"train_before_utc":"2022-01-01T00:00:00Z","test_from_utc":"2022-01-01T00:00:00Z"},
      "results":results,
      "contract":{
        "fixed_time_split_before_run":True,
        "test_period_not_used_for_training":True,
        "feature_sets_frozen_before_run":True,
        "models_frozen_before_run":True,
        "trading_entries_used":False,"stops_targets_used":False,"pnl_used":False,
        "future_filter_used":False,"parameter_search":False,
        "selection_or_optimization":False,"lookahead":False
      },
      "interpretation":"PRICE_DRUMMOND versus PRICE is the direct incremental-value test. Positive RET_GAIN_VS_PRICE or ABS_GAIN_VS_PRICE means lower out-of-sample MSE; positive DIR_DELTA_VS_PRICE means better directional accuracy.",
      "interpretation_limit":"This is a temporal out-of-sample test inside the already-studied historical universe and only for the frozen simple PRICE representation used here."
    }
    (a.out/"D33.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
      "D33 PRICE vs DRUMMOND INCREMENTAL PREDICTIVE VALUE",
      "STATUS: PASS",
      f"SYMBOLS_SEEN: {seen}",
      f"SYMBOLS_EVALUATED: {evaluated}",
      f"TRAIN_RECORDS_X_HORIZONS: {train_total}",
      f"TEST_RECORDS_X_HORIZONS: {test_total}",
      "TRAIN: before 2022-01-01 UTC",
      "TEST: 2022-01-01 UTC and later",
      "TRADING/PNL: NO",
      "LOOKAHEAD: NO",
      "PARAMETER SEARCH: NO"
    ]
    for h in horizons:
        lines.append(f"H{h}:")
        for m in MODELS:
            r=next(x for x in rows if x["HORIZON"]==h and x["MODEL"]==m)
            lines.append(
              f"  {m}: RET_GAIN_BASE={float(r['RET_GAIN_VS_BASE']):+.6f} "
              f"RET_GAIN_PRICE={float(r['RET_GAIN_VS_PRICE']):+.6f} "
              f"DIR_ACC={float(r['DIR_ACC']):.6f} "
              f"DIR_DPRICE={float(r['DIR_DELTA_VS_PRICE']):+.6f} "
              f"ABS_GAIN_PRICE={float(r['ABS_GAIN_VS_PRICE']):+.6f} "
              f"RET_SYMS_BETTER={r['RET_BETTER_THAN_PRICE']}/{r['SYMBOLS']} "
              f"DIR_SYMS_BETTER={r['DIR_BETTER_THAN_PRICE']}/{r['SYMBOLS']} "
              f"ABS_SYMS_BETTER={r['ABS_BETTER_THAN_PRICE']}/{r['SYMBOLS']}"
            )
    (a.out/"D33.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
