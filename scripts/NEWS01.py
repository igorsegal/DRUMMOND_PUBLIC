#!/usr/bin/env python3
"""
NEWS01 — HIGH-IMPACT NEWS REGIME AUDIT.

External calendar:
Forex Factory historical archive dataset (2007-01-01..2025-04-07),
pinned and SHA-verified by the workflow. NEWS01 uses ONLY:
- event timestamp
- affected currency
- Impact == "High Impact Expected"
- event name for reporting

No Actual/Forecast/Previous values are used, so there is no revision/surprise
lookahead in this block.

For each high-impact event and each FX pair containing the affected currency:
- align event to the first M5 bar at/after event time (max 5 minutes);
- measure PRE30, POST30 and POST120 price response;
- measure recorded M5 spread behavior;
- build a matched non-news control from same weekday/time at +/- 1..4 weeks,
  excluding candidate controls within +/-120 minutes of any relevant
  high-impact event;
- compare event observation with the mean of >=2 valid matched controls.

This block asks only whether high-impact news defines a distinct market regime.
It does NOT trade and does NOT optimize thresholds.
"""
import argparse,bisect,csv,json,math,statistics
from collections import defaultdict
from datetime import datetime,timezone,timedelta
from pathlib import Path
from drummond_replay01 import read_xfbar

CURS={"AUD","CAD","CHF","EUR","GBP","JPY","NZD","USD"}
PAIRS=[
"AUDCAD","AUDCHF","AUDJPY","AUDNZD","AUDUSD",
"CADCHF","CADJPY","CHFJPY",
"EURAUD","EURCAD","EURCHF","EURGBP","EURJPY","EURNZD","EURUSD",
"GBPAUD","GBPCAD","GBPCHF","GBPJPY","GBPNZD","GBPUSD",
"NZDCAD","NZDCHF","NZDJPY","NZDUSD",
"USDCAD","USDCHF","USDJPY"
]
WINDOWS={"PRE30":(-30,0),"POST30":(0,30),"POST120":(0,120)}
CONTROL_WEEK_OFFSETS=(-4,-3,-2,-1,1,2,3,4)
EXCLUSION_MINUTES=120

def avg(x): return statistics.fmean(x) if x else None
def med(x): return statistics.median(x) if x else None

def parse_dt(s):
    s=s.strip()
    # Dataset timestamps carry explicit Asia/Tehran historical UTC offset.
    dt=datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError("calendar DateTime is not timezone-aware: "+s)
    return int(dt.astimezone(timezone.utc).timestamp())

def load_calendar(path):
    raw=[]
    with path.open("r",encoding="utf-8-sig",newline="") as f:
        rd=csv.DictReader(f)
        need={"DateTime","Currency","Impact","Event"}
        if not need.issubset(set(rd.fieldnames or [])):
            raise SystemExit("calendar missing columns: "+str(need-set(rd.fieldnames or [])))
        for r in rd:
            cur=(r.get("Currency") or "").strip().upper()
            imp=(r.get("Impact") or "").strip()
            if cur not in CURS or imp!="High Impact Expected":
                continue
            try: ts=parse_dt(r["DateTime"])
            except Exception: continue
            raw.append((ts,cur,(r.get("Event") or "").strip()))
    # Exact duplicate defense only; simultaneous distinct events remain.
    raw=sorted(set(raw))
    return raw

def build_event_index(events):
    bycur=defaultdict(list)
    for ts,cur,name in events:
        bycur[cur].append(ts)
    for c in bycur:
        bycur[c]=sorted(set(bycur[c]))
    return bycur

def relevant_news_near(ts,pair,event_index,minutes=EXCLUSION_MINUTES):
    lo=ts-minutes*60;hi=ts+minutes*60
    for cur in (pair[:3],pair[3:]):
        a=event_index.get(cur,[])
        j=bisect.bisect_left(a,lo)
        if j<len(a) and a[j]<=hi:
            return True
    return False

def metric_at(mb,mt,ts):
    i=bisect.bisect_left(mt,ts)
    if i>=len(mt) or mt[i]-ts>300:
        return None
    # PRE30 needs i-6, POST120 needs i+24.
    if i<6 or i+24>=len(mb):
        return None

    def window(a,b):
        bars=mb[a:b]
        if not bars:return None
        start=float(bars[0][1])
        if start<=0:return None
        end_open=float(mb[b][1]) if b<len(mb) else float(bars[-1][4])
        absret=abs(math.log(end_open/start))*10000.0
        signed=math.log(end_open/start)*10000.0
        hi=max(float(x[2]) for x in bars);lo=min(float(x[3]) for x in bars)
        rng=(hi-lo)/start*10000.0
        spreads=[max(0,int(x[6])) for x in bars]
        return {
            "ABS_RETURN_BPS":absret,
            "SIGNED_RETURN_BPS":signed,
            "RANGE_BPS":rng,
            "MEAN_SPREAD_POINTS":avg(spreads),
            "MAX_SPREAD_POINTS":max(spreads)
        }

    return {
        "ALIGNED_TIME":mt[i],
        "PRE30":window(i-6,i),
        "POST30":window(i,i+6),
        "POST120":window(i,i+24)
    }

def ratio(a,b):
    if a is None or b is None or b==0:return None
    return a/b

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--calendar",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    events=load_calendar(a.calendar)
    if len(events)<1000: raise SystemExit("too few high-impact events")
    event_index=build_event_index(events)
    pair_events=defaultdict(list)
    for ts,cur,name in events:
        for p in PAIRS:
            if cur==p[:3] or cur==p[3:]:
                pair_events[p].append((ts,cur,name))

    detail=[]
    pair_summary=[]
    skipped_no_align=0;skipped_controls=0

    for pi,pair in enumerate(PAIRS,1):
        path=a.root/pair/(pair+"_M5.bin")
        if not path.exists(): raise SystemExit("missing M5 "+str(path))
        hdr,mb=read_xfbar(path)
        if hdr["period_seconds"]!=300: raise SystemExit(pair+" not M5")
        mt=[int(x[0]) for x in mb]

        pe=sorted(set(pair_events[pair]))
        used=0
        for ts,cur,name in pe:
            em=metric_at(mb,mt,ts)
            if em is None:
                skipped_no_align+=1;continue

            controls=[]
            for wk in CONTROL_WEEK_OFFSETS:
                cts=ts+wk*7*86400
                if relevant_news_near(cts,pair,event_index):
                    continue
                cm=metric_at(mb,mt,cts)
                if cm is not None:
                    controls.append(cm)
            if len(controls)<2:
                skipped_controls+=1;continue

            used+=1
            for wn in ("PRE30","POST30","POST120"):
                e=em[wn]
                c={}
                for k in ("ABS_RETURN_BPS","SIGNED_RETURN_BPS","RANGE_BPS","MEAN_SPREAD_POINTS","MAX_SPREAD_POINTS"):
                    c[k]=avg([x[wn][k] for x in controls])
                detail.append({
                    "PAIR":pair,"EVENT_TIME_UTC":datetime.fromtimestamp(ts,tz=timezone.utc).isoformat(),
                    "ALIGNED_M5_UTC":datetime.fromtimestamp(em["ALIGNED_TIME"],tz=timezone.utc).isoformat(),
                    "CURRENCY":cur,"EVENT":name,"WINDOW":wn,"CONTROL_N":len(controls),
                    "EVENT_ABS_RETURN_BPS":e["ABS_RETURN_BPS"],
                    "CONTROL_ABS_RETURN_BPS":c["ABS_RETURN_BPS"],
                    "ABS_RETURN_RATIO":ratio(e["ABS_RETURN_BPS"],c["ABS_RETURN_BPS"]),
                    "EVENT_SIGNED_RETURN_BPS":e["SIGNED_RETURN_BPS"],
                    "CONTROL_SIGNED_RETURN_BPS":c["SIGNED_RETURN_BPS"],
                    "EVENT_RANGE_BPS":e["RANGE_BPS"],
                    "CONTROL_RANGE_BPS":c["RANGE_BPS"],
                    "RANGE_RATIO":ratio(e["RANGE_BPS"],c["RANGE_BPS"]),
                    "EVENT_MEAN_SPREAD_POINTS":e["MEAN_SPREAD_POINTS"],
                    "CONTROL_MEAN_SPREAD_POINTS":c["MEAN_SPREAD_POINTS"],
                    "MEAN_SPREAD_RATIO":ratio(e["MEAN_SPREAD_POINTS"],c["MEAN_SPREAD_POINTS"]),
                    "EVENT_MAX_SPREAD_POINTS":e["MAX_SPREAD_POINTS"],
                    "CONTROL_MAX_SPREAD_POINTS":c["MAX_SPREAD_POINTS"],
                    "MAX_SPREAD_RATIO":ratio(e["MAX_SPREAD_POINTS"],c["MAX_SPREAD_POINTS"])
                })
        pair_summary.append({"PAIR":pair,"CALENDAR_EVENTS":len(pe),"MATCHED_EVENTS":used,
                             "M5_BARS":len(mb),"FIRST_M5":hdr["first_time"],"LAST_M5":hdr["last_time"]})
        print(f"[{pi}/{len(PAIRS)}] {pair} calendar={len(pe)} matched={used} PASS")

    if not detail: raise SystemExit("no matched event observations")

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";")
            w.writeheader();w.writerows(data)

    write("NEWS01_EVENTS.csv",detail)
    write("NEWS01_PAIRS.csv",pair_summary)

    aggregate=[]
    by_currency=[]
    for wn in ("PRE30","POST30","POST120"):
        rr=[r for r in detail if r["WINDOW"]==wn]
        aggregate.append({
            "WINDOW":wn,"N":len(rr),
            "EVENT_ABS_RETURN_BPS":avg([r["EVENT_ABS_RETURN_BPS"] for r in rr]),
            "CONTROL_ABS_RETURN_BPS":avg([r["CONTROL_ABS_RETURN_BPS"] for r in rr]),
            "ABS_RETURN_RATIO":ratio(avg([r["EVENT_ABS_RETURN_BPS"] for r in rr]),avg([r["CONTROL_ABS_RETURN_BPS"] for r in rr])),
            "EVENT_RANGE_BPS":avg([r["EVENT_RANGE_BPS"] for r in rr]),
            "CONTROL_RANGE_BPS":avg([r["CONTROL_RANGE_BPS"] for r in rr]),
            "RANGE_RATIO":ratio(avg([r["EVENT_RANGE_BPS"] for r in rr]),avg([r["CONTROL_RANGE_BPS"] for r in rr])),
            "EVENT_MEAN_SPREAD_POINTS":avg([r["EVENT_MEAN_SPREAD_POINTS"] for r in rr]),
            "CONTROL_MEAN_SPREAD_POINTS":avg([r["CONTROL_MEAN_SPREAD_POINTS"] for r in rr]),
            "MEAN_SPREAD_RATIO":ratio(avg([r["EVENT_MEAN_SPREAD_POINTS"] for r in rr]),avg([r["CONTROL_MEAN_SPREAD_POINTS"] for r in rr])),
            "EVENT_MAX_SPREAD_POINTS":avg([r["EVENT_MAX_SPREAD_POINTS"] for r in rr]),
            "CONTROL_MAX_SPREAD_POINTS":avg([r["CONTROL_MAX_SPREAD_POINTS"] for r in rr]),
            "MAX_SPREAD_RATIO":ratio(avg([r["EVENT_MAX_SPREAD_POINTS"] for r in rr]),avg([r["CONTROL_MAX_SPREAD_POINTS"] for r in rr]))
        })
        for cur in sorted(CURS):
            cc=[r for r in rr if r["CURRENCY"]==cur]
            if not cc:continue
            by_currency.append({
                "CURRENCY":cur,"WINDOW":wn,"N":len(cc),
                "EVENT_ABS_RETURN_BPS":avg([r["EVENT_ABS_RETURN_BPS"] for r in cc]),
                "CONTROL_ABS_RETURN_BPS":avg([r["CONTROL_ABS_RETURN_BPS"] for r in cc]),
                "ABS_RETURN_RATIO":ratio(avg([r["EVENT_ABS_RETURN_BPS"] for r in cc]),avg([r["CONTROL_ABS_RETURN_BPS"] for r in cc])),
                "EVENT_RANGE_BPS":avg([r["EVENT_RANGE_BPS"] for r in cc]),
                "CONTROL_RANGE_BPS":avg([r["CONTROL_RANGE_BPS"] for r in cc]),
                "RANGE_RATIO":ratio(avg([r["EVENT_RANGE_BPS"] for r in cc]),avg([r["CONTROL_RANGE_BPS"] for r in cc])),
                "MEAN_SPREAD_RATIO":ratio(avg([r["EVENT_MEAN_SPREAD_POINTS"] for r in cc]),avg([r["CONTROL_MEAN_SPREAD_POINTS"] for r in cc]))
            })

    write("NEWS01_AGGREGATE.csv",aggregate)
    write("NEWS01_CURRENCY.csv",by_currency)

    meta={
      "block":"NEWS01","status":"PASS",
      "calendar_high_impact_events":len(events),
      "calendar_first_utc":datetime.fromtimestamp(events[0][0],tz=timezone.utc).isoformat(),
      "calendar_last_utc":datetime.fromtimestamp(events[-1][0],tz=timezone.utc).isoformat(),
      "matched_event_window_rows":len(detail),
      "skipped_no_m5_alignment":skipped_no_align,
      "skipped_insufficient_controls":skipped_controls,
      "contract":{
        "calendar_source":"Ehsanrs2/Forex_Factory_Calendar pinned historical dataset",
        "impact_filter":"High Impact Expected",
        "actual_forecast_previous_used":False,
        "windows_minutes":{"PRE30":[-30,0],"POST30":[0,30],"POST120":[0,120]},
        "control_offsets_weeks":list(CONTROL_WEEK_OFFSETS),
        "control_excludes_relevant_high_impact_within_minutes":EXCLUSION_MINUTES,
        "trading_or_pnl":False,
        "parameter_optimization":False
      },
      "aggregate":aggregate
    }
    (a.out/"NEWS01.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
      "NEWS01 — HIGH-IMPACT NEWS REGIME AUDIT",
      "STATUS: PASS",
      f"HIGH_IMPACT_EVENTS={len(events)}",
      f"MATCHED_EVENT_WINDOW_ROWS={len(detail)}",
      "ACTUAL/FORECAST/PREVIOUS USED: NO",
      "TRADING/PNL: NO",
      "OPTIMIZATION: NO",""
    ]
    for r in aggregate:
        lines.append(
          f"{r['WINDOW']}: N={r['N']} "
          f"ABS={r['EVENT_ABS_RETURN_BPS']:.4f}/{r['CONTROL_ABS_RETURN_BPS']:.4f}bps x{r['ABS_RETURN_RATIO']:.3f} "
          f"RANGE={r['EVENT_RANGE_BPS']:.4f}/{r['CONTROL_RANGE_BPS']:.4f}bps x{r['RANGE_RATIO']:.3f} "
          f"MEAN_SPREAD=x{r['MEAN_SPREAD_RATIO']:.3f} MAX_SPREAD=x{r['MAX_SPREAD_RATIO']:.3f}"
        )
    (a.out/"NEWS01.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
