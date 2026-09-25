#!/usr/bin/env python3
import argparse,csv,json
from collections import Counter,defaultdict
from pathlib import Path

FIELDS=["SIGNAL","HORIZON","N","MEAN_SIGNED_RET","BASE_MEAN_SIGNED_RET","DELTA_RET","WIN_RATE","BASE_WIN_RATE","DELTA_WIN","MEAN_MFE","MEAN_MAE","SYMBOLS","POS_DELTA_SYMBOLS"]

def read_csv(p):
    with Path(p).open("r",encoding="utf-8-sig",newline="") as f:
        yield from csv.DictReader(f,delimiter=";")

def fmt(v):return f"{v:.12f}"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    js=sorted(a.root.rglob("T02.json"));cs=sorted(a.root.rglob("T02.csv"))
    if len(js)!=7 or len(cs)!=7:raise SystemExit(f"T02A expected 7 shards json={len(js)} csv={len(cs)}")
    syms=0;sc=Counter();waits=Counter()
    for p in js:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s["status"]!="PASS" or s["contract"]["lookahead"] or s["contract"]["selection_or_optimization"]:
            raise SystemExit(f"bad T02 shard {p}")
        syms+=int(s["symbols"]);sc.update({k:int(v) for k,v in s["signal_counts"].items()});waits.update({k:int(v) for k,v in s["iqamat_wait_buckets"].items()})

    agg=defaultdict(lambda:{"n":0,"sum":0.0,"win":0,"base":0.0,"basewin":0.0,"mfe":0.0,"mae":0.0})
    bysym=defaultdict(lambda:{"n":0,"sum":0.0,"base":0.0})
    for p in cs:
        for r in read_csv(p):
            key=(r["SIGNAL"],int(r["HORIZON"]));z=agg[key];n=int(r["N"])
            z["n"]+=n;z["sum"]+=float(r["SUM_SIGNED_RET"]);z["win"]+=int(r["WIN_N"]);z["base"]+=float(r["SUM_BASE_RET"]);z["basewin"]+=float(r["SUM_BASE_WIN_EXP"]);z["mfe"]+=float(r["SUM_MFE"]);z["mae"]+=float(r["SUM_MAE"])
            q=bysym[(r["SIGNAL"],int(r["HORIZON"]),r["SYMBOL"])]
            q["n"]+=n;q["sum"]+=float(r["SUM_SIGNED_RET"]);q["base"]+=float(r["SUM_BASE_RET"])

    rows=[];results=[]
    for sig in ("AZAN","IQAMAT"):
        for h in (1,4,12,24,72):
            z=agg[(sig,h)]
            if not z["n"]:continue
            mean=z["sum"]/z["n"];base=z["base"]/z["n"];win=z["win"]/z["n"];bwin=z["basewin"]/z["n"]
            symlist=[k for k in bysym if k[0]==sig and k[1]==h]
            pos=0;valid=0
            for k in symlist:
                q=bysym[k]
                if not q["n"]:continue
                valid+=1
                if (q["sum"]-q["base"])/q["n"]>0:pos+=1
            row={
              "SIGNAL":sig,"HORIZON":h,"N":z["n"],
              "MEAN_SIGNED_RET":fmt(mean),"BASE_MEAN_SIGNED_RET":fmt(base),"DELTA_RET":fmt(mean-base),
              "WIN_RATE":fmt(win),"BASE_WIN_RATE":fmt(bwin),"DELTA_WIN":fmt(win-bwin),
              "MEAN_MFE":fmt(z["mfe"]/z["n"]),"MEAN_MAE":fmt(z["mae"]/z["n"]),
              "SYMBOLS":valid,"POS_DELTA_SYMBOLS":pos
            }
            rows.append(row);results.append(row)
    a.out.mkdir(parents=True,exist_ok=True)
    with (a.out/"T02A.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";");w.writeheader();w.writerows(rows)
    out={"block":"T02","status":"PASS","symbols":syms,"signal_counts":dict(sc),"iqamat_wait_buckets":dict(waits),"results":results,
         "contract":{"trading_pnl":False,"lookahead":False,"selection_or_optimization":False}}
    (a.out/"T02.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["T02 TAKBIR SIGNAL PREDICTIVE AUDIT","STATUS: PASS",f"SYMBOLS: {syms}",
           f"AZAN: {sc['AZAN_UP']+sc['AZAN_DN']}","IQAMAT: "+str(sc["IQAMAT_UP"]+sc["IQAMAT_DN"]),
           "IQAMAT_WAIT: "+json.dumps(dict(waits),sort_keys=True),"TRADING/PNL: NO","LOOKAHEAD: NO"]
    for r in rows:
        lines.append(f"{r['SIGNAL']} H{r['HORIZON']}: N={r['N']} MEAN={float(r['MEAN_SIGNED_RET']):+.6f} BASE={float(r['BASE_MEAN_SIGNED_RET']):+.6f} DELTA={float(r['DELTA_RET']):+.6f} WIN={float(r['WIN_RATE']):.6f} BASEWIN={float(r['BASE_WIN_RATE']):.6f} DWIN={float(r['DELTA_WIN']):+.6f} MFE={float(r['MEAN_MFE']):.6f} MAE={float(r['MEAN_MAE']):.6f} SYMS+={r['POS_DELTA_SYMBOLS']}/{r['SYMBOLS']}")
    (a.out/"T02.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
if __name__=="__main__":main()
