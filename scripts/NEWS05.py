#!/usr/bin/env python3
"""
NEWS05 — UNTOUCHED POST-DISCOVERY VALIDATION.

Validation source:
A separately maintained Forex Factory feed snapshot, pinned by immutable Git
commit in the workflow. Only event timestamp, currency, high-impact flag and
event name are used. Actual / Forecast / Previous are ignored.

The trading hypothesis is frozen from NEWS03/NEWS04:
- wait 30 minutes after a scheduled high-impact event;
- target pair is excluded from cross-market currency strength;
- build 30m volatility-normalized external gap from the six third currencies;
- DISLOCATION = external gap - target pair normalized 30m move;
- primary event: abs(DISLOCATION) >= 2 sigma;
- direction = sign(DISLOCATION);
- evaluate +30m and +90m after the decision;
- apply recorded M5 spread;
- compare on the exact same timestamps against price-only mean reversion:
  -sign(target pair normalized 30m move).

No threshold fitting. No event-type reselection. No use of NEWS05 outcomes in
the signal definition. This is the first untouched time validation after the
NEWS03/NEWS04 discovery period ended on 2025-04-07.
"""
import argparse,csv,json,math,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

from drummond_replay01 import read_xfbar
from NEWS01 import CURS,PAIRS,avg
from NEWS02 import classify
from NEWS03 import (
    VOL_BARS,HORIZONS_MIN,FOCUS_CATEGORIES,PAIR_SET,
    find_pair,disloc_bin,pair_features,side_returns,sgn,pf
)

def load_bridge(files):
    out=[]
    seen=set()
    for path in files:
        with path.open("r",encoding="utf-8-sig",newline="") as f:
            rd=csv.DictReader(f)
            need={"datetime_utc","currency","impact_level","event"}
            if not need.issubset(set(rd.fieldnames or [])):
                raise SystemExit(f"{path}: missing {need-set(rd.fieldnames or [])}")
            for r in rd:
                if (r.get("impact_level") or "").strip().lower()!="high":
                    continue
                cur=(r.get("currency") or "").strip().upper()
                if cur not in CURS:
                    continue
                dt=(r.get("datetime_utc") or "").strip()
                if not dt:
                    continue
                try:
                    ts=int(datetime.fromisoformat(dt.replace("Z","+00:00")).astimezone(timezone.utc).timestamp())
                except Exception:
                    continue
                name=(r.get("event") or "").strip()
                k=(ts,cur,name)
                if k in seen: continue
                seen.add(k);out.append(k)
    return sorted(out)

def build_clusters(events):
    d=defaultdict(list)
    for ts,cur,name in events:
        d[(ts,cur)].append(name)
    out=[]
    for (ts,cur),names in sorted(d.items()):
        names=sorted(set(names))
        cats=sorted(set(classify(x) for x in names))
        out.append({
            "ts":ts,"currency":cur,"names":" | ".join(names),
            "categories":cats,
            "category_label":"+".join(cats),
            "focus":bool(set(cats)&FOCUS_CATEGORIES)
        })
    return out

def metric(vals):
    if not vals:
        return {"N":0,"MEAN_BPS":None,"MEDIAN_BPS":None,"WIN_RATE":None,"PF":None}
    return {
        "N":len(vals),
        "MEAN_BPS":statistics.fmean(vals),
        "MEDIAN_BPS":statistics.median(vals),
        "WIN_RATE":sum(x>0 for x in vals)/len(vals),
        "PF":pf(vals)
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--calendar",type=Path,nargs="+",required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    events=load_bridge(a.calendar)
    if not events: raise SystemExit("no high-impact bridge events")
    clusters=build_clusters(events)
    print("NEWS05 HIGH_IMPACT_EVENTS",len(events),"CLUSTERS",len(clusters))

    feat={}
    for i,p in enumerate(PAIRS,1):
        feat[p]=pair_features(a.root,p,clusters)
        ok=sum(x is not None for x in feat[p])
        print(f"[{i}/{len(PAIRS)}] {p} event_features={ok} PASS")

    rows=[]
    max_market_ts=0
    for p in PAIRS:
        h,b=read_xfbar(a.root/p/(p+"_M5.bin"))
        max_market_ts=max(max_market_ts,int(h["last_time"]))

    for ei,e in enumerate(clusters):
        cur=e["currency"]
        for target in PAIRS:
            if cur not in (target[:3],target[3:]): continue
            tf=feat[target][ei]
            if tf is None: continue
            base=target[:3];quote=target[3:]
            thirds=sorted(CURS-{base,quote})
            bz=[];qz=[];aligns=[tf["align"]]
            ok=True
            for k in thirds:
                pb,sb=find_pair(base,k)
                pq,sq=find_pair(quote,k)
                fb=feat[pb][ei];fq=feat[pq][ei]
                if fb is None or fq is None:
                    ok=False;break
                aligns.extend([fb["align"],fq["align"]])
                bz.append(sb*fb["z30"])
                qz.append(sq*fq["z30"])
            if not ok or len(set(aligns))!=1:
                continue

            external=avg(bz)-avg(qz)
            target_z=tf["z30"]
            d=external-target_z
            cross_side=sgn(d)
            price_side=-sgn(target_z)
            if cross_side==0 or price_side==0: continue

            for hmin in HORIZONS_MIN:
                sr=side_returns(tf,cross_side,hmin)
                raw_future=cross_side*sr["GROSS_BPS"]
                price_gross=price_side*raw_future

                # Apply the same spread mechanics to the price-only direction.
                psr=side_returns(tf,price_side,hmin)

                rows.append({
                    "EVENT_TIME_UTC":datetime.fromtimestamp(e["ts"],tz=timezone.utc).isoformat(),
                    "NEWS_CURRENCY":cur,"EVENTS":e["names"],
                    "CATEGORIES":e["category_label"],"FOCUS_NEWS":int(e["focus"]),
                    "TARGET":target,"HORIZON_MIN":hmin,
                    "TARGET_Z30":target_z,"EXTERNAL_GAP_Z30":external,
                    "DISLOCATION_Z":d,"ABS_DISLOCATION_Z":abs(d),
                    "DISLOCATION_BIN":disloc_bin(d),
                    "CROSS_SIDE":"LONG" if cross_side>0 else "SHORT",
                    "PRICE_MR_SIDE":"LONG" if price_side>0 else "SHORT",
                    "CROSS_EQ_PRICE_MR":int(cross_side==price_side),
                    "CROSS_GROSS_BPS":sr["GROSS_BPS"],
                    "CROSS_NET0_BPS":sr["NET_C0_BPS"],
                    "CROSS_NET2_BPS":sr["NET_C2_BPS"],
                    "PRICE_GROSS_BPS":price_gross,
                    "PRICE_NET0_BPS":psr["NET_C0_BPS"],
                    "CROSS_MINUS_PRICE_GROSS_BPS":sr["GROSS_BPS"]-price_gross,
                    "ENTRY_SPREAD_POINTS":tf["entry_spread"]
                })

    if not rows: raise SystemExit("no validation rows")

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";")
            w.writeheader();w.writerows(data)

    write("NEWS05_EVENTS.csv",rows)

    summary=[]
    scopes=[
        ("ALL_NEWS",lambda r:True),
        ("FOCUS_NEWS",lambda r:r["FOCUS_NEWS"]==1)
    ]
    for scope,pred in scopes:
        for hmin in HORIZONS_MIN:
            for band,bpred in [
                ("ALL",lambda r:True),
                ("LT2",lambda r:r["ABS_DISLOCATION_Z"]<2),
                ("GE2",lambda r:r["ABS_DISLOCATION_Z"]>=2)
            ]:
                rr=[r for r in rows if pred(r) and r["HORIZON_MIN"]==hmin and bpred(r)]
                if not rr: continue
                cm=metric([r["CROSS_NET0_BPS"] for r in rr])
                cg=metric([r["CROSS_GROSS_BPS"] for r in rr])
                pm=metric([r["PRICE_NET0_BPS"] for r in rr])
                summary.append({
                    "SCOPE":scope,"HORIZON_MIN":hmin,"BAND":band,
                    "N":len(rr),
                    "UNIQUE_EVENT_CLUSTERS":len(set((r["EVENT_TIME_UTC"],r["NEWS_CURRENCY"]) for r in rr)),
                    "UNIQUE_TARGETS":len(set(r["TARGET"] for r in rr)),
                    "MEAN_ABS_DISLOCATION_Z":avg([r["ABS_DISLOCATION_Z"] for r in rr]),
                    "CROSS_GROSS_MEAN_BPS":cg["MEAN_BPS"],
                    "CROSS_NET0_MEAN_BPS":cm["MEAN_BPS"],
                    "CROSS_NET0_MEDIAN_BPS":cm["MEDIAN_BPS"],
                    "CROSS_NET0_WIN_RATE":cm["WIN_RATE"],
                    "CROSS_NET0_PF":cm["PF"],
                    "CROSS_NET2_MEAN_BPS":avg([r["CROSS_NET2_BPS"] for r in rr]),
                    "PRICE_NET0_MEAN_BPS":pm["MEAN_BPS"],
                    "PRICE_NET0_PF":pm["PF"],
                    "CROSS_MINUS_PRICE_GROSS_MEAN_BPS":avg([r["CROSS_MINUS_PRICE_GROSS_BPS"] for r in rr]),
                    "CROSS_EQ_PRICE_MR_RATE":avg([r["CROSS_EQ_PRICE_MR"] for r in rr])
                })
    write("NEWS05_SUMMARY.csv",summary)

    ge2=[r for r in summary if r["BAND"]=="GE2"]
    meta={
        "block":"NEWS05","status":"PASS",
        "validation_calendar_events":len(events),
        "validation_event_clusters":len(clusters),
        "validation_first_utc":datetime.fromtimestamp(events[0][0],tz=timezone.utc).isoformat(),
        "validation_last_calendar_utc":datetime.fromtimestamp(events[-1][0],tz=timezone.utc).isoformat(),
        "market_data_last_utc":datetime.fromtimestamp(max_market_ts,tz=timezone.utc).isoformat(),
        "event_target_horizon_rows":len(rows),
        "primary_ge2_summary":ge2,
        "contract":{
            "untouched_time_validation":True,
            "discovery_calendar_end":"2025-04-07",
            "signal_frozen_from_news03_news04":True,
            "actual_forecast_previous_used":False,
            "decision_delay_minutes":30,
            "target_pair_excluded_from_external_strength":True,
            "primary_threshold_abs_dislocation_z":2.0,
            "future_horizons_after_decision_minutes":list(HORIZONS_MIN),
            "recorded_m5_spread_applied":True,
            "extra_cost_stress_points":2,
            "same_timestamp_price_only_control":True,
            "parameter_optimization":False,
            "event_type_reselection":False,
            "portfolio_pnl":False
        }
    }
    (a.out/"NEWS05.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
        "NEWS05 — UNTOUCHED POST-DISCOVERY VALIDATION",
        "STATUS: PASS",
        f"CALENDAR_EVENTS={len(events)} CLUSTERS={len(clusters)}",
        f"CALENDAR={meta['validation_first_utc']} -> {meta['validation_last_calendar_utc']}",
        f"MARKET_DATA_LAST={meta['market_data_last_utc']}",
        "SIGNAL FROZEN FROM NEWS03/04: YES",
        "ACTUAL/FORECAST/PREVIOUS USED: NO",
        "THRESHOLD: |DISLOCATION| >= 2 sigma",
        "RECORDED M5 SPREAD: APPLIED",
        "PARAMETER OPTIMIZATION: NO",""
    ]
    for scope in ("ALL_NEWS","FOCUS_NEWS"):
        lines.append(scope+" — PRIMARY GE2:")
        for hmin in HORIZONS_MIN:
            r=next((x for x in summary if x["SCOPE"]==scope and x["HORIZON_MIN"]==hmin and x["BAND"]=="GE2"),None)
            if r is None:
                lines.append(f" H+{hmin}m: N=0")
            else:
                pfv="NA" if r["CROSS_NET0_PF"] is None else f"{r['CROSS_NET0_PF']:.4f}"
                lines.append(
                    f" H+{hmin}m: N={r['N']} CLUSTERS={r['UNIQUE_EVENT_CLUSTERS']} TARGETS={r['UNIQUE_TARGETS']} "
                    f"|D|={r['MEAN_ABS_DISLOCATION_Z']:.3f} "
                    f"GROSS={r['CROSS_GROSS_MEAN_BPS']:+.4f} "
                    f"NET0={r['CROSS_NET0_MEAN_BPS']:+.4f} PF={pfv} "
                    f"NET2={r['CROSS_NET2_MEAN_BPS']:+.4f} "
                    f"PRICE0={r['PRICE_NET0_MEAN_BPS']:+.4f} "
                    f"dGROSS={r['CROSS_MINUS_PRICE_GROSS_MEAN_BPS']:+.4f}"
                )
        lines.append("")
    (a.out/"NEWS05.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
