#!/usr/bin/env python3
import argparse,csv,json,statistics
from collections import Counter,defaultdict
from pathlib import Path

FIELDS=["SIDE","TRADES","MEAN_R","MEDIAN_R","WIN_RATE","STOP_RATE","OPPOSITE_IQAMAT_RATE","AMBIG_RATE","SYMBOLS","POS_MEAN_SYMBOLS"]

def read_csv(p):
    with Path(p).open("r",encoding="utf-8-sig",newline="") as f:
        yield from csv.DictReader(f,delimiter=";")

def fmt(x): return f"{x:.10f}"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    js=sorted(a.root.rglob("T03.json"));cs=sorted(a.root.rglob("T03.csv"))
    if len(js)!=7 or len(cs)!=7: raise SystemExit(f"T03A expected 7 shards json={len(js)} csv={len(cs)}")

    syms=signals=trades=0;outs=Counter();errs=0
    for p in js:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s["status"]!="PASS" or s["contract"]["lookahead"] or s["contract"]["selection_or_optimization"]:
            raise SystemExit(f"bad T03 shard {p}")
        syms+=int(s["symbols"]);signals+=int(s["iqamat_signals"]);trades+=int(s["trades"]);outs.update({k:int(v) for k,v in s["outcomes"].items()});errs+=int(s["errors"])

    allrows=[]
    for p in cs: allrows.extend(list(read_csv(p)))
    if len(allrows)!=trades: raise SystemExit(f"T03 trade count mismatch {len(allrows)} != {trades}")

    rows=[];summary={}
    for side in ("ALL","LONG","SHORT"):
        rr=[x for x in allrows if side=="ALL" or x["SIDE"]==side]
        rs=[float(x["R"]) for x in rr]
        n=len(rs);oc=Counter(x["OUTCOME"] for x in rr)
        bysym=defaultdict(list)
        for x in rr:bysym[x["SYMBOL"]].append(float(x["R"]))
        pos=sum((sum(v)/len(v))>0 for v in bysym.values())
        row={
          "SIDE":side,"TRADES":n,"MEAN_R":fmt(sum(rs)/n),"MEDIAN_R":fmt(statistics.median(rs)),
          "WIN_RATE":fmt(sum(r>0 for r in rs)/n),
          "STOP_RATE":fmt(oc["STOP"]/n),
          "OPPOSITE_IQAMAT_RATE":fmt(oc["OPPOSITE_IQAMAT"]/n),
          "AMBIG_RATE":fmt(oc["AMBIGUOUS_ENTRY_STOP"]/n),
          "SYMBOLS":len(bysym),"POS_MEAN_SYMBOLS":pos
        }
        rows.append(row);summary[side]=row

    a.out.mkdir(parents=True,exist_ok=True)
    with (a.out/"T03A.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";");w.writeheader();w.writerows(rows)
    out={"block":"T03","status":"PASS","symbols":syms,"iqamat_signals":signals,"trades":trades,"outcomes":dict(outs),"results":summary,
         "contract":{"lookahead":False,"selection_or_optimization":False,"spread_slippage_fees":False}}
    (a.out/"T03.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["T03 TAKBIR SOURCE-FAITHFUL M5 EXECUTION","STATUS: PASS",f"SYMBOLS: {syms}",f"IQAMAT_SIGNALS: {signals}",f"TRADES: {trades}",
           "COSTS: NOT YET MODELED","LOOKAHEAD: NO","SELECTION/OPTIMIZATION: NO"]
    for r in rows:
        lines.append(f"{r['SIDE']}: N={r['TRADES']} MEAN_R={float(r['MEAN_R']):+.6f} MEDIAN_R={float(r['MEDIAN_R']):+.6f} WIN={float(r['WIN_RATE']):.6f} STOP={float(r['STOP_RATE']):.6f} OPP_IQ={float(r['OPPOSITE_IQAMAT_RATE']):.6f} AMBIG={float(r['AMBIG_RATE']):.6f} SYMS+={r['POS_MEAN_SYMBOLS']}/{r['SYMBOLS']}")
    (a.out/"T03.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
if __name__=="__main__":main()
