#!/usr/bin/env python3
"""
CS04 — matched price-only controls and temporal stability.

Cross-market CS02 events are compared with price-only analogues constructed
from EURUSD's own 24h return using the same causal mechanics where possible.
This prevents a reversal feature from being "credited" merely for being the
opposite of a momentum baseline.

Fixed holdout: 2022-01-01 onward. Also reports yearly sign stability.
No trading/PnL, no optimization.
"""
import argparse,csv,json,math,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from drummond_replay01 import read_xfbar

FEATURES=["F1_CROSS","F2_POSTCROSS_SEPARATION","F3_OPPOSING_SLOPES",
          "F4_LARGE_DISTANCE","F5_EXTREME_CONVERGENCE","F6_ACCELERATION",
          "F7_LEADERSHIP_DURATION","F8_BREADTH"]
H=[1,3,6,18]
ROLL=252
SPLIT=int(datetime(2022,1,1,tzinfo=timezone.utc).timestamp())

def sgn(x):return 1 if x>0 else (-1 if x<0 else 0)
def avg(x):return statistics.fmean(x) if x else None
def qtile(xs,q):
    if not xs:return None
    z=sorted(xs);p=(len(z)-1)*q;lo=int(p);hi=min(len(z)-1,lo+1);f=p-lo
    return z[lo]*(1-f)+z[hi]*f

def build_price_analogs(states):
    out=[];last=0;since=10**9;lead=0;prev=None;prev_speed=None;dists=[]
    for r in states:
        o=r["OWN_RET24"];so=sgn(o);cross=0
        if last and so and so!=last:
            cross=so;since=0;lead=1
        else:
            since+=1
            if so and so==last:lead+=1
            elif so:lead=1
            else:lead=0
        if so:last=so
        speed=o-prev if prev is not None else 0.0
        accel=speed-prev_speed if prev_speed is not None else 0.0
        dist=abs(o);pd=abs(prev) if prev is not None else None
        hist=dists[max(0,len(dists)-ROLL):]
        q75=qtile(hist,.75) if len(hist)>=50 else None
        q90=qtile(hist,.90) if len(hist)>=50 else None
        f2=so*(dist-pd) if since<=3 and pd is not None and dist>pd else 0.0
        f4=o if q75 is not None and dist>=q75 else 0.0
        f5=-sgn(prev)*(pd-dist) if q90 is not None and pd is not None and pd>=q90 and dist<pd else 0.0
        out.append({"TIME":r["TIME"],"P1":float(cross),"P2":f2,"P3":speed,
                    "P4":f4,"P5":f5,"P6":accel,
                    "P7":so*lead if lead>=6 else 0.0,"P8":o})
        dists.append(dist);prev=o;prev_speed=speed
    return out

def metric(rows,key,ykey):
    rr=[r for r in rows if r[key]!=0]
    v=[sgn(r[key])*r[ykey]*10000 for r in rr]
    return {"n":len(rr),"mean":avg(v),"acc":sum(x>0 for x in v)/len(v) if v else None}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--states",type=Path,required=True)
    ap.add_argument("--features",type=Path,required=True)
    ap.add_argument("--eurusd",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    with a.states.open("r",encoding="utf-8-sig",newline="") as f:
        states=[{"TIME":int(float(r["TIME"])),"OWN_RET24":float(r["OWN_RET24"])} for r in csv.DictReader(f,delimiter=";")]
    price=build_price_analogs(states);pmap={r["TIME"]:r for r in price}
    with a.features.open("r",encoding="utf-8-sig",newline="") as f: fr=list(csv.DictReader(f,delimiter=";"))
    hdr,bars=read_xfbar(a.eurusd);close={int(b[0]):float(b[4]) for b in bars}

    outputs=[];yearly=[]
    for form in ("RAW","VOL"):
        rr=[]
        for r in fr:
            if r["FORMULA"]!=form:continue
            t=int(float(r["TIME"]))
            z={"TIME":t,"YEAR":datetime.fromtimestamp(t,tz=timezone.utc).year}
            for k in FEATURES:z[k]=float(r[k])
            for j in range(1,9):z["P"+str(j)]=pmap[t]["P"+str(j)]
            rr.append(z)
        rr.sort(key=lambda x:x["TIME"])
        times=[r["TIME"] for r in rr]
        enrich=[]
        for i,r in enumerate(rr):
            if i+max(H)>=len(rr):continue
            z=dict(r);ok=True
            for h in H:
                if r["TIME"] not in close or times[i+h] not in close:ok=False;break
                z["Y"+str(h)]=math.log(close[times[i+h]]/close[r["TIME"]])
            if ok:enrich.append(z)

        for h in H:
            yk="Y"+str(h)
            for j,feat in enumerate(FEATURES,1):
                pk="P"+str(j)
                for period,pred in [("ALL",lambda r:True),("PRE2022",lambda r:r["TIME"]<SPLIT),("HOLDOUT2022+",lambda r:r["TIME"]>=SPLIT)]:
                    sub=[r for r in enrich if pred(r)]
                    cm=metric(sub,feat,yk);pm=metric(sub,pk,yk)
                    outputs.append({"FORMULA":form,"HORIZON_H4":h,"FEATURE":feat,"PERIOD":period,
                                    "CROSS_N":cm["n"],"CROSS_MEAN_SIGNED_BPS":cm["mean"],"CROSS_ACCURACY":cm["acc"],
                                    "PRICE_ANALOG_N":pm["n"],"PRICE_ANALOG_MEAN_SIGNED_BPS":pm["mean"],"PRICE_ANALOG_ACCURACY":pm["acc"],
                                    "DELTA_CROSS_MINUS_PRICE_BPS":(cm["mean"]-pm["mean"] if cm["mean"] is not None and pm["mean"] is not None else None)})
                for y in sorted({r["YEAR"] for r in enrich}):
                    sub=[r for r in enrich if r["YEAR"]==y]
                    cm=metric(sub,feat,yk);pm=metric(sub,pk,yk)
                    yearly.append({"FORMULA":form,"HORIZON_H4":h,"FEATURE":feat,"YEAR":y,
                                   "CROSS_N":cm["n"],"CROSS_MEAN_SIGNED_BPS":cm["mean"],
                                   "PRICE_N":pm["n"],"PRICE_MEAN_SIGNED_BPS":pm["mean"]})

    def write(name,data):
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys()),delimiter=";");w.writeheader();w.writerows(data)
    write("CS04_MATCHED.csv",outputs);write("CS04_YEARLY.csv",yearly)

    # Headline: holdout winners by delta, but only descriptive; no selection into trading.
    head={}
    for form in ("RAW","VOL"):
        head[form]={}
        for h in H:
            z=[r for r in outputs if r["FORMULA"]==form and r["HORIZON_H4"]==h and r["PERIOD"]=="HOLDOUT2022+"]
            z=sorted(z,key=lambda r:(r["DELTA_CROSS_MINUS_PRICE_BPS"] if r["DELTA_CROSS_MINUS_PRICE_BPS"] is not None else -1e99),reverse=True)
            head[form][str(h)]=z[0]
    meta={"block":"CS04","status":"PASS","holdout":"2022-01-01 onward","headlines":head,
          "contract":{"trading_or_pnl":False,"parameter_optimization":False,
                      "matched_price_only_controls":True,"feature_selection_for_trading":False}}
    (a.out/"CS04.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["CURRENCY STRENGTH CS04 — MATCHED CONTROLS","STATUS: PASS","HOLDOUT: 2022-01-01 onward","TRADING/PNL: NO","OPTIMIZATION: NO",""]
    for form in ("RAW","VOL"):
        lines.append(form+":")
        for h in H:
            x=head[form][str(h)]
            lines.append(f" H{h} BEST_DELTA={x['FEATURE']} CROSS={x['CROSS_MEAN_SIGNED_BPS']:+.4f}bps PRICE_ANALOG={x['PRICE_ANALOG_MEAN_SIGNED_BPS']:+.4f}bps DELTA={x['DELTA_CROSS_MINUS_PRICE_BPS']:+.4f}bps N={x['CROSS_N']}/{x['PRICE_ANALOG_N']}")
        lines.append("")
    (a.out/"CS04.txt").write_text("\n".join(lines)+"\n",encoding="utf-8");print("\n".join(lines))
if __name__=="__main__":main()
