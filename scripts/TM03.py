#!/usr/bin/env python3
"""
TM03 — XAUUSD electronic microscope / forensic audit.

Descriptive only. No filtering, optimization, or new trading rule is created.
The purpose is to identify where TM01 gross expectancy comes from and how
concentrated it is in time, holding duration, structural risk, side, and exit.

Consumes the frozen XAUUSD_TM01_TRADES.csv + XAUUSD_TM01.json artifact.
"""
import argparse,csv,json,math,statistics
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

HOLD_BINS=[
    ("0-5",0,5),("6-15",6,15),("16-60",16,60),
    ("61-240",61,240),("241-1440",241,1440),("1441+",1441,None)
]
WAIT_BINS=[
    ("0",0,0),("1-5",1,5),("6-15",6,15),("16-60",16,60),("61+",61,None)
]
RISK_BINS=[
    ("1-10",1,10),("11-25",11,25),("26-50",26,50),("51-100",51,100),
    ("101-250",101,250),("251-500",251,500),("501-1000",501,1000),("1001+",1001,None)
]
RETURN_BINS=[
    ("<=-1R",None,-1.0),("-1..0R",-1.0,0.0),("0..1R",0.0,1.0),
    ("1..2R",1.0,2.0),("2..5R",2.0,5.0),("5..10R",5.0,10.0),
    ("10..20R",10.0,20.0),("20R+",20.0,None)
]
COST_POINTS=(0,1,2,5)
TOP_FRACS=(0.001,0.005,0.01)

def metric(vals):
    if not vals:return {"n":0}
    pos=sum(x for x in vals if x>0)
    neg=-sum(x for x in vals if x<0)
    return {
        "n":len(vals),"mean":sum(vals)/len(vals),"median":statistics.median(vals),
        "sum":sum(vals),"win_rate":sum(x>0 for x in vals)/len(vals),
        "profit_factor":pos/neg if neg>0 else None,
        "min":min(vals),"max":max(vals)
    }

def pick_bin(v,bins,inclusive_high=True):
    for name,lo,hi in bins:
        if lo is None:
            if v<=hi:return name
        elif hi is None:
            if v>=lo:return name
        else:
            if inclusive_high:
                if lo<=v<=hi:return name
            else:
                if lo<=v<hi:return name
    return "OTHER"

def read_inputs(root):
    js=list(root.rglob("XAUUSD_TM01.json"))
    cs=list(root.rglob("XAUUSD_TM01_TRADES.csv"))
    if len(js)!=1 or len(cs)!=1:
        raise SystemExit(f"TM03 expected one XAUUSD summary/trades: json={len(js)} csv={len(cs)}")
    s=json.loads(js[0].read_text(encoding="utf-8"))
    if s["status"]!="PASS" or s["contract"]["lookahead"] or s["contract"]["selection_or_optimization"]:
        raise SystemExit("TM01 XAUUSD causal contract invalid")
    point=float(s["data"]["point"])
    rows=[]
    with cs[0].open("r",encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f,delimiter=";"):
            trigger=float(r["ENTRY_TRIGGER"]); stop=float(r["STOP"])
            risk_points=abs(trigger-stop)/point
            if risk_points<=0 or not math.isfinite(risk_points):
                raise SystemExit("invalid structural risk")
            et=int(r["ENTRY_TIME"])
            rows.append({
                "side":r["SIDE"],"entry_time":et,
                "entry_iso":datetime.fromtimestamp(et,tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "year":datetime.fromtimestamp(et,tz=timezone.utc).year,
                "gross_r":float(r["GROSS_R"]),
                "risk_points":risk_points,
                "wait":int(r["WAIT_M1"]),"hold":int(r["HOLD_M1"]),
                "outcome":r["OUTCOME"],
                "trigger":trigger,"stop":stop,
                "exit":float(r["EXIT_GROSS"])
            })
    return s,point,rows

def cost_r(r,pts):
    return r["gross_r"]-pts/r["risk_points"]

def group_metric(rows,keyfunc,cost=0):
    g=defaultdict(list)
    for r in rows:g[keyfunc(r)].append(r)
    out=[]
    for k in sorted(g,key=lambda x:str(x)):
        rr=g[k]; vals=[cost_r(r,cost) for r in rr]; m=metric(vals)
        out.append((k,rr,m))
    return out

def write_csv(path,rows):
    if not rows:return
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys()),delimiter=";")
        w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    s,point,rows=read_inputs(a.root)
    n=len(rows)
    gross=metric([r["gross_r"] for r in rows])

    # Year-by-year robustness under fixed point costs.
    yearly=[]
    years=sorted({r["year"] for r in rows})
    for y in years:
        yr=[r for r in rows if r["year"]==y]
        for pts in COST_POINTS:
            m=metric([cost_r(r,pts) for r in yr])
            yearly.append({
                "YEAR":y,"TOTAL_COST_POINTS":pts,"N":m["n"],
                "MEAN_R":m["mean"],"SUM_R":m["sum"],"WIN_RATE":m["win_rate"],
                "PROFIT_FACTOR":m["profit_factor"]
            })
    write_csv(a.out/"TM03_YEARLY.csv",yearly)

    # Side / outcome.
    structural=[]
    for label,keyfn in [
        ("SIDE",lambda r:r["side"]),
        ("OUTCOME",lambda r:r["outcome"]),
    ]:
        for key,rr,m in group_metric(rows,keyfn):
            structural.append({
                "DIMENSION":label,"BUCKET":key,"N":m["n"],"MEAN_R":m["mean"],
                "SUM_R":m["sum"],"WIN_RATE":m["win_rate"],"PROFIT_FACTOR":m["profit_factor"],
                "MEDIAN_HOLD_M1":statistics.median(r["hold"] for r in rr),
                "MEDIAN_RISK_POINTS":statistics.median(r["risk_points"] for r in rr)
            })
    write_csv(a.out/"TM03_STRUCTURE.csv",structural)

    # Fixed bins, descriptive only.
    bins_out=[]
    defs=[
        ("HOLD_M1",HOLD_BINS,lambda r:r["hold"],True),
        ("WAIT_M1",WAIT_BINS,lambda r:r["wait"],True),
        ("RISK_POINTS",RISK_BINS,lambda r:r["risk_points"],True),
        ("GROSS_R",RETURN_BINS,lambda r:r["gross_r"],False),
    ]
    for dim,bins,fn,incl in defs:
        grouped=defaultdict(list)
        for r in rows:
            grouped[pick_bin(fn(r),bins,incl)].append(r)
        for name,_,_ in bins:
            rr=grouped.get(name,[])
            if not rr:continue
            m=metric([r["gross_r"] for r in rr])
            bins_out.append({
                "DIMENSION":dim,"BUCKET":name,"N":m["n"],"MEAN_R":m["mean"],
                "SUM_R":m["sum"],"WIN_RATE":m["win_rate"],"PROFIT_FACTOR":m["profit_factor"],
                "SHARE_OF_ALL_TRADES":len(rr)/n,
                "SHARE_OF_TOTAL_GROSS_R":(m["sum"]/gross["sum"] if gross["sum"] else None)
            })
    write_csv(a.out/"TM03_BINS.csv",bins_out)

    # Top winners: fixed fractions plus top 100 exact trade file.
    sorted_win=sorted(rows,key=lambda r:r["gross_r"],reverse=True)
    top_summary=[]
    total_positive=sum(r["gross_r"] for r in rows if r["gross_r"]>0)
    for frac in TOP_FRACS:
        k=max(1,math.ceil(n*frac)); top=sorted_win[:k]
        sm=sum(r["gross_r"] for r in top)
        top_summary.append({
            "TOP_FRACTION":frac,"TOP_TRADES":k,"SUM_R":sm,
            "SHARE_OF_TOTAL_GROSS_R":sm/gross["sum"] if gross["sum"] else None,
            "SHARE_OF_POSITIVE_R":sm/total_positive if total_positive else None,
            "MEDIAN_R":statistics.median(r["gross_r"] for r in top),
            "MEDIAN_HOLD_M1":statistics.median(r["hold"] for r in top),
            "MEDIAN_RISK_POINTS":statistics.median(r["risk_points"] for r in top),
            "LONG_SHARE":sum(r["side"]=="LONG" for r in top)/k,
            "STOP_EXIT_SHARE":sum(r["outcome"]=="STOP" for r in top)/k,
            "OPPOSITE_IQAMAT_SHARE":sum(r["outcome"]=="OPPOSITE_IQAMAT" for r in top)/k,
        })
    write_csv(a.out/"TM03_TAIL_CONCENTRATION.csv",top_summary)

    top100=[]
    for rank,r in enumerate(sorted_win[:100],1):
        top100.append({
            "RANK":rank,"ENTRY_ISO":r["entry_iso"],"YEAR":r["year"],"SIDE":r["side"],
            "GROSS_R":r["gross_r"],"HOLD_M1":r["hold"],"WAIT_M1":r["wait"],
            "RISK_POINTS":r["risk_points"],"OUTCOME":r["outcome"],
            "ENTRY_TRIGGER":r["trigger"],"STOP":r["stop"],"EXIT":r["exit"]
        })
    write_csv(a.out/"TM03_TOP100.csv",top100)

    # Contribution concentration by year, including top-tail counts.
    top01=set(id(r) for r in sorted_win[:max(1,math.ceil(n*0.001))])
    ycon=[]
    for y in years:
        yr=[r for r in rows if r["year"]==y]
        m=metric([r["gross_r"] for r in yr])
        ycon.append({
            "YEAR":y,"N":len(yr),"SUM_R":m["sum"],"MEAN_R":m["mean"],
            "SHARE_OF_TOTAL_GROSS_R":m["sum"]/gross["sum"] if gross["sum"] else None,
            "TOP_0_1PCT_TRADES":sum(id(r) in top01 for r in yr),
            "TOP_0_1PCT_R":sum(r["gross_r"] for r in yr if id(r) in top01)
        })
    write_csv(a.out/"TM03_YEAR_CONTRIBUTION.csv",ycon)

    # Fixed eras, no fitting.
    era_defs=[("2004-2009",2004,2009),("2010-2014",2010,2014),("2015-2019",2015,2019),
              ("2020-2024",2020,2024),("2025-2026",2025,2026)]
    eras=[]
    for name,lo,hi in era_defs:
        rr=[r for r in rows if lo<=r["year"]<=hi]
        if not rr:continue
        for pts in COST_POINTS:
            m=metric([cost_r(r,pts) for r in rr])
            eras.append({
                "ERA":name,"TOTAL_COST_POINTS":pts,"N":m["n"],"MEAN_R":m["mean"],
                "SUM_R":m["sum"],"WIN_RATE":m["win_rate"],"PROFIT_FACTOR":m["profit_factor"]
            })
    write_csv(a.out/"TM03_ERAS.csv",eras)

    pos_years={}
    for pts in COST_POINTS:
        vals=[]
        for y in years:
            yr=[r for r in rows if r["year"]==y]
            vals.append((y,sum(cost_r(r,pts) for r in yr)))
        pos_years[str(pts)]={
            "positive":sum(v>0 for _,v in vals),
            "negative":sum(v<0 for _,v in vals),
            "zero":sum(v==0 for _,v in vals),
            "total":len(vals)
        }

    top01=top_summary[0]
    summary={
        "block":"TM03","status":"PASS","symbol":"XAUUSD","trades":n,
        "gross":gross,
        "point":point,
        "positive_year_counts_by_total_cost_points":pos_years,
        "tail":{
            "top_0_1_pct":top01,
            "largest_trade_r":sorted_win[0]["gross_r"],
            "largest_trade_entry_iso":sorted_win[0]["entry_iso"],
            "largest_trade_hold_m1":sorted_win[0]["hold"],
            "largest_trade_risk_points":sorted_win[0]["risk_points"]
        },
        "all_trade_medians":{
            "hold_m1":statistics.median(r["hold"] for r in rows),
            "wait_m1":statistics.median(r["wait"] for r in rows),
            "risk_points":statistics.median(r["risk_points"] for r in rows)
        },
        "contract":{
            "descriptive_only":True,
            "new_filter_or_rule":False,
            "selection_or_optimization":False,
            "lookahead":False,
            "fixed_cost_points":list(COST_POINTS),
            "fixed_tail_fractions":list(TOP_FRACS)
        }
    }
    (a.out/"TM03.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
        "TAKBIR M1 TM03 — XAUUSD ELECTRONIC MICROSCOPE",
        "STATUS: PASS",
        f"TRADES: {n}",
        f"GROSS: MEAN_R={gross['mean']:+.6f} SUM_R={gross['sum']:+.1f} PF={(gross['profit_factor'] or 0):.6f}",
        f"YEARS: {min(years)}-{max(years)} ({len(years)} calendar years with trades)",
        "POSITIVE YEARS: "+", ".join(f"{p}pt={pos_years[str(p)]['positive']}/{pos_years[str(p)]['total']}" for p in COST_POINTS),
        f"ALL MEDIANS: HOLD={summary['all_trade_medians']['hold_m1']:.1f}m WAIT={summary['all_trade_medians']['wait_m1']:.1f}m RISK={summary['all_trade_medians']['risk_points']:.1f}pt",
        f"TOP 0.1%: N={top01['TOP_TRADES']} SUM_R={top01['SUM_R']:+.1f} SHARE_TOTAL={top01['SHARE_OF_TOTAL_GROSS_R']:.3f} SHARE_POSITIVE={top01['SHARE_OF_POSITIVE_R']:.3f}",
        f"TOP 0.1% MEDIANS: R={top01['MEDIAN_R']:+.3f} HOLD={top01['MEDIAN_HOLD_M1']:.1f}m RISK={top01['MEDIAN_RISK_POINTS']:.1f}pt LONG_SHARE={top01['LONG_SHARE']:.3f}",
        f"LARGEST: R={summary['tail']['largest_trade_r']:+.3f} ENTRY={summary['tail']['largest_trade_entry_iso']} HOLD={summary['tail']['largest_trade_hold_m1']}m RISK={summary['tail']['largest_trade_risk_points']:.1f}pt",
        "LOOKAHEAD: NO",
        "SELECTION/OPTIMIZATION: NO",
        "NEW TRADING FILTER: NO"
    ]
    (a.out/"TM03.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
