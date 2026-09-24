#!/usr/bin/env python3
import argparse,csv,json
from collections import Counter,defaultdict
from pathlib import Path

POLICIES=[
 ("ALL_N20",20,"ALL"),
 ("ALL_N50",50,"ALL"),
 ("ALL_N100",100,"ALL"),
 ("PRIMARY_N20",20,"PRIMARY"),
 ("LIVE_N20",20,"LIVE"),
]
LIVE_FEATURES={
 "H1_PLDOT_SIDE_R_B","H1_LIVE_SIDE_R_B","H1_REFRESH_AT_OPEN",
 "LIVE_PATH_STATUS","LIVE_PREV_PUSH","LIVE_PREV_CROSS_STATIC",
 "LIVE_PREV_REFRESH_TOUCH","LIVE_PREV_RANGE_R_B"
}

SEL_FIELDS=[
 "POLICY","SCHEME","FOLD","FEATURE","VALUE","IS_N","IS_MEAN_R",
 "OOS_N","OOS_MEAN_R","BASE_OOS_N","BASE_OOS_MEAN_R","OOS_DELTA_R"
]
SUM_FIELDS=[
 "POLICY","SCHEME","FOLDS","SELECTED_FOLDS","OOS_N","OOS_MEAN_R",
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

def num(x):
    try:return float(x)
    except:return None

def allowed(feature,family):
    if family=="ALL":return True
    if family=="PRIMARY":return feature=="PRIMARY_SIGNAL"
    if family=="LIVE":return feature in LIVE_FEATURES
    return False

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    fv=read_csv(a.root/"D17FV.csv")
    folds=read_csv(a.root/"D17F.csv")
    d17=json.loads((a.root/"D17.json").read_text(encoding="utf-8"))
    if d17.get("status")!="PASS":raise SystemExit("D17 source not PASS")

    base={(r["SCHEME"],r["FOLD"]):r for r in folds}
    groups=defaultdict(list)
    for r in fv:groups[(r["SCHEME"],r["FOLD"])].append(r)

    selections=[]
    summaries=[]
    schemes=sorted({k[0] for k in groups})
    for pname,min_n,family in POLICIES:
        for scheme in schemes:
            picks=[]
            keys=sorted([k for k in groups if k[0]==scheme],key=lambda x:int(x[1]))
            for key in keys:
                cand=[]
                for r in groups[key]:
                    if not allowed(r["FEATURE"],family):continue
                    isn=int(r["IS_N"])
                    ism=num(r["IS_MEAN_R"])
                    if isn<min_n or ism is None:continue
                    # IMPORTANT: candidate selection uses IS fields only.
                    cand.append((ism,isn,r["FEATURE"],r["VALUE"],r))
                if not cand:continue
                cand.sort(key=lambda x:(-x[0],-x[1],x[2],x[3]))
                r=cand[0][4]
                b=base[key]
                oom=num(r["OOS_MEAN_R"]);bom=num(b["OOS_MEAN_R"])
                rec={
                  "POLICY":pname,"SCHEME":scheme,"FOLD":key[1],
                  "FEATURE":r["FEATURE"],"VALUE":r["VALUE"],
                  "IS_N":r["IS_N"],"IS_MEAN_R":r["IS_MEAN_R"],
                  "OOS_N":r["OOS_N"],"OOS_MEAN_R":r["OOS_MEAN_R"],
                  "BASE_OOS_N":b["OOS_N"],"BASE_OOS_MEAN_R":b["OOS_MEAN_R"],
                  "OOS_DELTA_R":"" if oom is None or bom is None else f"{oom-bom:.8f}"
                }
                selections.append(rec);picks.append(rec)

            valid=[x for x in picks if int(x["OOS_N"])>0 and num(x["OOS_MEAN_R"]) is not None]
            on=sum(int(x["OOS_N"]) for x in valid)
            ow=sum(int(x["OOS_N"])*float(x["OOS_MEAN_R"]) for x in valid)
            bn=sum(int(x["BASE_OOS_N"]) for x in valid)
            bw=sum(int(x["BASE_OOS_N"])*float(x["BASE_OOS_MEAN_R"]) for x in valid if num(x["BASE_OOS_MEAN_R"]) is not None)
            om=ow/on if on else None;bm=bw/bn if bn else None
            pos=sum(float(x["OOS_MEAN_R"])>0 for x in valid)
            dpos=sum(float(x["OOS_DELTA_R"])>0 for x in valid if x["OOS_DELTA_R"]!="")
            cnt=Counter(f"{x['FEATURE']}={x['VALUE']}" for x in picks)
            top=cnt.most_common(1)[0] if cnt else ("",0)
            summaries.append({
              "POLICY":pname,"SCHEME":scheme,"FOLDS":len(keys),"SELECTED_FOLDS":len(picks),
              "OOS_N":on,"OOS_MEAN_R":"" if om is None else f"{om:.8f}",
              "BASE_OOS_N":bn,"BASE_OOS_MEAN_R":"" if bm is None else f"{bm:.8f}",
              "DELTA_R":"" if om is None or bm is None else f"{om-bm:.8f}",
              "POS_OOS_FOLDS":pos,"POS_OOS_RATE":"" if not valid else f"{pos/len(valid):.8f}",
              "DELTA_POS_FOLDS":dpos,"DELTA_POS_RATE":"" if not valid else f"{dpos/len(valid):.8f}",
              "MOST_SELECTED":top[0],"MOST_SELECTED_N":top[1]
            })

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"D18.csv",SEL_FIELDS,selections)
    write_csv(a.out/"D18S.csv",SUM_FIELDS,summaries)

    overall=[]
    for pname,_,_ in POLICIES:
        rr=[x for x in summaries if x["POLICY"]==pname and x["OOS_MEAN_R"]!=""]
        if not rr:continue
        n=sum(int(x["OOS_N"]) for x in rr)
        w=sum(int(x["OOS_N"])*float(x["OOS_MEAN_R"]) for x in rr)
        bn=sum(int(x["BASE_OOS_N"]) for x in rr)
        bw=sum(int(x["BASE_OOS_N"])*float(x["BASE_OOS_MEAN_R"]) for x in rr)
        overall.append({
          "policy":pname,"schemes":len(rr),"oos_n_sum_across_schemes":n,
          "weighted_oos_mean_r":w/n if n else None,
          "weighted_base_mean_r":bw/bn if bn else None,
          "weighted_delta_r":(w/n-bw/bn) if n and bn else None,
          "positive_scheme_means":sum(float(x["OOS_MEAN_R"])>0 for x in rr),
          "positive_delta_schemes":sum(float(x["DELTA_R"])>0 for x in rr)
        })

    summary={
      "block":"D18","status":"PASS","source_run":35982263438,
      "source_events":d17["events"],"policies":overall,
      "selection_source":"IS_ONLY",
      "oos_used_for_selection":False,
      "selection_scope":"single feature=value rule per fold; no multi-feature combinations",
      "future_wait_required":False,
      "promotion_allowed":False
    }
    (a.out/"D18.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["D18 NESTED WALK-FORWARD","STATUS: PASS","SELECTION: IS ONLY","OOS USED FOR SELECTION: NO"]
    for x in overall:
        lines.append(f"{x['policy']}: meanR={x['weighted_oos_mean_r']:.8f} base={x['weighted_base_mean_r']:.8f} delta={x['weighted_delta_r']:.8f} positiveSchemes={x['positive_scheme_means']}/{x['schemes']}")
    (a.out/"D18.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
