#!/usr/bin/env python3
"""
CS02 — eight frozen Currency Strength features.

For both RAW and volatility-normalized EUR-vs-USD strength:
1 cross
2 post-cross separation speed (first 3 H4 bars)
3 opposing slopes of EUR and USD
4 large signed distance (>= causal rolling 75th percentile)
5 extreme divergence -> convergence (prior distance >= causal 90th percentile)
6 relative acceleration
7 leadership duration
8 breadth of external pair confirmation

All thresholds are frozen before evaluation. No trading, no PnL, no fitting.
"""
import argparse,csv,json,math
from pathlib import Path

ROLL=252
POST_CROSS=3
LEAD_MIN=6
BREADTH_MIN=0.50

def sgn(x): return 1 if x>0 else (-1 if x<0 else 0)

def qtile(xs,q):
    if not xs:return None
    z=sorted(xs);p=(len(z)-1)*q;lo=int(math.floor(p));hi=int(math.ceil(p))
    if lo==hi:return z[lo]
    return z[lo]+(z[hi]-z[lo])*(p-lo)

def fnum(r,k): return float(r[k])
def inum(r,k): return int(float(r[k]))

def build(rows,prefix):
    dk="DIFF_"+prefix; ek="EUR_"+prefix; uk="USD_"+prefix
    out=[]
    last_sign=0;since_cross=10**9;lead=0
    prev_d=None;prev_e=None;prev_u=None;prev_speed=None
    dists=[]
    for i,r in enumerate(rows):
        d=fnum(r,dk);e=fnum(r,ek);u=fnum(r,uk)
        sd=sgn(d)
        cross=0
        if last_sign and sd and sd!=last_sign:
            cross=sd; since_cross=0; lead=1
        else:
            since_cross+=1
            if sd and sd==last_sign: lead+=1
            elif sd: lead=1
            else: lead=0
        if sd:last_sign=sd

        speed=(d-prev_d) if prev_d is not None else 0.0
        de=(e-prev_e) if prev_e is not None else 0.0
        du=(u-prev_u) if prev_u is not None else 0.0
        accel=(speed-prev_speed) if prev_speed is not None else 0.0
        dist=abs(d);prev_dist=abs(prev_d) if prev_d is not None else None

        hist=dists[max(0,len(dists)-ROLL):]
        q75=qtile(hist,0.75) if len(hist)>=50 else None
        q90=qtile(hist,0.90) if len(hist)>=50 else None

        post=0.0
        if since_cross<=POST_CROSS and prev_dist is not None and dist>prev_dist:
            post=sd*(dist-prev_dist)

        opp=0.0
        if de*du<0:
            opp=de-du

        large=0.0
        if q75 is not None and dist>=q75:
            large=d

        conv=0.0
        if q90 is not None and prev_dist is not None and prev_dist>=q90 and dist<prev_dist:
            conv=-sgn(prev_d)*(prev_dist-dist)

        leadership=(sd*lead) if lead>=LEAD_MIN else 0.0
        breadth=float(r["BREADTH_SIGNED"])
        breadth_feat=breadth if abs(breadth)>=BREADTH_MIN else 0.0

        out.append({
            "TIME":inum(r,"TIME"),
            "FORMULA":prefix,
            "OWN_RET24":fnum(r,"OWN_RET24"),
            "DIFF":d,
            "F1_CROSS":float(cross),
            "F2_POSTCROSS_SEPARATION":post,
            "F3_OPPOSING_SLOPES":opp,
            "F4_LARGE_DISTANCE":large,
            "F5_EXTREME_CONVERGENCE":conv,
            "F6_ACCELERATION":accel,
            "F7_LEADERSHIP_DURATION":leadership,
            "F8_BREADTH":breadth_feat,
            "RAW_BREADTH":breadth,
            "RANK_DIFF":fnum(r,"RANK_DIFF" if prefix=="RAW" else "VOL_RANK_DIFF")
        })
        dists.append(dist)
        prev_d=d;prev_e=e;prev_u=u;prev_speed=speed
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--states",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    with a.states.open("r",encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f,delimiter=";"))
    allrows=build(rows,"RAW")+build(rows,"VOL")
    allrows.sort(key=lambda x:(x["TIME"],x["FORMULA"]))
    with (a.out/"CS02_FEATURES.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(allrows[0].keys()),delimiter=";")
        w.writeheader();w.writerows(allrows)
    counts={}
    for form in ("RAW","VOL"):
        rr=[r for r in allrows if r["FORMULA"]==form]
        counts[form]={}
        for k in ["F1_CROSS","F2_POSTCROSS_SEPARATION","F3_OPPOSING_SLOPES","F4_LARGE_DISTANCE",
                  "F5_EXTREME_CONVERGENCE","F6_ACCELERATION","F7_LEADERSHIP_DURATION","F8_BREADTH"]:
            counts[form][k]=sum(r[k]!=0 for r in rr)
    meta={"block":"CS02","status":"PASS","rows":len(allrows),"counts":counts,
          "contract":{"trading_or_pnl":False,"parameter_optimization":False,"lookahead":False,
          "rolling_percentiles_causal":True,"rolling_window_h4":ROLL,
          "post_cross_bars":POST_CROSS,"leadership_min_bars":LEAD_MIN,"breadth_min_abs":BREADTH_MIN}}
    (a.out/"CS02.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("CURRENCY STRENGTH CS02")
    print("STATUS: PASS")
    print("FEATURE_ROWS:",len(allrows))
    for form in ("RAW","VOL"): print(form,counts[form])
    print("TRADING/PNL: NO")
    print("OPTIMIZATION: NO")
if __name__=="__main__": main()
