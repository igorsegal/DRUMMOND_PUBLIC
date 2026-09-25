#!/usr/bin/env python3
import argparse,csv,json
from collections import Counter
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    js=sorted(a.root.rglob("T01.json"))
    if len(js)!=7:raise SystemExit(f"T01A expected 7 shards, got {len(js)}")
    syms=0;tot=Counter();errs=0
    for p in js:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s["status"]!="PASS":raise SystemExit(f"bad shard {p}")
        c=s["contract"]
        if not c["five_bars_right_required"] or c["lookahead"] or c["selection_or_optimization"]:
            raise SystemExit("T01 causal contract violation")
        syms+=int(s["symbols"]);errs+=int(s["errors"])
        tot.update({k:int(v) for k,v in s["totals"].items()})
    az=tot["AZAN_UP"]+tot["AZAN_DN"];iq=tot["IQAMAT_UP"]+tot["IQAMAT_DN"]
    out={
      "block":"T01","status":"PASS" if syms and errs==0 else "FAIL",
      "symbols":syms,"totals":dict(tot),"azan_total":az,"iqamat_total":iq,
      "iqamat_per_azan":iq/az if az else None,"errors":errs,
      "contract":{"lookahead":False,"selection_or_optimization":False,"trading_pnl":False}
    }
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/"T01.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=[
      "T01 TAKBIR CAUSAL RECONSTRUCTION",
      f"STATUS: {out['status']}",
      f"SYMBOLS: {syms}",
      f"TAKBIR: {tot['TAKBIR']}",
      f"LEVELS: {tot['LEVELS']} (KIMMA={tot['KIMMA']} YAMMA={tot['YAMMA']})",
      f"AZAN: {az} (UP={tot['AZAN_UP']} DN={tot['AZAN_DN']})",
      f"IQAMAT: {iq} (UP={tot['IQAMAT_UP']} DN={tot['IQAMAT_DN']})",
      f"IQAMAT/AZAN: {(iq/az if az else 0):.6f}",
      "LOOKAHEAD: NO",
      "TRADING/PNL: NO"
    ]
    (a.out/"T01.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
    if out["status"]!="PASS":raise SystemExit(2)
if __name__=="__main__":main()
