#!/usr/bin/env python3
import argparse,bisect,csv,math,statistics
from datetime import datetime,timezone
from pathlib import Path
from drummond_replay01 import read_xfbar

VOL_BARS=288
SIGMA=2.0
HOLD_SECONDS=1800

def ts(s):
    return int(datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(timezone.utc).timestamp())

def iso(x):
    return datetime.fromtimestamp(x,tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def aligned_idx(mt,t,max_lag=300):
    i=bisect.bisect_left(mt,t)
    if i>=len(mt) or mt[i]-t>max_lag: return None
    return i

def target_z30(mt,op,event_ts):
    i0=aligned_idx(mt,event_ts)
    if i0 is None or i0<=VOL_BARS: return None
    t0=mt[i0]
    i30=aligned_idx(mt,t0+1800)
    if i30 is None or not(op[i0]>0 and op[i30]>0): return None
    vals=[]
    for i in range(i0-VOL_BARS,i0):
        if i<=0 or op[i-1]<=0 or op[i]<=0: return None
        vals.append(math.log(op[i]/op[i-1]))
    sd=statistics.stdev(vals)
    if not math.isfinite(sd) or sd<=0: return None
    r30=math.log(op[i30]/op[i0])
    return t0,i30,r30/(sd*math.sqrt(6.0))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--xau",type=Path,required=True)
    ap.add_argument("--external",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)

    hdr,bars=read_xfbar(a.xau)
    assert hdr["period_seconds"]==300, hdr
    mt=[int(x[0]) for x in bars]
    op=[float(x[1]) for x in bars]

    ext=list(csv.DictReader(a.external.open(encoding="utf-8-sig"),delimiter=";"))
    assert ext
    results=[]; skipped=[]
    for r in ext:
        e=ts(r["UTC_TIME"])
        z=target_z30(mt,op,e)
        if z is None:
            skipped.append((r["UTC_TIME"],r["EVENT"],"NO_XAU_Z30"))
            continue
        aligned,i30,target=z
        i60=aligned_idx(mt,aligned+3600)
        if i60 is None or op[i30]<=0 or op[i60]<=0:
            skipped.append((r["UTC_TIME"],r["EVENT"],"NO_HOLD30_EXIT"))
            continue
        external=float(r["EXTERNAL_GAP_Z30"])
        d=external-target
        side=1 if d>0 else -1
        signal=abs(d)>=SIGMA
        gross_log=side*math.log(op[i60]/op[i30]) if signal else 0.0
        gross_delta=side*(op[i60]-op[i30]) if signal else 0.0
        results.append({
          "UTC_TIME":r["UTC_TIME"],
          "ALIGNED_M5_UTC":iso(aligned),
          "EVENT":r["EVENT"],
          "USD_STRENGTH_Z30":r["USD_STRENGTH_Z30"],
          "EXTERNAL_GAP_Z30":f"{external:.10f}",
          "XAU_TARGET_Z30":f"{target:.10f}",
          "D":f"{d:.10f}",
          "SIGNAL":"Y" if signal else "N",
          "SIDE":"LONG" if side>0 else "SHORT",
          "ENTRY_UTC":iso(mt[i30]),
          "EXIT_UTC":iso(mt[i60]),
          "ENTRY_OPEN":f"{op[i30]:.10f}",
          "EXIT_OPEN":f"{op[i60]:.10f}",
          "GROSS_HOLD30_DELTA":f"{gross_delta:.10f}",
          "GROSS_HOLD30_LOGRET":f"{gross_log:.12f}",
        })

    out=a.out/"N29_XAUUSD_REPLAY.csv"
    fields=list(results[0])
    with out.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";")
        w.writeheader();w.writerows(results)

    with (a.out/"N29_SKIPPED.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.writer(f,delimiter=";"); w.writerow(["UTC_TIME","EVENT","REASON"]); w.writerows(skipped)

    sig=[r for r in results if r["SIGNAL"]=="Y"]
    wins=[r for r in sig if float(r["GROSS_HOLD30_LOGRET"])>0]
    losses=[r for r in sig if float(r["GROSS_HOLD30_LOGRET"])<0]
    flats=[r for r in sig if float(r["GROSS_HOLD30_LOGRET"])==0]
    gross=[float(r["GROSS_HOLD30_LOGRET"]) for r in sig]
    deltas=[float(r["GROSS_HOLD30_DELTA"]) for r in sig]

    lines=[
      "N29 XAUUSD CANONICAL RESEARCH REPLAY",
      "STATUS: PASS",
      f"EXTERNAL_ROWS={len(ext)}",
      f"EVALUATED_ROWS={len(results)}",
      f"SKIPPED_ROWS={len(skipped)}",
      f"SIGMA={SIGMA:.1f}",
      "DELAY_MIN=30",
      "HOLD_MIN=30",
      f"SIGNALS={len(sig)}",
      f"WINS_GROSS={len(wins)}",
      f"LOSSES_GROSS={len(losses)}",
      f"FLAT_GROSS={len(flats)}",
      f"GROSS_WIN_RATE={(len(wins)/len(sig)*100 if sig else 0):.4f}",
      f"MEAN_GROSS_LOGRET={(statistics.fmean(gross) if gross else 0):.12f}",
      f"MEAN_GROSS_XAU_DELTA={(statistics.fmean(deltas) if deltas else 0):.10f}",
      "COSTS_SPREAD_SLIPPAGE=NOT_INCLUDED",
      "PURPOSE=research signal/outcome precheck before final MT4 validation",
    ]
    (a.out/"N29.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
