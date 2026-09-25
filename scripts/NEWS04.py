#!/usr/bin/env python3
"""
NEWS04 — STRICT PRICE-ONLY CONTROL FOR NEWS03.

Purpose:
Test whether the apparently strong >=2-sigma NEWS03 result is genuinely
cross-market information or mostly ordinary reversal of an extreme first
30-minute target-pair move.

Uses the EXACT SAME NEWS03 event-target timestamps and horizons.

Signals:
- CROSS: NEWS03 side = sign(EXTERNAL_GAP_Z30 - TARGET_Z30)
- PRICE_MR: price-only mean reversion = -sign(TARGET_Z30)
- EXTERNAL_ONLY: sign(EXTERNAL_GAP_Z30)

Because NEWS03_GROSS_BPS = CROSS_SIDE * RAW_FUTURE_LOG_RETURN,
the unsigned future return is recovered exactly and each alternative signal is
evaluated on the same timestamps without rereading market data.

No parameter fitting. No new thresholds. No portfolio PnL.
This is a falsification/control block, not fresh out-of-sample validation.
"""
import argparse,csv,json,math,statistics
from pathlib import Path

BINS=("LT1","1_TO_2","2_TO_3","GE3")

def avg(x): return statistics.fmean(x) if x else None
def med(x): return statistics.median(x) if x else None
def sgn(x): return 1 if x>0 else (-1 if x<0 else 0)
def pf(vals):
    w=sum(x for x in vals if x>0)
    l=-sum(x for x in vals if x<0)
    return w/l if l>0 else None

def metric(vals):
    return {
        "N":len(vals),
        "MEAN_BPS":avg(vals),
        "MEDIAN_BPS":med(vals),
        "WIN_RATE":sum(x>0 for x in vals)/len(vals) if vals else None,
        "PF":pf(vals)
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--events",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    rows=[]
    with a.events.open("r",encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f,delimiter=";"):
            cross_side=1 if r["SIDE"]=="LONG" else -1
            target_z=float(r["TARGET_Z30"])
            ext_z=float(r["EXTERNAL_GAP_Z30"])
            cross_gross=float(r["GROSS_BPS"])
            raw_future=cross_side*cross_gross
            price_side=-sgn(target_z)
            ext_side=sgn(ext_z)
            price_gross=price_side*raw_future if price_side else 0.0
            ext_gross=ext_side*raw_future if ext_side else 0.0
            rows.append({
                "EVENT_TIME_UTC":r["EVENT_TIME_UTC"],
                "NEWS_CURRENCY":r["NEWS_CURRENCY"],
                "CATEGORIES":r["CATEGORIES"],
                "FOCUS_NEWS":int(r["FOCUS_NEWS"]),
                "TARGET":r["TARGET"],
                "PERIOD":r["PERIOD"],
                "HORIZON_MIN":int(r["HORIZON_MIN"]),
                "DISLOCATION_BIN":r["DISLOCATION_BIN"],
                "ABS_DISLOCATION_Z":float(r["ABS_DISLOCATION_Z"]),
                "TARGET_Z30":target_z,
                "EXTERNAL_GAP_Z30":ext_z,
                "CROSS_SIDE":cross_side,
                "PRICE_MR_SIDE":price_side,
                "EXTERNAL_ONLY_SIDE":ext_side,
                "CROSS_EQ_PRICE_MR":int(cross_side==price_side),
                "RAW_FUTURE_BPS":raw_future,
                "CROSS_GROSS_BPS":cross_gross,
                "PRICE_MR_GROSS_BPS":price_gross,
                "EXTERNAL_ONLY_GROSS_BPS":ext_gross,
                "CROSS_MINUS_PRICE_BPS":cross_gross-price_gross,
                "CROSS_MINUS_EXTERNAL_BPS":cross_gross-ext_gross
            })

    if not rows:raise SystemExit("no rows")

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";")
            w.writeheader();w.writerows(data)

    write("NEWS04_EVENTS.csv",rows)

    atlas=[]
    scopes=[
        ("ALL_NEWS",lambda r:True),
        ("FOCUS_NEWS",lambda r:r["FOCUS_NEWS"]==1)
    ]
    for scope,pred in scopes:
      for period in ("ALL","PRE2022","2022+"):
       for h in (30,90):
        for bn in BINS:
            rr=[r for r in rows if pred(r) and r["HORIZON_MIN"]==h and r["DISLOCATION_BIN"]==bn
                and (period=="ALL" or r["PERIOD"]==period)]
            if not rr:continue
            cm=metric([r["CROSS_GROSS_BPS"] for r in rr])
            pm=metric([r["PRICE_MR_GROSS_BPS"] for r in rr])
            em=metric([r["EXTERNAL_ONLY_GROSS_BPS"] for r in rr])
            atlas.append({
                "SCOPE":scope,"PERIOD":period,"HORIZON_MIN":h,"BIN":bn,
                "N":len(rr),
                "CROSS_EQ_PRICE_MR_RATE":avg([r["CROSS_EQ_PRICE_MR"] for r in rr]),
                "CROSS_MEAN_BPS":cm["MEAN_BPS"],"CROSS_MEDIAN_BPS":cm["MEDIAN_BPS"],
                "CROSS_WIN_RATE":cm["WIN_RATE"],"CROSS_PF":cm["PF"],
                "PRICE_MR_MEAN_BPS":pm["MEAN_BPS"],"PRICE_MR_MEDIAN_BPS":pm["MEDIAN_BPS"],
                "PRICE_MR_WIN_RATE":pm["WIN_RATE"],"PRICE_MR_PF":pm["PF"],
                "EXTERNAL_ONLY_MEAN_BPS":em["MEAN_BPS"],
                "EXTERNAL_ONLY_WIN_RATE":em["WIN_RATE"],"EXTERNAL_ONLY_PF":em["PF"],
                "CROSS_MINUS_PRICE_MEAN_BPS":avg([r["CROSS_MINUS_PRICE_BPS"] for r in rr]),
                "CROSS_GT_PRICE_RATE":sum(r["CROSS_GROSS_BPS"]>r["PRICE_MR_GROSS_BPS"] for r in rr)/len(rr)
            })
    write("NEWS04_ATLAS.csv",atlas)

    # Critical >=2 pooled audit and disagreement-with-price subset.
    critical=[]
    for scope,pred in scopes:
      for period in ("ALL","PRE2022","2022+"):
       for h in (30,90):
        rr=[r for r in rows if pred(r) and r["HORIZON_MIN"]==h
            and r["DISLOCATION_BIN"] in ("2_TO_3","GE3")
            and (period=="ALL" or r["PERIOD"]==period)]
        if not rr:continue
        for subset,qq in [
            ("ALL_GE2",rr),
            ("CROSS_EQ_PRICE_MR",[r for r in rr if r["CROSS_EQ_PRICE_MR"]==1]),
            ("CROSS_NE_PRICE_MR",[r for r in rr if r["CROSS_EQ_PRICE_MR"]==0])
        ]:
            if not qq:continue
            critical.append({
                "SCOPE":scope,"PERIOD":period,"HORIZON_MIN":h,"SUBSET":subset,
                "N":len(qq),
                "UNIQUE_EVENT_CLUSTERS":len(set((r["EVENT_TIME_UTC"],r["NEWS_CURRENCY"]) for r in qq)),
                "CROSS_MEAN_BPS":avg([r["CROSS_GROSS_BPS"] for r in qq]),
                "PRICE_MR_MEAN_BPS":avg([r["PRICE_MR_GROSS_BPS"] for r in qq]),
                "EXTERNAL_ONLY_MEAN_BPS":avg([r["EXTERNAL_ONLY_GROSS_BPS"] for r in qq]),
                "CROSS_MINUS_PRICE_MEAN_BPS":avg([r["CROSS_MINUS_PRICE_BPS"] for r in qq]),
                "CROSS_WIN_RATE":sum(r["CROSS_GROSS_BPS"]>0 for r in qq)/len(qq),
                "PRICE_MR_WIN_RATE":sum(r["PRICE_MR_GROSS_BPS"]>0 for r in qq)/len(qq),
                "CROSS_PF":pf([r["CROSS_GROSS_BPS"] for r in qq]),
                "PRICE_MR_PF":pf([r["PRICE_MR_GROSS_BPS"] for r in qq])
            })
    write("NEWS04_CRITICAL_GE2.csv",critical)

    meta={
        "block":"NEWS04","status":"PASS",
        "rows":len(rows),
        "contract":{
            "same_timestamps_as_news03":True,
            "same_horizons_as_news03":True,
            "same_dislocation_bins_as_news03":True,
            "price_only_control":"opposite sign of target first-30m normalized return",
            "external_only_control":"sign of external gap",
            "raw_future_recovered_exactly_from_news03_cross_side_and_gross":True,
            "parameter_optimization":False,
            "portfolio_pnl":False,
            "fresh_out_of_sample_validation":False
        }
    }
    (a.out/"NEWS04.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
        "NEWS04 — STRICT PRICE-ONLY CONTROL FOR NEWS03",
        "STATUS: PASS",
        f"ROWS={len(rows)}",
        "CONTROL: price-only mean reversion on EXACT SAME timestamps",
        "NEW THRESHOLDS: NO",
        "PORTFOLIO PNL: NO",
        "FRESH OUT-OF-SAMPLE: NO",""
    ]
    for scope in ("ALL_NEWS","FOCUS_NEWS"):
        lines.append(scope+" — GE2 POOLED:")
        for period in ("ALL","2022+"):
            for h in (30,90):
                r=next((x for x in critical if x["SCOPE"]==scope and x["PERIOD"]==period
                        and x["HORIZON_MIN"]==h and x["SUBSET"]=="ALL_GE2"),None)
                if r:
                    lines.append(
                        f" {period} H+{h}m: N={r['N']} CLUSTERS={r['UNIQUE_EVENT_CLUSTERS']} "
                        f"CROSS={r['CROSS_MEAN_BPS']:+.4f} PRICE_MR={r['PRICE_MR_MEAN_BPS']:+.4f} "
                        f"DELTA={r['CROSS_MINUS_PRICE_MEAN_BPS']:+.4f} "
                        f"EXT_ONLY={r['EXTERNAL_ONLY_MEAN_BPS']:+.4f}"
                    )
        lines.append("")

    lines.append("ALL_NEWS GE2 — DIRECTION DECOMPOSITION, ALL HISTORY:")
    for h in (30,90):
        for subset in ("CROSS_EQ_PRICE_MR","CROSS_NE_PRICE_MR"):
            r=next((x for x in critical if x["SCOPE"]=="ALL_NEWS" and x["PERIOD"]=="ALL"
                    and x["HORIZON_MIN"]==h and x["SUBSET"]==subset),None)
            if r:
                lines.append(
                    f" H+{h}m {subset}: N={r['N']} CROSS={r['CROSS_MEAN_BPS']:+.4f} "
                    f"PRICE_MR={r['PRICE_MR_MEAN_BPS']:+.4f} DELTA={r['CROSS_MINUS_PRICE_MEAN_BPS']:+.4f}"
                )

    (a.out/"NEWS04.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
