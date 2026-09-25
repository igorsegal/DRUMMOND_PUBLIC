#!/usr/bin/env python3
"""
NEWS03 — NEWS x CROSS-MARKET DISLOCATION AUDIT.

Question:
After a scheduled High-Impact event, when the target FX pair's first 30-minute
move materially disagrees with the volatility-normalized move implied by the
OTHER FX crosses, does the target subsequently catch up strongly enough to
survive recorded spread?

Causal construction:
- high-impact calendar timestamp/currency only; no Actual/Forecast/Previous;
- decision is made 30 minutes after the event;
- target pair is excluded from external currency-strength calculation;
- each external pair's 30m return is normalized by its own PRIOR 24h M5
  volatility (288 completed 5m returns);
- external gap = mean(base-vs-6-third-currencies z) -
                 mean(quote-vs-same-6-third-currencies z);
- target z uses its own prior volatility;
- DISLOCATION = external_gap - target_z;
- fixed absolute bins: <1, 1-2, 2-3, >=3;
- future catch-up measured from event+30m to event+60m and event+120m;
- recorded M5 spread is applied; extra round-trip stress 0/1/2/5 points.

Important:
NEWS02 informed the event taxonomy/focus classes on this SAME historical
sample. Therefore NEWS03 is an exploratory interaction/economic audit, NOT a
fresh untouched out-of-sample validation and NOT a portfolio PnL test.
"""
import argparse,bisect,csv,json,math,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from drummond_replay01 import read_xfbar
from NEWS01 import CURS,PAIRS,load_calendar,avg
from NEWS02 import classify

VOL_BARS=288          # prior 24h of M5 returns
MEASURE_MIN=30
HORIZONS_MIN=(30,90)  # after the +30m decision -> event+60 / event+120
EXTRA_COST_POINTS=(0,1,2,5)
FOCUS_CATEGORIES={"CB_POLICY_DECISION","CB_COMMUNICATION","GROWTH_OUTPUT"}
SPLIT=int(datetime(2022,1,1,tzinfo=timezone.utc).timestamp())

PAIR_SET=set(PAIRS)

def sgn(x): return 1 if x>0 else (-1 if x<0 else 0)
def med(x): return statistics.median(x) if x else None

def find_pair(a,b):
    p=a+b
    if p in PAIR_SET:return p,1
    p=b+a
    if p in PAIR_SET:return p,-1
    raise KeyError(a+b)

def disloc_bin(x):
    a=abs(x)
    if a<1:return "LT1"
    if a<2:return "1_TO_2"
    if a<3:return "2_TO_3"
    return "GE3"

def pf(vals):
    w=sum(x for x in vals if x>0)
    l=-sum(x for x in vals if x<0)
    return w/l if l>0 else None

def stdev_from_prefix(ps,ps2,lo,hi):
    # [lo,hi), sample standard deviation
    n=hi-lo
    if n<2:return None
    sm=ps[hi]-ps[lo];ss=ps2[hi]-ps2[lo]
    var=max(0.0,(ss-sm*sm/n)/(n-1))
    return math.sqrt(var)

def aligned_index(mt,ts,max_lag=300):
    i=bisect.bisect_left(mt,ts)
    if i>=len(mt) or mt[i]-ts>max_lag:return None
    return i

def exactish_index(mt,ts,max_lag=300):
    i=bisect.bisect_left(mt,ts)
    if i>=len(mt) or mt[i]-ts>max_lag:return None
    return i

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

def pair_features(root,pair,clusters):
    path=root/pair/(pair+"_M5.bin")
    if not path.exists(): raise SystemExit("missing M5 "+str(path))
    hdr,mb=read_xfbar(path)
    if hdr["period_seconds"]!=300:raise SystemExit(pair+" not M5")
    mt=[int(x[0]) for x in mb]
    op=[float(x[1]) for x in mb]
    sp=[max(0,int(x[6])) for x in mb]

    # one-step open-to-open log returns and prefixes
    one=[0.0]*len(mb)
    for i in range(1,len(mb)):
        if op[i-1]>0 and op[i]>0:
            one[i]=math.log(op[i]/op[i-1])
    ps=[0.0]*(len(mb)+1);ps2=[0.0]*(len(mb)+1)
    for i,x in enumerate(one):
        ps[i+1]=ps[i]+x;ps2[i+1]=ps2[i]+x*x

    out=[None]*len(clusters)
    for ei,e in enumerate(clusters):
        i0=aligned_index(mt,e["ts"])
        if i0 is None or i0<=VOL_BARS:continue
        t0=mt[i0]
        i30=exactish_index(mt,t0+30*60)
        i60=exactish_index(mt,t0+60*60)
        i120=exactish_index(mt,t0+120*60)
        if None in (i30,i60,i120):continue
        if not (op[i0]>0 and op[i30]>0 and op[i60]>0 and op[i120]>0):continue

        # strictly prior to event-aligned open: one[i0-VOL_BARS : i0]
        sd=stdev_from_prefix(ps,ps2,i0-VOL_BARS,i0)
        if sd is None or sd<=0:continue
        r30=math.log(op[i30]/op[i0])
        z30=r30/(sd*math.sqrt(6.0))

        out[ei]={
            "align":t0,"z30":z30,"point":float(hdr["point"]),
            "entry_time":mt[i30],"entry_bid":op[i30],"entry_spread":sp[i30],
            "exit30_time":mt[i60],"exit30_bid":op[i60],"exit30_spread":sp[i60],
            "exit90_time":mt[i120],"exit90_bid":op[i120],"exit90_spread":sp[i120]
        }
    return out

def side_returns(f,side,horizon):
    eb=f["entry_bid"];point=f["point"]
    xb=f["exit30_bid"] if horizon==30 else f["exit90_bid"]
    xs=f["exit30_spread"] if horizon==30 else f["exit90_spread"]
    if side>0:
        gross=math.log(xb/eb)*10000.0
        net0=math.log(xb/(eb+f["entry_spread"]*point))*10000.0
    else:
        gross=math.log(eb/xb)*10000.0
        net0=math.log(eb/(xb+xs*point))*10000.0
    out={"GROSS_BPS":gross,"NET_C0_BPS":net0}
    for cp in EXTRA_COST_POINTS:
        if cp==0:continue
        extra=cp*point/eb*10000.0
        out["NET_C"+str(cp)+"_BPS"]=net0-extra
    return out

def summarize(rr,key):
    vals=[r[key] for r in rr]
    return {
        "N":len(vals),
        "MEAN_BPS":avg(vals),
        "MEDIAN_BPS":med(vals),
        "WIN_RATE":sum(x>0 for x in vals)/len(vals) if vals else None,
        "PF":pf(vals)
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--calendar",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    events=load_calendar(a.calendar)
    clusters=build_clusters(events)
    print("HIGH_IMPACT_EVENTS",len(events),"CLUSTERS",len(clusters))

    feat={}
    for i,p in enumerate(PAIRS,1):
        feat[p]=pair_features(a.root,p,clusters)
        ok=sum(x is not None for x in feat[p])
        print(f"[{i}/{len(PAIRS)}] {p} event_features={ok} PASS")

    rows=[]
    synchronous_reject=0
    for ei,e in enumerate(clusters):
        cur=e["currency"]
        for target in PAIRS:
            if cur not in (target[:3],target[3:]):continue
            tf=feat[target][ei]
            if tf is None:continue
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
            if not ok:continue
            if len(set(aligns))!=1:
                synchronous_reject+=1;continue

            external=avg(bz)-avg(qz)
            target_z=tf["z30"]
            d=external-target_z
            side=sgn(d)
            if side==0:continue
            bn=disloc_bin(d)
            period="2022+" if e["ts"]>=SPLIT else "PRE2022"

            base_row={
                "EVENT_TIME_UTC":datetime.fromtimestamp(e["ts"],tz=timezone.utc).isoformat(),
                "ALIGNED_M5_UTC":datetime.fromtimestamp(tf["align"],tz=timezone.utc).isoformat(),
                "NEWS_CURRENCY":cur,"EVENTS":e["names"],
                "CATEGORIES":e["category_label"],"FOCUS_NEWS":int(e["focus"]),
                "TARGET":target,"PERIOD":period,
                "TARGET_Z30":target_z,"EXTERNAL_GAP_Z30":external,
                "DISLOCATION_Z":d,"ABS_DISLOCATION_Z":abs(d),"DISLOCATION_BIN":bn,
                "SIDE":"LONG" if side>0 else "SHORT",
                "ENTRY_SPREAD_POINTS":tf["entry_spread"]
            }
            for h in HORIZONS_MIN:
                r=side_returns(tf,side,h)
                row=dict(base_row);row["HORIZON_MIN"]=h
                row.update(r);rows.append(row)

    if not rows:raise SystemExit("no NEWS03 rows")

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";")
            w.writeheader();w.writerows(data)

    write("NEWS03_EVENTS.csv",rows)

    atlas=[]
    scopes=[
        ("ALL_NEWS",lambda r:True),
        ("FOCUS_NEWS",lambda r:r["FOCUS_NEWS"]==1)
    ]
    for scope,pred in scopes:
      for period in ("ALL","PRE2022","2022+"):
       for h in HORIZONS_MIN:
        for bn in ("LT1","1_TO_2","2_TO_3","GE3"):
            rr=[r for r in rows if pred(r) and r["HORIZON_MIN"]==h and r["DISLOCATION_BIN"]==bn
                and (period=="ALL" or r["PERIOD"]==period)]
            if not rr:continue
            row={"SCOPE":scope,"PERIOD":period,"HORIZON_MIN":h,"BIN":bn,
                 "MEAN_ABS_DISLOCATION_Z":avg([r["ABS_DISLOCATION_Z"] for r in rr]),
                 "MEAN_ENTRY_SPREAD_POINTS":avg([r["ENTRY_SPREAD_POINTS"] for r in rr])}
            for key in ("GROSS_BPS","NET_C0_BPS","NET_C1_BPS","NET_C2_BPS","NET_C5_BPS"):
                s=summarize(rr,key)
                for k,v in s.items():row[key+"_"+k]=v
            atlas.append(row)
    write("NEWS03_ATLAS.csv",atlas)

    cat=[]
    for period in ("ALL","PRE2022","2022+"):
      for h in HORIZONS_MIN:
       for category in sorted(set(x for e in clusters for x in e["categories"])):
        rr=[r for r in rows if r["HORIZON_MIN"]==h and category in r["CATEGORIES"].split("+")
            and r["DISLOCATION_BIN"] in ("2_TO_3","GE3")
            and (period=="ALL" or r["PERIOD"]==period)]
        if not rr:continue
        s=summarize(rr,"NET_C0_BPS")
        cat.append({"PERIOD":period,"HORIZON_MIN":h,"CATEGORY":category,
                    "N_GE2":s["N"],"NET_C0_MEAN_BPS":s["MEAN_BPS"],
                    "NET_C0_MEDIAN_BPS":s["MEDIAN_BPS"],"NET_C0_WIN_RATE":s["WIN_RATE"],
                    "NET_C0_PF":s["PF"],
                    "GROSS_MEAN_BPS":avg([r["GROSS_BPS"] for r in rr])})
    write("NEWS03_CATEGORY_GE2.csv",cat)

    meta={
        "block":"NEWS03","status":"PASS",
        "high_impact_events":len(events),"event_clusters":len(clusters),
        "event_target_horizon_rows":len(rows),
        "synchronous_reject":synchronous_reject,
        "focus_categories":sorted(FOCUS_CATEGORIES),
        "contract":{
            "actual_forecast_previous_used":False,
            "decision_delay_minutes":MEASURE_MIN,
            "external_target_pair_excluded":True,
            "external_currency_strength_third_currencies":6,
            "normalization":"30m log return / prior 24h M5 realized sd / sqrt(6)",
            "dislocation_bins_abs_z":["<1","1-2","2-3",">=3"],
            "future_horizons_after_decision_minutes":list(HORIZONS_MIN),
            "recorded_m5_spread_applied":True,
            "extra_round_trip_cost_points":list(EXTRA_COST_POINTS),
            "parameter_optimization":False,
            "fresh_out_of_sample_validation":False,
            "portfolio_pnl":False,
            "overlap_blocking":False,
            "reason_not_fresh":"NEWS02 taxonomy/focus classes were inspected on the same history"
        }
    }
    (a.out/"NEWS03.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
        "NEWS03 — NEWS x CROSS-MARKET DISLOCATION AUDIT",
        "STATUS: PASS",
        f"HIGH_IMPACT_EVENTS={len(events)} CLUSTERS={len(clusters)}",
        f"ROWS={len(rows)}",
        "DECISION: +30m after scheduled event",
        "TARGET EXCLUDED FROM EXTERNAL STRENGTH: YES",
        "ACTUAL/FORECAST/PREVIOUS USED: NO",
        "FRESH OUT-OF-SAMPLE: NO",
        "PORTFOLIO PNL: NO","",
    ]
    for scope in ("ALL_NEWS","FOCUS_NEWS"):
        lines.append(scope+" — ALL HISTORY:")
        for h in HORIZONS_MIN:
            lines.append(f" HORIZON +{h}m after decision:")
            for bn in ("LT1","1_TO_2","2_TO_3","GE3"):
                rr=next((x for x in atlas if x["SCOPE"]==scope and x["PERIOD"]=="ALL" and x["HORIZON_MIN"]==h and x["BIN"]==bn),None)
                if rr is None:continue
                lines.append(
                    f"  {bn}: N={rr['NET_C0_BPS_N']} |D|={rr['MEAN_ABS_DISLOCATION_Z']:.3f} "
                    f"GROSS={rr['GROSS_BPS_MEAN_BPS']:+.4f}bps "
                    f"NET0={rr['NET_C0_BPS_MEAN_BPS']:+.4f} PF={rr['NET_C0_BPS_PF']:.4f} "
                    f"NET2={rr['NET_C2_BPS_MEAN_BPS']:+.4f}"
                )
        lines.append("")

    lines.append("CATEGORY GE2 — ALL HISTORY, +90m after decision:")
    cr=sorted([r for r in cat if r["PERIOD"]=="ALL" and r["HORIZON_MIN"]==90 and r["N_GE2"]>=100],
              key=lambda r:r["NET_C0_MEAN_BPS"],reverse=True)
    for r in cr:
        lines.append(
            f" {r['CATEGORY']}: N={r['N_GE2']} GROSS={r['GROSS_MEAN_BPS']:+.4f} "
            f"NET0={r['NET_C0_MEAN_BPS']:+.4f} PF={r['NET_C0_PF']:.4f} WIN={r['NET_C0_WIN_RATE']:.4f}"
        )
    (a.out/"NEWS03.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
