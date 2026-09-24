#!/usr/bin/env python3
import argparse,csv,json,math,statistics,bisect
from pathlib import Path
from drummond_replay01 import read_xfbar

FIELDS=[
 "SYMBOL","STATUS","H1_M5_MATCHES","H1_M5_MED_RATIO","H1_M5_MED_POINT_DIFF","H1_M5_P95_POINT_DIFF","H1_M5_MAX_POINT_DIFF",
 "H4_H1_MATCHES","H4_H1_MED_RATIO","H4_H1_MED_POINT_DIFF","H4_H1_P95_POINT_DIFF","H4_H1_MAX_POINT_DIFF",
 "H1_POINT","M5_POINT","H4_POINT","H1_DIGITS","M5_DIGITS","H4_DIGITS","REASON"
]

def pct(a,q):
    if not a:return None
    x=sorted(a)
    if len(x)==1:return x[0]
    z=(len(x)-1)*q;i=int(z);j=min(i+1,len(x)-1);w=z-i
    return x[i]*(1-w)+x[j]*w

def fmt(x,n=10):
    return "" if x is None else f"{x:.{n}f}"

def compare(a,b,point):
    # exact-time open-to-open comparison
    bt={x[0]:x[1] for x in b}
    ratios=[];pd=[]
    for x in a:
        y=bt.get(x[0])
        if y is None or x[1]<=0 or y<=0:continue
        ratios.append(x[1]/y)
        pd.append(abs(x[1]-y)/point if point>0 else math.inf)
    return {
      "n":len(ratios),
      "med_ratio":statistics.median(ratios) if ratios else None,
      "med_pd":statistics.median(pd) if pd else None,
      "p95_pd":pct(pd,.95),"max_pd":max(pd) if pd else None
    }

def classify(c1,c2,h1h,h4h,m5h):
    reasons=[]
    for name,c in (("H1_M5",c1),("H4_H1",c2)):
        if c["n"]<10:reasons.append(name+"_TOO_FEW_MATCHES");continue
        if c["med_ratio"] is None:reasons.append(name+"_NO_RATIO");continue
        if abs(c["med_ratio"]-1.0)>0.01:
            reasons.append(name+"_SCALE_MISMATCH")
        elif c["p95_pd"] is not None and c["p95_pd"]>5.0:
            reasons.append(name+"_VALUE_MISMATCH")
    if abs(h1h["point"]-m5h["point"])>1e-15:reasons.append("H1_M5_POINT_MISMATCH")
    if abs(h1h["point"]-h4h["point"])>1e-15:reasons.append("H1_H4_POINT_MISMATCH")
    if h1h["digits"]!=m5h["digits"]:reasons.append("H1_M5_DIGITS_MISMATCH")
    if h1h["digits"]!=h4h["digits"]:reasons.append("H1_H4_DIGITS_MISMATCH")
    return ("PASS" if not reasons else "FAIL"),"|".join(reasons)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    rows=[];errs=[];skips=0
    for h1p in sorted(a.data_root.rglob("*_H1.bin")):
        sym=h1p.name[:-7]
        try:
            h4s=list(a.data_root.rglob(f"{sym}_H4.bin"));m5s=list(a.data_root.rglob(f"{sym}_M5.bin"))
            if len(h4s)==0 or len(m5s)==0:
                skips+=1;continue
            if len(h4s)!=1 or len(m5s)!=1:raise RuntimeError("duplicate TF file")
            h1h,h1=read_xfbar(h1p);h4h,h4=read_xfbar(h4s[0]);m5h,m5=read_xfbar(m5s[0])
            c1=compare(h1,m5,h1h["point"])
            c2=compare(h4,h1,h1h["point"])
            status,reason=classify(c1,c2,h1h,h4h,m5h)
            rows.append({
              "SYMBOL":sym,"STATUS":status,
              "H1_M5_MATCHES":c1["n"],"H1_M5_MED_RATIO":fmt(c1["med_ratio"],8),
              "H1_M5_MED_POINT_DIFF":fmt(c1["med_pd"],4),"H1_M5_P95_POINT_DIFF":fmt(c1["p95_pd"],4),"H1_M5_MAX_POINT_DIFF":fmt(c1["max_pd"],4),
              "H4_H1_MATCHES":c2["n"],"H4_H1_MED_RATIO":fmt(c2["med_ratio"],8),
              "H4_H1_MED_POINT_DIFF":fmt(c2["med_pd"],4),"H4_H1_P95_POINT_DIFF":fmt(c2["p95_pd"],4),"H4_H1_MAX_POINT_DIFF":fmt(c2["max_pd"],4),
              "H1_POINT":h1h["point"],"M5_POINT":m5h["point"],"H4_POINT":h4h["point"],
              "H1_DIGITS":h1h["digits"],"M5_DIGITS":m5h["digits"],"H4_DIGITS":h4h["digits"],"REASON":reason
            })
        except Exception as e:
            errs.append({"symbol":sym,"error":str(e)})
    a.out.mkdir(parents=True,exist_ok=True)
    with (a.out/"D22.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";");w.writeheader();w.writerows(rows)
    bad=[r for r in rows if r["STATUS"]!="PASS"]
    summary={
      "block":"D22","status":"PASS" if rows and not errs else "FAIL",
      "checked":len(rows),"passed":len(rows)-len(bad),"failed":len(bad),"skipped_missing_tf":skips,"errors":len(errs),
      "failed_symbols":[{"symbol":r["SYMBOL"],"reason":r["REASON"],"h1_m5_ratio":r["H1_M5_MED_RATIO"],"h4_h1_ratio":r["H4_H1_MED_RATIO"]} for r in bad],
      "gate":{
        "scale_mismatch":"abs(median open ratio - 1) > 1%",
        "value_mismatch":"p95 exact-time open difference > 5 symbol points",
        "header_point_digits_must_match":True,
        "uses_outcomes":False
      }
    }
    (a.out/"D22.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (a.out/"D22_ERR.json").write_text(json.dumps(errs,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("D22",summary["status"],"checked",len(rows),"PASS",len(rows)-len(bad),"FAIL",len(bad),"SKIP",skips,"ERR",len(errs))
    for r in bad[:50]:print("FAIL",r["SYMBOL"],r["REASON"],"H1/M5",r["H1_M5_MED_RATIO"],"H4/H1",r["H4_H1_MED_RATIO"])
    if errs:raise SystemExit(2)

if __name__=="__main__":
    main()
