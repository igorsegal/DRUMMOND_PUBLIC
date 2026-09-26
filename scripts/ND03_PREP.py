#!/usr/bin/env python3
"""
ND03_PREP — precompute the external USD-strength leg for XAUUSD Strategy Tester.

Why:
Classic MT4 Strategy Tester reliably models only the tested symbol. Asking it
for historical M5 from seven additional FX symbols produced SHORT_M5_HISTORY,
so ND02 never reached its signal threshold.

This script moves ONLY the external cross-market leg offline, using the same
canonical XFBAR M5 data and the same 30m/prior-24h z-score construction.
The EA still computes XAUUSD's own TARGET_Z30 inside MT4 and still decides /
opens / closes orders in Strategy Tester.

No Actual/Forecast/Previous fields are used.
"""
import argparse,bisect,csv,math,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from drummond_replay01 import read_xfbar

VOL_BARS=288
LEGS={
    "AUDUSD":-1, # USD/AUD = -AUD/USD
    "USDCAD":+1,
    "USDCHF":+1,
    "EURUSD":-1,
    "GBPUSD":-1,
    "NZDUSD":-1,
    "USDJPY":+1,
}

def parse_utc(s):
    return int(datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(timezone.utc).timestamp())

def load_usd_clusters(path):
    d=defaultdict(list)
    with path.open("r",encoding="utf-8-sig",newline="") as f:
        rd=csv.DictReader(f,delimiter=";")
        need={"UTC_TIME","CURRENCY","IMPACT","EVENT"}
        if not need.issubset(set(rd.fieldnames or [])):
            raise SystemExit(f"bad NEWS file, missing {need-set(rd.fieldnames or [])}")
        for r in rd:
            if (r.get("CURRENCY") or "").strip().upper()!="USD": continue
            if (r.get("IMPACT") or "").strip().upper()!="HIGH": continue
            ts=parse_utc((r.get("UTC_TIME") or "").strip())
            d[ts].append((r.get("EVENT") or "").strip())
    return [(ts," | ".join(sorted(set(names)))) for ts,names in sorted(d.items())]

def sd_sample(vals):
    return statistics.stdev(vals) if len(vals)>=2 else None

def load_pair(root,pair):
    p=root/pair/(pair+"_M5.bin")
    if not p.exists():
        raise SystemExit("missing "+str(p))
    hdr,rows=read_xfbar(p)
    if hdr["period_seconds"]!=300:
        raise SystemExit(pair+" not M5")
    mt=[int(x[0]) for x in rows]
    op=[float(x[1]) for x in rows]
    return hdr,mt,op

def aligned_idx(mt,ts,max_lag=300):
    i=bisect.bisect_left(mt,ts)
    if i>=len(mt) or mt[i]-ts>max_lag:
        return None
    return i

def z30_for_event(mt,op,ts):
    i0=aligned_idx(mt,ts)
    if i0 is None or i0<=VOL_BARS:
        return None
    t0=mt[i0]
    i30=aligned_idx(mt,t0+1800)
    if i30 is None:
        return None
    if not (op[i0]>0 and op[i30]>0):
        return None

    vals=[]
    for i in range(i0-VOL_BARS,i0):
        if i<=0 or op[i-1]<=0 or op[i]<=0:
            return None
        vals.append(math.log(op[i]/op[i-1]))
    sd=sd_sample(vals)
    if sd is None or sd<=0:
        return None
    r30=math.log(op[i30]/op[i0])
    return t0,r30/(sd*math.sqrt(6.0))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--news",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)

    clusters=load_usd_clusters(a.news)
    print("USD_NEWS_CLUSTERS",len(clusters))

    data={}
    for pair in LEGS:
        data[pair]=load_pair(a.root,pair)
        print("LOAD",pair,"bars",len(data[pair][1]))

    out=[]
    skipped=[]
    for ts,names in clusters:
        zs=[]
        aligns=[]
        missing=[]
        for pair,orient in LEGS.items():
            _,mt,op=data[pair]
            z=z30_for_event(mt,op,ts)
            if z is None:
                missing.append(pair)
                continue
            align,zv=z
            aligns.append(align)
            zs.append(orient*zv)

        if missing or len(zs)!=7 or len(set(aligns))!=1:
            skipped.append((ts,names,",".join(missing) if missing else "ASYNC"))
            continue

        usd_strength=statistics.fmean(zs)
        external_gap=-usd_strength # XAUUSD has USD as quote currency
        out.append({
            "UTC_TIME":datetime.fromtimestamp(ts,tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ALIGNED_M5_UTC":datetime.fromtimestamp(aligns[0],tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "EVENT":names,
            "USD_STRENGTH_Z30":f"{usd_strength:.10f}",
            "EXTERNAL_GAP_Z30":f"{external_gap:.10f}",
            "LEG_COUNT":"7",
        })

    if not out:
        raise SystemExit("no ND03 external rows")

    op=a.out/"USD26.csv"
    with op.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(out[0]),delimiter=";")
        w.writeheader();w.writerows(out)

    sp=a.out/"ND03_SKIPPED.csv"
    with sp.open("w",encoding="utf-8",newline="") as f:
        w=csv.writer(f,delimiter=";")
        w.writerow(["UTC_TIME","EVENT","REASON"])
        for ts,names,reason in skipped:
            w.writerow([datetime.fromtimestamp(ts,tz=timezone.utc).isoformat(),names,reason])

    first=out[0]["UTC_TIME"]; last=out[-1]["UTC_TIME"]
    summary=[
        "ND03 PRECOMPUTED USD EXTERNAL STRENGTH",
        "STATUS: PASS",
        f"USD_NEWS_CLUSTERS={len(clusters)}",
        f"VALID_EXTERNAL_ROWS={len(out)}",
        f"SKIPPED_ROWS={len(skipped)}",
        f"FIRST={first}",
        f"LAST={last}",
        "LEGS="+",".join(LEGS),
        "FORMULA=mean oriented seven USD FX z30 legs",
        "XAUUSD_EXTERNAL_GAP=-USD_STRENGTH",
        "TARGET_XAUUSD_Z30=NOT_PRECOMPUTED; calculated in MT4 Strategy Tester",
        "ACTUAL_FORECAST_PREVIOUS_USED=NO",
    ]
    (a.out/"ND03.txt").write_text("\n".join(summary)+"\n",encoding="utf-8")
    print("\n".join(summary))

if __name__=="__main__":
    main()
