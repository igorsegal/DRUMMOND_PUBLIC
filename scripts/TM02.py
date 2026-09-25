#!/usr/bin/env python3
"""
TM02 — TAKBIR M1 hard cost + tail stress.

Consumes the frozen TM01 trade artifacts for EURUSD, USDJPY, XAUUSD.
No trade selection, no parameter fitting, no signal changes.

Cost model:
  NET_R = GROSS_R - total_cost_points / structural_risk_points

The point-equivalent round-trip cost is decomposed as:
  spread_points + 2 * slippage_points_per_fill + commission_points_round_trip

Because the MT4 M1 history exported zero historical spreads and does not include
contract/tick-value commission metadata, TM02 does NOT pretend to know broker
money costs. It applies a deliberately broad, predeclared stress grid in native
symbol points, plus an independent direct R-cost grid.

Tail stress:
- cap only positive trade R at fixed ceilings
- remove the largest positive trades by fixed fractions
This tests dependence on rare outsized winners without changing entries/exits.
"""
import argparse,csv,json,math,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

POINT_COSTS=[0,1,2,5,10,20,50,100]
R_COSTS=[0.0,0.005,0.01,0.02,0.03,0.05,0.10,0.20]
TAIL_CAPS=[None,50.0,20.0,10.0,5.0]
TOP_REMOVE_FRACS=[0.001,0.005,0.01]

NAMED_COSTS=[
    ("ZERO",0,0,0),
    ("COST_1_1_1",1,1,1),   # total 4 points
    ("COST_2_2_2",2,2,2),   # total 8 points
    ("COST_5_5_5",5,5,5),   # total 20 points
    ("COST_10_10_10",10,10,10), # total 40 points
]

def metric(vals):
    if not vals:
        return {"n":0}
    pos=sum(x for x in vals if x>0)
    neg=-sum(x for x in vals if x<0)
    return {
        "n":len(vals),
        "mean":sum(vals)/len(vals),
        "median":statistics.median(vals),
        "sum":sum(vals),
        "win_rate":sum(x>0 for x in vals)/len(vals),
        "profit_factor":(pos/neg if neg>0 else None),
        "min":min(vals),
        "max":max(vals),
    }

def load(root):
    summaries=sorted(root.rglob("*_TM01.json"))
    trades=sorted(root.rglob("*_TM01_TRADES.csv"))
    if len(summaries)!=3 or len(trades)!=3:
        raise SystemExit(f"TM02 expected 3 TM01 summaries/trade files; json={len(summaries)} csv={len(trades)}")

    meta={}
    for p in summaries:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s["status"]!="PASS":
            raise SystemExit(f"TM01 summary not PASS: {p}")
        if s["contract"]["lookahead"] or s["contract"]["selection_or_optimization"]:
            raise SystemExit(f"TM01 causal contract violation: {p}")
        meta[s["symbol"]]=s

    rows=[]
    for p in trades:
        with p.open("r",encoding="utf-8-sig",newline="") as f:
            for r in csv.DictReader(f,delimiter=";"):
                sym=r["SYMBOL"]
                if sym not in meta:
                    raise SystemExit(f"trade symbol {sym} missing summary")
                point=float(meta[sym]["data"]["point"])
                trigger=float(r["ENTRY_TRIGGER"])
                stop=float(r["STOP"])
                risk_price=abs(trigger-stop)
                risk_points=risk_price/point if point>0 else 0.0
                if not math.isfinite(risk_points) or risk_points<=0:
                    raise SystemExit(f"invalid risk points: {sym} {risk_points}")
                rows.append({
                    "symbol":sym,
                    "side":r["SIDE"],
                    "entry_time":int(r["ENTRY_TIME"]),
                    "gross_r":float(r["GROSS_R"]),
                    "risk_points":risk_points,
                    "point":point,
                })
    return meta,rows

def scopes(rows):
    syms=sorted({r["symbol"] for r in rows})
    out={"ALL":rows}
    for s in syms: out[s]=[r for r in rows if r["symbol"]==s]
    out["LONG"]=[r for r in rows if r["side"]=="LONG"]
    out["SHORT"]=[r for r in rows if r["side"]=="SHORT"]
    return out

def net_vals(rr,total_points=0.0,direct_r=0.0,cap=None):
    vals=[]
    for r in rr:
        g=r["gross_r"]
        if cap is not None and g>cap:
            g=cap
        vals.append(g - total_points/r["risk_points"] - direct_r)
    return vals

def break_even_points(rr):
    if not rr:return None
    mg=sum(r["gross_r"] for r in rr)/len(rr)
    inv=sum(1.0/r["risk_points"] for r in rr)/len(rr)
    if inv<=0:return None
    return mg/inv

def top_removed_vals(rr,frac):
    if not rr:return []
    n=max(1,math.ceil(len(rr)*frac))
    order=sorted(range(len(rr)),key=lambda i:rr[i]["gross_r"],reverse=True)
    banned=set(order[:n])
    return [r["gross_r"] for i,r in enumerate(rr) if i not in banned]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)

    meta,rows=load(a.root)
    sc=scopes(rows)

    grid=[]
    named=[]
    rcost=[]
    tail=[]
    removal=[]
    yearly=[]

    # 1) Point-equivalent total round-trip cost grid.
    for scope,rr in sc.items():
        for pts in POINT_COSTS:
            m=metric(net_vals(rr,total_points=pts))
            grid.append({
                "SCOPE":scope,"TOTAL_COST_POINTS":pts,"N":m["n"],
                "MEAN_R":m["mean"],"SUM_R":m["sum"],"WIN_RATE":m["win_rate"],
                "PROFIT_FACTOR":m["profit_factor"],"MEDIAN_R":m["median"]
            })

    # 2) Explicit spread/slippage/commission decomposition.
    for scope,rr in sc.items():
        for name,spread,slip,comm in NAMED_COSTS:
            total=spread+2*slip+comm
            m=metric(net_vals(rr,total_points=total))
            named.append({
                "SCOPE":scope,"SCENARIO":name,
                "SPREAD_POINTS":spread,
                "SLIPPAGE_POINTS_PER_FILL":slip,
                "COMMISSION_POINTS_ROUND_TRIP":comm,
                "TOTAL_COST_POINTS":total,
                "N":m["n"],"MEAN_R":m["mean"],"SUM_R":m["sum"],
                "WIN_RATE":m["win_rate"],"PROFIT_FACTOR":m["profit_factor"]
            })

    # 3) Direct R-cost grid, instrument-independent.
    for scope,rr in sc.items():
        for cr in R_COSTS:
            m=metric(net_vals(rr,direct_r=cr))
            rcost.append({
                "SCOPE":scope,"ROUND_TRIP_COST_R":cr,"N":m["n"],
                "MEAN_R":m["mean"],"SUM_R":m["sum"],"WIN_RATE":m["win_rate"],
                "PROFIT_FACTOR":m["profit_factor"]
            })

    # 4) Tail caps crossed with point costs.
    for scope,rr in sc.items():
        for cap in TAIL_CAPS:
            for pts in POINT_COSTS:
                m=metric(net_vals(rr,total_points=pts,cap=cap))
                tail.append({
                    "SCOPE":scope,
                    "POSITIVE_R_CAP":"UNCAPPED" if cap is None else cap,
                    "TOTAL_COST_POINTS":pts,
                    "N":m["n"],"MEAN_R":m["mean"],"SUM_R":m["sum"],
                    "WIN_RATE":m["win_rate"],"PROFIT_FACTOR":m["profit_factor"]
                })

    # 5) Delete the best 0.1%, 0.5%, 1% trades entirely.
    for scope,rr in sc.items():
        for frac in TOP_REMOVE_FRACS:
            vals=top_removed_vals(rr,frac)
            m=metric(vals)
            removal.append({
                "SCOPE":scope,"TOP_FRACTION_REMOVED":frac,
                "REMOVED_TRADES":len(rr)-len(vals),
                "N_LEFT":m["n"],"MEAN_R":m["mean"],"SUM_R":m["sum"],
                "WIN_RATE":m["win_rate"],"PROFIT_FACTOR":m["profit_factor"]
            })

    # 6) Calendar-year robustness at 0 / 5 / 10 point total cost.
    for scope,rr in sc.items():
        groups=defaultdict(list)
        for r in rr:
            y=datetime.fromtimestamp(r["entry_time"],tz=timezone.utc).year
            groups[y].append(r)
        for y in sorted(groups):
            yr=groups[y]
            for pts in (0,5,10):
                m=metric(net_vals(yr,total_points=pts))
                yearly.append({
                    "SCOPE":scope,"YEAR":y,"TOTAL_COST_POINTS":pts,
                    "N":m["n"],"MEAN_R":m["mean"],"SUM_R":m["sum"],
                    "WIN_RATE":m["win_rate"],"PROFIT_FACTOR":m["profit_factor"]
                })

    # CSV writers
    def write(name,rows_):
        p=a.out/name
        fields=list(rows_[0].keys())
        with p.open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields,delimiter=";")
            w.writeheader();w.writerows(rows_)

    write("TM02_POINT_COST_GRID.csv",grid)
    write("TM02_NAMED_COSTS.csv",named)
    write("TM02_R_COST_GRID.csv",rcost)
    write("TM02_TAIL_CAP_GRID.csv",tail)
    write("TM02_TOP_WIN_REMOVAL.csv",removal)
    write("TM02_YEARLY.csv",yearly)

    summary={
        "block":"TM02",
        "status":"PASS",
        "symbols":sorted(meta),
        "trades":len(rows),
        "contract":{
            "signals_or_entries_changed":False,
            "selection_or_optimization":False,
            "lookahead":False,
            "historical_spread_available":False,
            "money_commission_available":False,
            "point_cost_formula":"spread + 2*slippage_per_fill + commission_round_trip",
            "net_r_formula":"gross_r - total_cost_points / structural_risk_points",
            "point_cost_grid":POINT_COSTS,
            "direct_r_cost_grid":R_COSTS,
            "positive_r_caps":["UNCAPPED",50,20,10,5],
            "top_winner_removal_fractions":TOP_REMOVE_FRACS
        },
        "break_even":{
            scope:{
                "gross_mean_r":metric([r["gross_r"] for r in rr])["mean"],
                "break_even_direct_cost_r":metric([r["gross_r"] for r in rr])["mean"],
                "break_even_total_cost_points":break_even_points(rr)
            } for scope,rr in sc.items()
        }
    }
    (a.out/"TM02.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=[
        "TAKBIR M1 TM02 — HARD COST + TAIL STRESS",
        "STATUS: PASS",
        "SYMBOLS: "+", ".join(sorted(meta)),
        f"TRADES: {len(rows)}",
        "LOOKAHEAD: NO",
        "SELECTION/OPTIMIZATION: NO",
        "HISTORICAL SPREAD: NOT AVAILABLE (MT4 M1 field was zero)",
        "MONEY COMMISSION: NOT AVAILABLE; commission is stressed in point-equivalent units",
        ""
    ]
    for scope in ("ALL","EURUSD","USDJPY","XAUUSD","LONG","SHORT"):
        rr=sc.get(scope)
        if not rr:continue
        be=summary["break_even"][scope]
        g=metric([r["gross_r"] for r in rr])
        lines.append(
            f"{scope}: N={g['n']} GROSS_MEAN_R={g['mean']:+.6f} PF={(g['profit_factor'] or 0):.6f} "
            f"BREAK_EVEN_COST_R={be['break_even_direct_cost_r']:.6f} "
            f"BREAK_EVEN_TOTAL_POINTS={be['break_even_total_cost_points']:.3f}"
        )
        for pts in (1,2,5,10,20,50):
            m=metric(net_vals(rr,total_points=pts))
            lines.append(
                f"  COST {pts:>3} pts: MEAN_R={m['mean']:+.6f} SUM_R={m['sum']:+.1f} PF={(m['profit_factor'] or 0):.6f}"
            )
        for cap in (20.0,10.0,5.0):
            m=metric(net_vals(rr,cap=cap))
            lines.append(
                f"  CAP +{cap:g}R: MEAN_R={m['mean']:+.6f} SUM_R={m['sum']:+.1f} PF={(m['profit_factor'] or 0):.6f}"
            )
        for frac in TOP_REMOVE_FRACS:
            m=metric(top_removed_vals(rr,frac))
            lines.append(
                f"  REMOVE TOP {frac*100:g}%: MEAN_R={m['mean']:+.6f} SUM_R={m['sum']:+.1f} PF={(m['profit_factor'] or 0):.6f}"
            )
        lines.append("")

    # Named severe combined scenario for quick reading: spread 5 + slip 5 each side + commission 5 = 20 pts.
    lines.append("HARD COMBINED SCENARIO = spread 5 pts + slippage 5 pts/fill + commission 5 pts/round-trip = 20 total points.")
    (a.out/"TM02.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
