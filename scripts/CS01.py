#!/usr/bin/env python3
"""
CS01 — 8-currency strength engine, H4.

Currencies: AUD CAD CHF EUR GBP JPY NZD USD
Universe: all 28 standard crosses available in the canonical dataset.

For a closed H4 bar t:
- pair return = log(close[t] / close[t-6]) = 24h lookback
- RAW currency strength = mean signed return across its constituent pairs
- VOL strength = mean pair return normalized by causal 30-bar H4 volatility
- EURUSD is excluded from EUR and USD strength when evaluating EURUSD
  (leave-one-pair-out), so the cross-market features do not contain target price.
- breadth is the signed fraction of EUR/USD component votes supporting the
  EUR-vs-USD direction.
No trading, no fitting, no future data.
"""
import argparse,csv,json,math,statistics
from pathlib import Path
from drummond_replay01 import read_xfbar

CURS=["AUD","CAD","CHF","EUR","GBP","JPY","NZD","USD"]
PAIRS=[
"AUDCAD","AUDCHF","AUDJPY","AUDNZD","AUDUSD",
"CADCHF","CADJPY","CHFJPY",
"EURAUD","EURCAD","EURCHF","EURGBP","EURJPY","EURNZD","EURUSD",
"GBPAUD","GBPCAD","GBPCHF","GBPJPY","GBPNZD","GBPUSD",
"NZDCAD","NZDCHF","NZDJPY","NZDUSD",
"USDCAD","USDCHF","USDJPY"]
LB=6
VOL=30
TARGET="EURUSD"

def stdev(xs):
    if len(xs)<2:return None
    return statistics.stdev(xs)

def load(root,p):
    path=root/p/(p+"_H4.bin")
    if not path.exists(): raise SystemExit("missing "+str(path))
    h,b=read_xfbar(path)
    if h["period_seconds"]!=14400: raise SystemExit(p+" not H4")
    return {int(x[0]):float(x[4]) for x in b}

def rank_map(d):
    vals=sorted((v,k) for k,v in d.items())
    return {k:i for i,(_,k) in enumerate(vals)}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    s={p:load(a.root,p) for p in PAIRS}
    common=sorted(set.intersection(*(set(s[p]) for p in PAIRS)))
    if len(common)<VOL+LB+100: raise SystemExit("insufficient common bars")

    rows=[]
    for i in range(max(VOL,LB),len(common)):
        t=common[i];t0=common[i-LB]
        raw={c:[] for c in CURS}; voln={c:[] for c in CURS}
        eurusd_votes=[]
        for p in PAIRS:
            b=p[:3];q=p[3:]
            r=math.log(s[p][t]/s[p][t0])

            one=[]
            for j in range(i-VOL+1,i+1):
                ta=common[j-1];tb=common[j]
                one.append(math.log(s[p][tb]/s[p][ta]))
            sd=stdev(one)
            z=r/(sd*math.sqrt(LB)) if sd and sd>0 else 0.0

            if p!=TARGET:
                raw[b].append(r);raw[q].append(-r)
                voln[b].append(z);voln[q].append(-z)

                if b=="EUR": eurusd_votes.append(1 if r>0 else (-1 if r<0 else 0))
                elif q=="EUR": eurusd_votes.append(1 if -r>0 else (-1 if -r<0 else 0))
                if b=="USD": eurusd_votes.append(1 if -r>0 else (-1 if -r<0 else 0))
                elif q=="USD": eurusd_votes.append(1 if r>0 else (-1 if r<0 else 0))
            else:
                # keep target out of EUR/USD strength; no contribution at all
                pass

        rs={c:statistics.fmean(raw[c]) for c in CURS}
        vs={c:statistics.fmean(voln[c]) for c in CURS}
        rr=rank_map(rs); vr=rank_map(vs)

        own=math.log(s[TARGET][t]/s[TARGET][t0])
        breadth=(sum(eurusd_votes)/len(eurusd_votes)) if eurusd_votes else 0.0
        row={
            "TIME":t,
            "OWN_RET24":own,
            "EUR_RAW":rs["EUR"],"USD_RAW":rs["USD"],"DIFF_RAW":rs["EUR"]-rs["USD"],
            "EUR_VOL":vs["EUR"],"USD_VOL":vs["USD"],"DIFF_VOL":vs["EUR"]-vs["USD"],
            "EUR_RANK":rr["EUR"],"USD_RANK":rr["USD"],"RANK_DIFF":rr["EUR"]-rr["USD"],
            "EUR_VOL_RANK":vr["EUR"],"USD_VOL_RANK":vr["USD"],"VOL_RANK_DIFF":vr["EUR"]-vr["USD"],
            "BREADTH_SIGNED":breadth
        }
        for c in CURS:
            row[c+"_RAW"]=rs[c]
            row[c+"_VOL"]=vs[c]
        rows.append(row)

    outcsv=a.out/"CS01_STATES.csv"
    with outcsv.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys()),delimiter=";")
        w.writeheader();w.writerows(rows)

    meta={
      "block":"CS01","status":"PASS","timeframe":"H4","currencies":CURS,"pairs":PAIRS,
      "common_bars":len(common),"state_rows":len(rows),"lookback_h4":LB,"vol_window_h4":VOL,
      "target_pair":"EURUSD","target_excluded_from_strength":True,
      "contract":{"trading_or_pnl":False,"parameter_optimization":False,"lookahead":False}
    }
    (a.out/"CS01.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("CURRENCY STRENGTH CS01")
    print("STATUS: PASS")
    print("COMMON_BARS:",len(common),"STATE_ROWS:",len(rows))
    print("TARGET_EXCLUDED_FROM_STRENGTH: YES")
    print("TRADING/PNL: NO")
    print("OPTIMIZATION: NO")
if __name__=="__main__": main()
