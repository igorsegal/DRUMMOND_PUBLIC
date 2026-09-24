#!/usr/bin/env python3
import argparse,bisect,csv,json,statistics
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

SCHEMES=[
 ("1M_2W",2,1),
 ("2M_1M",4,2),
 ("3M_1.5M",6,3),
 ("4M_2M",8,4),
 ("5M_2.5M",10,5),
 ("6M_3M",12,6),
]

BASE_FEATURES=[
 "SIDE","H1_STATE","H4_STATE","H1_DOT_DIR","H4_DOT_DIR","HTP_ALIGNED",
 "H1_REFRESH_AT_OPEN","H1_DOT_DISTANCE_MODE","H1_DOT_IN_RANGE",
 "SUPPORT_CLUSTER","RESIST_CLUSTER","ENV_POS","BLOCK_REL","BLOCK_STRONG",
 "POWER_UP","POWER_DOWN","EXHAUST_UP","EXHAUST_DOWN","DOTTED_UP","DOTTED_DOWN",
 "PRIMARY_SIGNAL","LIVE_PATH_STATUS","LIVE_PREV_PUSH","LIVE_PREV_CROSS_STATIC",
 "LIVE_PREV_REFRESH_TOUCH",
 "L51_UP","L51_DOWN","L52_UP","L52_DOWN","L53_UP","L53_DOWN",
 "L59_UP","L59_DOWN","L11_FROM_LOW","L11_FROM_HIGH",
 "L61_UP","L65_DOWN","L61_DOWN","L65_UP","L67_UP","L67_DOWN","L66_UP","L66_DOWN"
]
DERIVED=["H1_PLDOT_SIDE_R_B","H1_LIVE_SIDE_R_B","LIVE_PREV_RANGE_R_B"]
FEATURES=BASE_FEATURES+DERIVED

FOLD_FIELDS=[
 "SCHEME","FOLD","IS_START","IS_END","OOS_START","OOS_END",
 "IS_N","IS_TP","IS_SL","IS_MEAN_R","OOS_N","OOS_TP","OOS_SL","OOS_MEAN_R"
]
FV_FIELDS=[
 "SCHEME","FOLD","FEATURE","VALUE",
 "IS_N","IS_TP","IS_SL","IS_MEAN_R",
 "OOS_N","OOS_TP","OOS_SL","OOS_MEAN_R","TRANSITION"
]
A_FIELDS=[
 "SCHEME","FEATURE","VALUE","OOS_N","OOS_TP","OOS_SL","OOS_MEAN_R",
 "OOS_FOLDS","POS_OOS_FOLDS","POS_OOS_RATE","N20_FOLDS","N20_POS","N20_POS_RATE",
 "IS_POS_OOS_POS","IS_POS_OOS_NONPOS","IS_NONPOS_OOS_POS","IS_NONPOS_OOS_NONPOS"
]

def read_csv(p):
    with Path(p).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(p,fields,rows):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";");w.writeheader();w.writerows(rows)

def next_half(dt):
    if dt.day==1:return datetime(dt.year,dt.month,16,tzinfo=timezone.utc)
    if dt.month==12:return datetime(dt.year+1,1,1,tzinfo=timezone.utc)
    return datetime(dt.year,dt.month+1,1,tzinfo=timezone.utc)

def metric(rows):
    if not rows:return {"n":0,"tp":0,"sl":0,"mean":None}
    tp=sum(r["OUTCOME"]=="TP" for r in rows);sl=sum(r["OUTCOME"]=="SL" for r in rows)
    vals=[float(r["LEVEL_R"]) for r in rows]
    return {"n":len(rows),"tp":tp,"sl":sl,"mean":sum(vals)/len(vals)}

def fmt(x):
    return "" if x is None else f"{x:.8f}"

def sign(x):
    if x is None:return "EMPTY"
    return "POS" if x>0 else "NONPOS"

def bucket(v):
    try:x=float(v)
    except:return "NA"
    if x < -1:return "<-1"
    if x < -.5:return "-1..-0.5"
    if x < 0:return "-0.5..0"
    if x < .5:return "0..0.5"
    if x < 1:return "0.5..1"
    return ">=1"

def range_bucket(v):
    try:x=float(v)
    except:return "NA"
    if x<.1:return "<0.1"
    if x<.25:return "0.1..0.25"
    if x<.5:return "0.25..0.5"
    if x<1:return "0.5..1"
    return ">=1"

def fval(r,f):
    if f=="H1_PLDOT_SIDE_R_B":return bucket(r.get("H1_PLDOT_SIDE_R",""))
    if f=="H1_LIVE_SIDE_R_B":return bucket(r.get("H1_LIVE_SIDE_R",""))
    if f=="LIVE_PREV_RANGE_R_B":return range_bucket(r.get("LIVE_PREV_RANGE_R",""))
    return r.get(f,"") or "EMPTY"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    csvs=sorted(a.root.rglob("D17.csv"))
    sums=sorted(a.root.rglob("D17.json"))
    if len(csvs)!=7 or len(sums)!=7:
        raise SystemExit(f"D17 aggregate expected 7 shards, got csv={len(csvs)} json={len(sums)}")
    rows=[];seen=set();longs=shorts=0
    live=Counter()
    for p in sums:
        s=json.loads(p.read_text(encoding="utf-8"))
        if s.get("status")!="PASS" or s.get("errors")!=0 or s.get("causality",{}).get("future_m5_used"):
            raise SystemExit(f"bad D17 shard {p}")
        longs+=int(s["long"]);shorts+=int(s["short"])
        live.update(s.get("live_path_status",{}))
    for p in csvs:
        for r in read_csv(p):
            k=(r["SYMBOL"],r["SIDE"],r["SIGNAL_ID"])
            if k in seen:raise SystemExit(f"duplicate event {k}")
            seen.add(k);rows.append(r)
    rows.sort(key=lambda r:(int(r["ENTRY_TIME"]),r["SYMBOL"].casefold(),r["SIDE"],r["SIGNAL_ID"]))
    if not rows:raise SystemExit("no D17 events")

    min_ts=int(rows[0]["ENTRY_TIME"]);max_ts=int(rows[-1]["ENTRY_TIME"])
    y=datetime.fromtimestamp(min_ts,tz=timezone.utc).year
    anchor=datetime(y,1,1,tzinfo=timezone.utc)
    bounds=[anchor]
    while int(bounds[-1].timestamp())<=max_ts:bounds.append(next_half(bounds[-1]))
    bt=[int(x.timestamp()) for x in bounds];periods=len(bt)-1
    byp=defaultdict(list)
    for r in rows:
        k=bisect.bisect_right(bt,int(r["ENTRY_TIME"]))-1
        if 0<=k<periods:byp[k].append(r)

    folds=[];fv=[];agg=defaultdict(list)
    scheme_summary={}
    for name,isu,ou in SCHEMES:
        start=0;fold=0;scheme_oos=[]
        while start+isu+ou<=periods:
            ie=start+isu;oe=ie+ou
            ir=[];orr=[]
            for k in range(start,ie):ir.extend(byp.get(k,[]))
            for k in range(ie,oe):orr.extend(byp.get(k,[]))
            im=metric(ir);om=metric(orr);fold+=1
            folds.append({
              "SCHEME":name,"FOLD":fold,"IS_START":bounds[start].strftime("%Y-%m-%d"),
              "IS_END":bounds[ie].strftime("%Y-%m-%d"),"OOS_START":bounds[ie].strftime("%Y-%m-%d"),
              "OOS_END":bounds[oe].strftime("%Y-%m-%d"),
              "IS_N":im["n"],"IS_TP":im["tp"],"IS_SL":im["sl"],"IS_MEAN_R":fmt(im["mean"]),
              "OOS_N":om["n"],"OOS_TP":om["tp"],"OOS_SL":om["sl"],"OOS_MEAN_R":fmt(om["mean"])
            })
            scheme_oos.extend(orr)

            for f in FEATURES:
                vals={fval(x,f) for x in ir}|{fval(x,f) for x in orr}
                for v in vals:
                    ii=[x for x in ir if fval(x,f)==v];oo=[x for x in orr if fval(x,f)==v]
                    mi=metric(ii);mo=metric(oo)
                    tr=f"{sign(mi['mean'])}->{sign(mo['mean'])}"
                    rec={
                      "SCHEME":name,"FOLD":fold,"FEATURE":f,"VALUE":v,
                      "IS_N":mi["n"],"IS_TP":mi["tp"],"IS_SL":mi["sl"],"IS_MEAN_R":fmt(mi["mean"]),
                      "OOS_N":mo["n"],"OOS_TP":mo["tp"],"OOS_SL":mo["sl"],"OOS_MEAN_R":fmt(mo["mean"]),
                      "TRANSITION":tr
                    }
                    fv.append(rec);agg[(name,f,v)].append(rec)
            start+=ou

        sm=metric(scheme_oos)
        scheme_summary[name]={"folds":fold,"oos_n":sm["n"],"oos_mean_r":sm["mean"]}

    ar=[]
    for (scheme,f,v),items in sorted(agg.items()):
        non=[x for x in items if int(x["OOS_N"])>0]
        n20=[x for x in non if int(x["OOS_N"])>=20]
        total_n=sum(int(x["OOS_N"]) for x in non)
        tp=sum(int(x["OOS_TP"]) for x in non);sl=sum(int(x["OOS_SL"]) for x in non)
        weighted=sum(float(x["OOS_MEAN_R"])*int(x["OOS_N"]) for x in non if x["OOS_MEAN_R"])
        mean=weighted/total_n if total_n else None
        pos=sum(float(x["OOS_MEAN_R"])>0 for x in non if x["OOS_MEAN_R"])
        n20pos=sum(float(x["OOS_MEAN_R"])>0 for x in n20 if x["OOS_MEAN_R"])
        tr=Counter(x["TRANSITION"] for x in non)
        ar.append({
          "SCHEME":scheme,"FEATURE":f,"VALUE":v,"OOS_N":total_n,"OOS_TP":tp,"OOS_SL":sl,
          "OOS_MEAN_R":fmt(mean),"OOS_FOLDS":len(non),"POS_OOS_FOLDS":pos,
          "POS_OOS_RATE":fmt(pos/len(non) if non else None),
          "N20_FOLDS":len(n20),"N20_POS":n20pos,"N20_POS_RATE":fmt(n20pos/len(n20) if n20 else None),
          "IS_POS_OOS_POS":tr["POS->POS"],"IS_POS_OOS_NONPOS":tr["POS->NONPOS"],
          "IS_NONPOS_OOS_POS":tr["NONPOS->POS"],"IS_NONPOS_OOS_NONPOS":tr["NONPOS->NONPOS"]
        })

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D17F.csv",FOLD_FIELDS,folds)
    write_csv(a.out/"D17FV.csv",FV_FIELDS,fv)
    write_csv(a.out/"D17A.csv",A_FIELDS,ar)
    full=metric(rows)
    robust_cells=[x for x in ar if int(x["OOS_N"])>=100 and int(x["OOS_FOLDS"])>=3]
    summary={
      "block":"D17","status":"PASS","dataset_id":"DRUMMOND_CANONICAL_8E9A1D784E3893D9",
      "events":len(rows),"long":longs,"short":shorts,
      "first_event_utc":datetime.fromtimestamp(min_ts,tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
      "last_event_utc":datetime.fromtimestamp(max_ts,tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
      "full_mean_r":full["mean"],"features":FEATURES,"feature_count":len(FEATURES),
      "six_schemes":scheme_summary,"feature_value_cells":len(ar),
      "cells_n100_folds3":len(robust_cells),
      "live_path_status":dict(live),
      "selection_or_optimization_performed":False,
      "future_wait_required":False,
      "source_gaps":["Closed 5/1","Closed 5/9","Jaws 5/9"],
      "envelope_status":"RECOVERED_PROXY"
    }
    (a.out/"D17.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=[
      "D17 AUTHOR HISTORY ATLAS","STATUS: PASS",
      f"EVENTS LONG/SHORT/TOTAL: {longs}/{shorts}/{len(rows)}",
      f"HISTORY: {summary['first_event_utc']} -> {summary['last_event_utc']}",
      f"FEATURES: {len(FEATURES)}",
      f"FULL MEAN_R: {full['mean']:.8f}",
      f"FEATURE-VALUE CELLS: {len(ar)}",
      f"N>=100 & >=3 OOS FOLDS CELLS: {len(robust_cells)}",
      "SELECTION/OPTIMIZATION: NO",
      "FUTURE WAIT: NO"
    ]
    for n in SCHEMES:
        x=scheme_summary[n[0]]
        lines.append(f"{n[0]} folds={x['folds']} OOS_N={x['oos_n']} meanR={x['oos_mean_r']:.8f}" if x["oos_mean_r"] is not None else f"{n[0]} EMPTY")
    (a.out/"D17.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
