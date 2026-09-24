#!/usr/bin/env python3
import argparse,bisect,csv,json
from collections import defaultdict,Counter
from datetime import datetime,timezone
from pathlib import Path

SCHEMES=[
 ("1M_2W",2,1),("2M_1M",4,2),("3M_1.5M",6,3),
 ("4M_2M",8,4),("5M_2.5M",10,5),("6M_3M",12,6)
]
PAIRS=[
 ("STATE_HTP","H1_STATE","H4_STATE"),
 ("STATE_ENV","H1_STATE","ENV_POS"),
 ("STATE_BLOCK","H1_STATE","BLOCK_REL"),
 ("HTP_REFRESH","HTP_ALIGNED","H1_REFRESH_AT_OPEN"),
 ("HTP_PREV_REFRESH","HTP_ALIGNED","LIVE_PREV_REFRESH_TOUCH"),
 ("HTP_DOTMODE","HTP_ALIGNED","H1_DOT_DISTANCE_MODE"),
 ("DOT_ENV","H1_DOT_DIR","ENV_POS"),
 ("DOT_BLOCK","H1_DOT_DIR","BLOCK_REL"),
 ("LIVE_PLDOT","H1_PLDOT_SIDE_R_B","H1_LIVE_SIDE_R_B"),
 ("LIVE_HTP","LIVE_PREV_PUSH","H4_DOT_DIR"),
 ("CLUSTERS","SUPPORT_CLUSTER","RESIST_CLUSTER"),
 ("BLOCK_HTP","BLOCK_STRONG","HTP_ALIGNED"),
 ("PRIMARY_ENV","PRIMARY_SIGNAL","ENV_POS"),
 ("PRIMARY_BLOCK","PRIMARY_SIGNAL","BLOCK_REL"),
]
POLICIES=[("P20",20),("P50",50),("P100",100)]
SIDES=["LONG","SHORT"]

SEL_FIELDS=[
 "POLICY","SIDE","SCHEME","FOLD","PAIR","F1","V1","F2","V2",
 "IS_N","IS_MEAN_R","OOS_N","OOS_MEAN_R","BASE_OOS_N","BASE_OOS_MEAN_R","DELTA_R"
]
SUM_FIELDS=[
 "POLICY","SIDE","SCHEME","FOLDS","SELECTED_FOLDS","OOS_N","OOS_MEAN_R",
 "BASE_OOS_N","BASE_OOS_MEAN_R","DELTA_R","POS_OOS_FOLDS","POS_OOS_RATE",
 "DELTA_POS_FOLDS","DELTA_POS_RATE","MOST_SELECTED","MOST_SELECTED_N"
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

def bucket(v):
    try:x=float(v)
    except:return "NA"
    if x<-1:return "<-1"
    if x<-.5:return "-1..-0.5"
    if x<0:return "-0.5..0"
    if x<.5:return "0..0.5"
    if x<1:return "0.5..1"
    return ">=1"

def val(r,f):
    if f=="H1_PLDOT_SIDE_R_B":return bucket(r.get("H1_PLDOT_SIDE_R",""))
    if f=="H1_LIVE_SIDE_R_B":return bucket(r.get("H1_LIVE_SIDE_R",""))
    return r.get(f,"") or "EMPTY"

def metric(rows):
    if not rows:return (0,None)
    vals=[float(r["LEVEL_R"]) for r in rows]
    return len(vals),sum(vals)/len(vals)

def grouped(rows,f1,f2):
    d=defaultdict(list)
    for r in rows:d[(val(r,f1),val(r,f2))].append(r)
    return d

def fmt(x):
    return "" if x is None else f"{x:.8f}"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    files=sorted(a.root.rglob("D17.csv"))
    if len(files)!=7:raise SystemExit(f"D19 expected 7 D17 event shards, got {len(files)}")
    rows=[];seen=set()
    for p in files:
        for r in read_csv(p):
            k=(r["SYMBOL"],r["SIDE"],r["SIGNAL_ID"])
            if k in seen:raise SystemExit(f"duplicate {k}")
            seen.add(k);rows.append(r)
    rows.sort(key=lambda r:(int(r["ENTRY_TIME"]),r["SYMBOL"],r["SIDE"],r["SIGNAL_ID"]))
    if not rows:raise SystemExit("no D17 rows")

    mn=int(rows[0]["ENTRY_TIME"]);mx=int(rows[-1]["ENTRY_TIME"])
    anchor=datetime(datetime.fromtimestamp(mn,tz=timezone.utc).year,1,1,tzinfo=timezone.utc)
    bounds=[anchor]
    while int(bounds[-1].timestamp())<=mx:bounds.append(next_half(bounds[-1]))
    bt=[int(x.timestamp()) for x in bounds];periods=len(bt)-1
    byp=defaultdict(list)
    for r in rows:
        k=bisect.bisect_right(bt,int(r["ENTRY_TIME"]))-1
        if 0<=k<periods:byp[k].append(r)

    selected=[];summ=[]
    for pname,min_n in POLICIES:
      for side in SIDES:
       for scheme,isu,ou in SCHEMES:
        start=0;fold=0;picks=[]
        while start+isu+ou<=periods:
            ie=start+isu;oe=ie+ou;fold+=1
            ir=[];orr=[]
            for k in range(start,ie):ir.extend(r for r in byp.get(k,[]) if r["SIDE"]==side)
            for k in range(ie,oe):orr.extend(r for r in byp.get(k,[]) if r["SIDE"]==side)
            bn,bm=metric(orr)

            candidates=[]
            cache={}
            for pair,f1,f2 in PAIRS:
                gi=grouped(ir,f1,f2);go=grouped(orr,f1,f2)
                cache[pair]=(gi,go,f1,f2)
                for key,rr in gi.items():
                    n,m=metric(rr)
                    if n>=min_n and m is not None:
                        # Selection uses IS n and IS mean only.
                        candidates.append((m,n,pair,key[0],key[1]))
            if not candidates:
                start+=ou;continue
            candidates.sort(key=lambda x:(-x[0],-x[1],x[2],x[3],x[4]))
            ism,isn,pair,v1,v2=candidates[0]
            gi,go,f1,f2=cache[pair]
            oo=go.get((v1,v2),[])
            on,om=metric(oo)
            rec={
              "POLICY":pname,"SIDE":side,"SCHEME":scheme,"FOLD":fold,
              "PAIR":pair,"F1":f1,"V1":v1,"F2":f2,"V2":v2,
              "IS_N":isn,"IS_MEAN_R":fmt(ism),"OOS_N":on,"OOS_MEAN_R":fmt(om),
              "BASE_OOS_N":bn,"BASE_OOS_MEAN_R":fmt(bm),
              "DELTA_R":fmt(om-bm) if om is not None and bm is not None else ""
            }
            selected.append(rec);picks.append(rec)
            start+=ou

        valid=[x for x in picks if int(x["OOS_N"])>0 and x["OOS_MEAN_R"]!=""]
        on=sum(int(x["OOS_N"]) for x in valid)
        om=sum(int(x["OOS_N"])*float(x["OOS_MEAN_R"]) for x in valid)/on if on else None
        bn=sum(int(x["BASE_OOS_N"]) for x in valid)
        bm=sum(int(x["BASE_OOS_N"])*float(x["BASE_OOS_MEAN_R"]) for x in valid)/bn if bn else None
        pos=sum(float(x["OOS_MEAN_R"])>0 for x in valid)
        dpos=sum(float(x["DELTA_R"])>0 for x in valid if x["DELTA_R"]!="")
        c=Counter(f"{x['PAIR']}:{x['V1']}|{x['V2']}" for x in picks)
        top=c.most_common(1)[0] if c else ("",0)
        summ.append({
          "POLICY":pname,"SIDE":side,"SCHEME":scheme,"FOLDS":fold,"SELECTED_FOLDS":len(picks),
          "OOS_N":on,"OOS_MEAN_R":fmt(om),"BASE_OOS_N":bn,"BASE_OOS_MEAN_R":fmt(bm),
          "DELTA_R":fmt(om-bm) if om is not None and bm is not None else "",
          "POS_OOS_FOLDS":pos,"POS_OOS_RATE":fmt(pos/len(valid)) if valid else "",
          "DELTA_POS_FOLDS":dpos,"DELTA_POS_RATE":fmt(dpos/len(valid)) if valid else "",
          "MOST_SELECTED":top[0],"MOST_SELECTED_N":top[1]
        })

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D19.csv",SEL_FIELDS,selected)
    write_csv(a.out/"D19S.csv",SUM_FIELDS,summ)

    overall=[]
    for pname,_ in POLICIES:
      for side in SIDES:
        rr=[x for x in summ if x["POLICY"]==pname and x["SIDE"]==side and x["OOS_MEAN_R"]!=""]
        n=sum(int(x["OOS_N"]) for x in rr)
        bn=sum(int(x["BASE_OOS_N"]) for x in rr)
        om=sum(int(x["OOS_N"])*float(x["OOS_MEAN_R"]) for x in rr)/n if n else None
        bm=sum(int(x["BASE_OOS_N"])*float(x["BASE_OOS_MEAN_R"]) for x in rr)/bn if bn else None
        overall.append({
          "policy":pname,"side":side,"schemes":len(rr),"oos_n_sum_across_schemes":n,
          "oos_mean_r":om,"base_mean_r":bm,"delta_r":om-bm if om is not None and bm is not None else None,
          "positive_schemes":sum(float(x["OOS_MEAN_R"])>0 for x in rr),
          "positive_delta_schemes":sum(float(x["DELTA_R"])>0 for x in rr)
        })

    summary={
      "block":"D19","status":"PASS","source_run":35982263438,"source_events":len(rows),
      "pairs":[x[0] for x in PAIRS],"policies":overall,
      "selection_source":"IS_ONLY","oos_used_for_selection":False,
      "side_separated":True,"future_wait_required":False,"promotion_allowed":False
    }
    (a.out/"D19.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["D19 AUTHOR PAIRS","STATUS: PASS","SELECTION: IS ONLY","SIDE: SEPARATE"]
    for x in overall:
        lines.append(f"{x['policy']} {x['side']}: meanR={x['oos_mean_r']:.8f} base={x['base_mean_r']:.8f} delta={x['delta_r']:.8f} positiveSchemes={x['positive_schemes']}/{x['schemes']}")
    (a.out/"D19.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
