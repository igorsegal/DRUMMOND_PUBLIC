#!/usr/bin/env python3
"""
NEWS02 — HIGH-IMPACT EVENT TYPE ATLAS.

Builds on NEWS01. Uses only scheduled high-impact event metadata:
timestamp, affected currency, and event name. Actual / Forecast / Previous
are not used.

Frozen event taxonomy is based on event-name semantics, not observed returns.
For every pair-event we reuse the NEWS01 matched-control design and report
paired event-minus-control effects by:
  1) event category
  2) event category x currency
  3) exact event name

No trading, no PnL, no threshold optimization.
"""
import argparse,bisect,csv,json,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from drummond_replay01 import read_xfbar
from NEWS01 import (
    CURS,PAIRS,CONTROL_WEEK_OFFSETS,EXCLUSION_MINUTES,
    load_calendar,build_event_index,relevant_news_near,metric_at,avg,ratio
)

# Taxonomy precedence is frozen before reading any market outcomes.
def classify(name):
    n=name.lower()

    # Scheduled policy decisions / formal policy announcements.
    if any(k in n for k in [
        "federal funds rate","official bank rate","official cash rate",
        "overnight rate","overnight call rate","cash rate","main refinancing rate",
        "policy rate","rate statement","fomc statement",
        "monetary policy statement","monetary policy summary",
        "asset purchase facility","official bank rate votes",
        "asset purchase facility votes"
    ]):
        return "CB_POLICY_DECISION"

    # Central-bank communication separate from the formal decision.
    if any(k in n for k in [
        "press conference","meeting minutes","monetary policy meeting accounts",
        "economic projections","monetary policy report","outlook report",
        "financial stability","gov ","chair ","chairman ","fomc member ",
        "monetary policy report hearings"
    ]):
        return "CB_COMMUNICATION"

    if any(k in n for k in [
        "cpi","ppi","pce price","inflation expectation","inflation expectations",
        "trimmed mean","trimmed cpi","median cpi"
    ]):
        return "INFLATION"

    if any(k in n for k in [
        "non-farm employment","adp non-farm","employment change",
        "unemployment","claimant count","average hourly earnings",
        "average earnings","jolts","employment cost","unit labor costs",
        "wage price index"
    ]):
        return "LABOR"

    if any(k in n for k in [
        "gdp","industrial production","manufacturing production",
        "construction work done","private capital expenditure"
    ]):
        return "GROWTH_OUTPUT"

    if any(k in n for k in [
        "pmi","ism manufacturing","ism services",
        "philly fed manufacturing","empire state manufacturing","chicago pmi"
    ]):
        return "PMI_ACTIVITY"

    if any(k in n for k in [
        "retail sales","consumer confidence","consumer sentiment",
        "personal spending","durable goods orders"
    ]):
        return "CONSUMPTION_DEMAND"

    if any(k in n for k in [
        "business confidence","business outlook","zew economic sentiment",
        "ifo business climate"
    ]):
        return "BUSINESS_CONFIDENCE"

    if any(k in n for k in [
        "building permits","building approvals","housing starts",
        "existing home sales","new home sales","pending home sales","hpi"
    ]):
        return "HOUSING"

    if any(k in n for k in [
        "trade balance","goods trade balance","current account"
    ]):
        return "TRADE_EXTERNAL"

    if "crude oil inventories" in n:
        return "ENERGY_INVENTORY"

    if any(k in n for k in [
        "election","elections","brexit vote","confidence vote",
        "budget release","forecast statement","economic summit",
        "euro summit","eurogroup meetings","ecofin meetings",
        "constitutional court ruling","president trump speaks",
        "president biden speaks","prime minister may speaks",
        "prime minister johnson speaks","fed chairman nomination vote"
    ]):
        return "POLITICAL_FISCAL"

    if any(k in n for k in [
        "bond auction","bank stress test","treasury currency report",
        "treasury sec "
    ]):
        return "FINANCIAL_OTHER"

    return "OTHER"

def paired_stats(rr):
    if not rr:
        return {}
    def calc(ev,ctl):
        e=[r[ev] for r in rr]
        c=[r[ctl] for r in rr]
        d=[x-y for x,y in zip(e,c)]
        return {
            "EVENT_MEAN":avg(e),
            "CONTROL_MEAN":avg(c),
            "RATIO":ratio(avg(e),avg(c)),
            "MEAN_DELTA":avg(d),
            "MEDIAN_DELTA":statistics.median(d),
            "EVENT_GT_CONTROL_RATE":sum(x>0 for x in d)/len(d)
        }
    return {
        "N":len(rr),
        "ABS":calc("EVENT_ABS_RETURN_BPS","CONTROL_ABS_RETURN_BPS"),
        "RANGE":calc("EVENT_RANGE_BPS","CONTROL_RANGE_BPS"),
        "MEAN_SPREAD":calc("EVENT_MEAN_SPREAD_POINTS","CONTROL_MEAN_SPREAD_POINTS"),
        "MAX_SPREAD":calc("EVENT_MAX_SPREAD_POINTS","CONTROL_MAX_SPREAD_POINTS")
    }

def flatten(prefix,st):
    o={"N":st["N"]}
    for k in ("ABS","RANGE","MEAN_SPREAD","MAX_SPREAD"):
        for m,v in st[k].items():
            o[f"{prefix}_{k}_{m}"]=v
    return o

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--calendar",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    events=load_calendar(a.calendar)
    event_index=build_event_index(events)
    pair_events=defaultdict(list)
    for ts,cur,name in events:
        cat=classify(name)
        for p in PAIRS:
            if cur==p[:3] or cur==p[3:]:
                pair_events[p].append((ts,cur,name,cat))

    detail=[]
    for pi,pair in enumerate(PAIRS,1):
        path=a.root/pair/(pair+"_M5.bin")
        hdr,mb=read_xfbar(path)
        if hdr["period_seconds"]!=300: raise SystemExit(pair+" not M5")
        mt=[int(x[0]) for x in mb]
        matched=0

        for ts,cur,name,cat in sorted(set(pair_events[pair])):
            em=metric_at(mb,mt,ts)
            if em is None: continue
            controls=[]
            for wk in CONTROL_WEEK_OFFSETS:
                cts=ts+wk*7*86400
                if relevant_news_near(cts,pair,event_index):
                    continue
                cm=metric_at(mb,mt,cts)
                if cm is not None: controls.append(cm)
            if len(controls)<2: continue
            matched+=1

            for wn in ("PRE30","POST30","POST120"):
                e=em[wn]
                c={k:avg([x[wn][k] for x in controls]) for k in (
                    "ABS_RETURN_BPS","SIGNED_RETURN_BPS","RANGE_BPS",
                    "MEAN_SPREAD_POINTS","MAX_SPREAD_POINTS")}
                detail.append({
                    "PAIR":pair,
                    "EVENT_TIME_UTC":datetime.fromtimestamp(ts,tz=timezone.utc).isoformat(),
                    "CURRENCY":cur,"EVENT":name,"CATEGORY":cat,"WINDOW":wn,
                    "CONTROL_N":len(controls),
                    "EVENT_ABS_RETURN_BPS":e["ABS_RETURN_BPS"],
                    "CONTROL_ABS_RETURN_BPS":c["ABS_RETURN_BPS"],
                    "EVENT_RANGE_BPS":e["RANGE_BPS"],
                    "CONTROL_RANGE_BPS":c["RANGE_BPS"],
                    "EVENT_MEAN_SPREAD_POINTS":e["MEAN_SPREAD_POINTS"],
                    "CONTROL_MEAN_SPREAD_POINTS":c["MEAN_SPREAD_POINTS"],
                    "EVENT_MAX_SPREAD_POINTS":e["MAX_SPREAD_POINTS"],
                    "CONTROL_MAX_SPREAD_POINTS":c["MAX_SPREAD_POINTS"]
                })
        print(f"[{pi}/{len(PAIRS)}] {pair} matched={matched} PASS")

    if not detail: raise SystemExit("no matched observations")

    def build_group(group_cols):
        out=[]
        keys=sorted(set(tuple(r[c] for c in group_cols) for r in detail))
        for key in keys:
            base={c:v for c,v in zip(group_cols,key)}
            for wn in ("PRE30","POST30","POST120"):
                rr=[r for r in detail if r["WINDOW"]==wn and all(r[c]==base[c] for c in group_cols)]
                if not rr: continue
                row=dict(base);row["WINDOW"]=wn
                row.update(flatten("",paired_stats(rr)))
                # Remove leading underscore from generated field names.
                row={k[1:] if k.startswith("_") else k:v for k,v in row.items()}
                out.append(row)
        return out

    cat=build_group(["CATEGORY"])
    curcat=build_group(["CURRENCY","CATEGORY"])
    exact=build_group(["CURRENCY","EVENT"])

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";")
            w.writeheader();w.writerows(data)

    write("NEWS02_DETAIL.csv",detail)
    write("NEWS02_CATEGORY.csv",cat)
    write("NEWS02_CURRENCY_CATEGORY.csv",curcat)
    write("NEWS02_EVENT_NAME.csv",exact)

    # Headline table uses POST120 only and N>=100 pair-event observations.
    headline=sorted(
        [r for r in cat if r["WINDOW"]=="POST120" and r["N"]>=100],
        key=lambda r:r["ABS_RATIO"],reverse=True
    )
    cur_head=sorted(
        [r for r in curcat if r["WINDOW"]=="POST120" and r["N"]>=100],
        key=lambda r:r["ABS_RATIO"],reverse=True
    )

    taxonomy_counts=defaultdict(int)
    for ts,cur,name in events:
        taxonomy_counts[classify(name)]+=1

    meta={
        "block":"NEWS02","status":"PASS",
        "calendar_high_impact_events":len(events),
        "matched_rows":len(detail),
        "taxonomy_counts":dict(sorted(taxonomy_counts.items())),
        "headline_post120_categories_n_ge_100":headline,
        "headline_post120_currency_categories_n_ge_100":cur_head[:30],
        "contract":{
            "taxonomy_frozen_before_market_outcomes":True,
            "actual_forecast_previous_used":False,
            "matched_control_design":"NEWS01 same weekday/time +/-1..4 weeks excluding relevant high-impact +/-120m",
            "reporting_min_n_for_headline":100,
            "trading_or_pnl":False,
            "parameter_optimization":False
        }
    }
    (a.out/"NEWS02.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
        "NEWS02 — HIGH-IMPACT EVENT TYPE ATLAS",
        "STATUS: PASS",
        f"HIGH_IMPACT_EVENTS={len(events)}",
        f"MATCHED_ROWS={len(detail)}",
        "ACTUAL/FORECAST/PREVIOUS USED: NO",
        "TAXONOMY FROZEN BEFORE MARKET OUTCOMES: YES",
        "TRADING/PNL: NO",
        "OPTIMIZATION: NO","",
        "POST120 CATEGORY ATLAS (N>=100):"
    ]
    for r in headline:
        lines.append(
            f" {r['CATEGORY']}: N={r['N']} "
            f"ABS={r['ABS_EVENT_MEAN']:.4f}/{r['ABS_CONTROL_MEAN']:.4f} x{r['ABS_RATIO']:.3f} "
            f"dABS={r['ABS_MEAN_DELTA']:+.4f} "
            f"RANGE=x{r['RANGE_RATIO']:.3f} "
            f"P(EVENT>CTRL)={r['ABS_EVENT_GT_CONTROL_RATE']:.3f}"
        )
    lines.append("")
    lines.append("POST120 TOP CURRENCY x CATEGORY CELLS (N>=100):")
    for r in cur_head[:20]:
        lines.append(
            f" {r['CURRENCY']} {r['CATEGORY']}: N={r['N']} "
            f"ABS=x{r['ABS_RATIO']:.3f} dABS={r['ABS_MEAN_DELTA']:+.4f} "
            f"RANGE=x{r['RANGE_RATIO']:.3f}"
        )
    (a.out/"NEWS02.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
