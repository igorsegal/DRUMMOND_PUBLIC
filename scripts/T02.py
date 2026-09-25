#!/usr/bin/env python3
"""
T02 — TAKBIR signal predictive audit.

Uses the frozen causal T01 reconstruction. Tests what happens AFTER signal close.
Reference = signal bar close; H1 means next H1 close, etc.
No trading/PnL, no fitted filters.

For each signal and horizon:
- signed normalized return in signal direction
- directional hit
- MFE / MAE
- matched same-symbol unconditional baseline for the same direction
"""
import argparse,csv,json,math
from collections import Counter,defaultdict
from pathlib import Path
from drummond_replay01 import read_xfbar
from T01 import reconstruct

HORIZONS=(1,4,12,24,72)
FIELDS=["SYMBOL","SIGNAL","HORIZON","N","SUM_SIGNED_RET","WIN_N","SUM_BASE_RET","SUM_BASE_WIN_EXP","SUM_MFE","SUM_MAE"]

def newa():
    return {"n":0,"sum":0.0,"win":0,"base":0.0,"basewin":0.0,"mfe":0.0,"mae":0.0}

def wait_bucket(x):
    if x==0:return "0"
    if x==1:return "1"
    if x<=4:return "2_4"
    if x<=8:return "5_8"
    if x<=16:return "9_16"
    return "17_PLUS"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    cells=defaultdict(newa);waits=Counter();errs=[];syms=0;signal_counts=Counter()
    for p in sorted(a.data_root.rglob("*_H1.bin")):
        sym=p.name[:-7]
        try:
            hdr,bars=read_xfbar(p)
            if hdr["period_seconds"]!=3600:continue
            point=float(hdr["point"]);r=reconstruct(bars)
            if r["errors"]:raise RuntimeError(",".join(r["errors"]))
            syms+=1

            rp=[0.0]
            for b in bars:rp.append(rp[-1]+max(0.0,float(b[2])-float(b[3])))

            # same-symbol unconditional future-return baseline
            base={}
            for h in HORIZONS:
                vals=[]
                ups=0
                for i in range(24,len(bars)-h):
                    scale=(rp[i]-rp[i-24])/24.0
                    if not math.isfinite(scale) or scale<=point*0.5:continue
                    rr=(float(bars[i+h][4])-float(bars[i][4]))/scale
                    if not math.isfinite(rr):continue
                    vals.append(rr);ups+=int(rr>0)
                if vals:
                    base[h]=(sum(vals)/len(vals),ups/len(vals))

            for e in r["events"]:
                sig="AZAN" if e["type"].startswith("AZAN") else "IQAMAT"
                signal_counts[e["type"]]+=1
                if sig=="IQAMAT":waits[wait_bucket(int(e["wait_bars"]))]+=1
                i=int(e["idx"]);d=int(e["dir"])
                if i<24:continue
                scale=(rp[i]-rp[i-24])/24.0
                if not math.isfinite(scale) or scale<=point*0.5:continue
                ref=float(bars[i][4])

                for h in HORIZONS:
                    if i+h>=len(bars) or h not in base:continue
                    y=d*(float(bars[i+h][4])-ref)/scale
                    future=bars[i+1:i+h+1]
                    if d>0:
                        mfe=(max(float(b[2]) for b in future)-ref)/scale
                        mae=(ref-min(float(b[3]) for b in future))/scale
                    else:
                        mfe=(ref-min(float(b[3]) for b in future))/scale
                        mae=(max(float(b[2]) for b in future)-ref)/scale
                    bm,bup=base[h]
                    bdir=d*bm
                    bwin=bup if d>0 else (1.0-bup)
                    z=cells[(sym,sig,h)]
                    z["n"]+=1;z["sum"]+=y;z["win"]+=int(y>0)
                    z["base"]+=bdir;z["basewin"]+=bwin
                    z["mfe"]+=mfe;z["mae"]+=mae

        except Exception as ex:
            errs.append({"symbol":sym,"error":str(ex)})

    rows=[]
    for (sym,sig,h),z in sorted(cells.items()):
        rows.append({
          "SYMBOL":sym,"SIGNAL":sig,"HORIZON":h,"N":z["n"],
          "SUM_SIGNED_RET":f"{z['sum']:.12f}","WIN_N":z["win"],
          "SUM_BASE_RET":f"{z['base']:.12f}","SUM_BASE_WIN_EXP":f"{z['basewin']:.12f}",
          "SUM_MFE":f"{z['mfe']:.12f}","SUM_MAE":f"{z['mae']:.12f}"
        })
    with (a.out/"T02.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";");w.writeheader();w.writerows(rows)

    out={
      "block":"T02","status":"PASS" if syms and rows and not errs else "FAIL",
      "symbols":syms,"signal_counts":dict(signal_counts),"iqamat_wait_buckets":dict(waits),
      "errors":len(errs),"horizons_h1_bars":list(HORIZONS),
      "contract":{
        "source":"T01 frozen causal reconstruction",
        "reference":"signal bar close",
        "future_starts_after_signal_close":True,
        "normalization":"prior 24 completed H1 mean high-low range",
        "matched_baseline":"same-symbol unconditional forward return, same direction",
        "trading_pnl":False,"future_filter":False,"selection_or_optimization":False,"lookahead":False
      }
    }
    (a.out/"T02.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.out/"T02_ERR.json").write_text(json.dumps(errs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"T02 {out['status']} symbols={syms} rows={len(rows)} signals={sum(signal_counts.values())} errors={len(errs)} waits={dict(waits)}")
    if out["status"]!="PASS":raise SystemExit(2)
if __name__=="__main__":main()
