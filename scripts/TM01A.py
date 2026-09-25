#!/usr/bin/env python3
import argparse,csv,json,statistics
from pathlib import Path

FIELDS=["SCOPE","MODE","N","MEAN_R","MEDIAN_R","SUM_R","WIN_RATE","PROFIT_FACTOR","MIN_R","MAX_R"]

def collect_metric(vals):
    if not vals:
        return {"n":0}
    pos=sum(x for x in vals if x>0)
    neg=-sum(x for x in vals if x<0)
    return {
        "n":len(vals),
        "mean":sum(vals)/len(vals),
        "median":statistics.median(vals),
        "sum":sum(vals),
        "win_rate":sum(x>0 for x in vals)/len(vals),
        "profit_factor":pos/neg if neg>0 else None,
        "min":min(vals),"max":max(vals)
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)

    js=sorted(a.root.rglob("*_TM01.json"))
    cs=sorted(a.root.rglob("*_TM01_TRADES.csv"))
    if len(js)!=3 or len(cs)!=3:
        raise SystemExit(f"TM01A expected 3 symbols json={len(js)} csv={len(cs)}")

    symbols=[]
    totals={"bars":0,"takbir":0,"levels":0,"azan":0,"iqamat":0,"trades":0}
    allrows=[]
    per_symbol={}
    for p in js:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s["status"]!="PASS":
            raise SystemExit(f"bad symbol summary: {p}")
        c=s["contract"]
        if c["lookahead"] or c["selection_or_optimization"]:
            raise SystemExit(f"causal contract violation: {p}")
        sym=s["symbol"]; symbols.append(sym)
        totals["bars"]+=int(s["data"]["bar_count"])
        totals["takbir"]+=int(s["takbir_candidates"])
        totals["levels"]+=int(s["confirmed_levels"])
        totals["azan"]+=int(s["azan"])
        totals["iqamat"]+=int(s["iqamat"])
        totals["trades"]+=int(s["trades"])
        per_symbol[sym]=s["results"]

    for p in cs:
        with p.open("r",encoding="utf-8-sig",newline="") as f:
            allrows.extend(list(csv.DictReader(f,delimiter=";")))

    if len(allrows)!=totals["trades"]:
        raise SystemExit(f"trade count mismatch {len(allrows)} != {totals['trades']}")

    rows=[]
    results={}
    for scope in ("ALL","LONG","SHORT"):
        rr=allrows if scope=="ALL" else [x for x in allrows if x["SIDE"]==scope]
        results[scope]={}
        for mode,col in (("GROSS","GROSS_R"),("SPREAD","SPREAD_R")):
            vals=[float(x[col]) for x in rr]
            m=collect_metric(vals)
            results[scope][mode]=m
            rows.append({
                "SCOPE":scope,"MODE":mode,"N":m.get("n",0),
                "MEAN_R":f"{m.get('mean',0):.10f}",
                "MEDIAN_R":f"{m.get('median',0):.10f}",
                "SUM_R":f"{m.get('sum',0):.10f}",
                "WIN_RATE":f"{m.get('win_rate',0):.10f}",
                "PROFIT_FACTOR":f"{(m.get('profit_factor') or 0):.10f}",
                "MIN_R":f"{m.get('min',0):.10f}",
                "MAX_R":f"{m.get('max',0):.10f}"
            })

    with (a.out/"TM01A.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";")
        w.writeheader();w.writerows(rows)

    out={
        "block":"TM01",
        "status":"PASS",
        "symbols":symbols,
        "totals":totals,
        "results":results,
        "per_symbol":per_symbol,
        "contract":{
            "timeframe":"M1",
            "lookahead":False,
            "selection_or_optimization":False,
            "spread_mode":"historical MT4 M1 field",
            "fees":False,
            "slippage":False
        }
    }
    (a.out/"TM01.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
        "TAKBIR M1 TM01 — 3 SYMBOL AGGREGATE",
        "STATUS: PASS",
        "SYMBOLS: "+", ".join(symbols),
        f"M1_BARS: {totals['bars']}",
        f"TAKBIR: {totals['takbir']}",
        f"LEVELS: {totals['levels']}",
        f"AZAN: {totals['azan']}",
        f"IQAMAT: {totals['iqamat']}",
        f"TRADES: {totals['trades']}",
        "LOOKAHEAD: NO",
        "SELECTION/OPTIMIZATION: NO"
    ]
    for scope in ("ALL","LONG","SHORT"):
        g=results[scope]["GROSS"]; s=results[scope]["SPREAD"]
        lines.append(
            f"{scope} GROSS: N={g['n']} MEAN_R={g['mean']:+.6f} SUM_R={g['sum']:+.3f} "
            f"WIN={g['win_rate']:.6f} PF={(g['profit_factor'] or 0):.6f}"
        )
        lines.append(
            f"{scope} SPREAD: N={s['n']} MEAN_R={s['mean']:+.6f} SUM_R={s['sum']:+.3f} "
            f"WIN={s['win_rate']:.6f} PF={(s['profit_factor'] or 0):.6f}"
        )
    (a.out/"TM01.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
