#!/usr/bin/env python3
"""
CS03 — incremental-information audit for the frozen CS02 feature set.

Two tests:
A) Event-direction audit: on exactly the same timestamps, compare each external
   currency-strength signal with a price-only EURUSD 24h-momentum baseline.
B) Fixed chronological holdout: OLS fitted before 2022-01-01, evaluated from
   2022 onward. Compare price-only vs price+one feature vs price+all 8 features.

No threshold fitting, no hyperparameter tuning, no trading/PnL.
"""
import argparse,csv,json,math,statistics
from datetime import datetime,timezone
from pathlib import Path
from drummond_replay01 import read_xfbar

FEATURES=["F1_CROSS","F2_POSTCROSS_SEPARATION","F3_OPPOSING_SLOPES",
          "F4_LARGE_DISTANCE","F5_EXTREME_CONVERGENCE","F6_ACCELERATION",
          "F7_LEADERSHIP_DURATION","F8_BREADTH"]
H=[1,3,6,18]
SPLIT_TS=int(datetime(2022,1,1,tzinfo=timezone.utc).timestamp())

def sgn(x): return 1 if x>0 else (-1 if x<0 else 0)
def avg(x): return statistics.fmean(x) if x else None
def corr(a,b):
    if len(a)<2:return None
    ma=avg(a);mb=avg(b)
    sa=sum((x-ma)*(x-ma) for x in a);sb=sum((x-mb)*(x-mb) for x in b)
    if sa<=0 or sb<=0:return 0.0
    return sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(sa*sb)

def solve(A,b):
    n=len(b);m=[list(A[i])+[b[i]] for i in range(n)]
    for col in range(n):
        piv=max(range(col,n),key=lambda r:abs(m[r][col]))
        if abs(m[piv][col])<1e-12:
            m[piv][col]+=1e-10
        m[col],m[piv]=m[piv],m[col]
        d=m[col][col]
        for j in range(col,n+1):m[col][j]/=d
        for r in range(n):
            if r==col:continue
            z=m[r][col]
            if z==0:continue
            for j in range(col,n+1):m[r][j]-=z*m[col][j]
    return [m[i][n] for i in range(n)]

def fit_ols(train,keys,ykey):
    means={k:avg([r[k] for r in train]) for k in keys}
    stds={}
    for k in keys:
        v=[r[k] for r in train];mu=means[k]
        sd=math.sqrt(sum((x-mu)**2 for x in v)/max(1,len(v)-1))
        stds[k]=sd if sd>1e-15 else 1.0
    X=[];y=[]
    for r in train:
        X.append([1.0]+[(r[k]-means[k])/stds[k] for k in keys]);y.append(r[ykey])
    p=len(keys)+1
    xtx=[[0.0]*p for _ in range(p)];xty=[0.0]*p
    for x,yy in zip(X,y):
        for i in range(p):
            xty[i]+=x[i]*yy
            for j in range(p):xtx[i][j]+=x[i]*x[j]
    for i in range(1,p):xtx[i][i]+=1e-12
    beta=solve(xtx,xty)
    return beta,means,stds,avg(y)

def predict(rows,keys,beta,means,stds):
    out=[]
    for r in rows:
        x=[1.0]+[(r[k]-means[k])/stds[k] for k in keys]
        out.append(sum(a*b for a,b in zip(beta,x)))
    return out

def eval_model(train,test,keys,ykey):
    beta,means,stds,train_y_mean=fit_ols(train,keys,ykey)
    pred=predict(test,keys,beta,means,stds); y=[r[ykey] for r in test]
    err=[p-v for p,v in zip(pred,y)]
    sse=sum(e*e for e in err)
    den=sum((v-train_y_mean)**2 for v in y)
    return {
      "N_TRAIN":len(train),"N_TEST":len(test),
      "RMSE_BPS":math.sqrt(sse/len(y))*10000,
      "MAE_BPS":avg([abs(e) for e in err])*10000,
      "CORR":corr(pred,y),
      "SIGN_ACCURACY":sum(sgn(p)==sgn(v) and sgn(v)!=0 for p,v in zip(pred,y))/len(y),
      "R2_TEST":1-sse/den if den>0 else None
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--features",type=Path,required=True)
    ap.add_argument("--eurusd",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)

    with a.features.open("r",encoding="utf-8-sig",newline="") as f:
        raw=list(csv.DictReader(f,delimiter=";"))
    forms={}
    for form in ("RAW","VOL"):
        forms[form]=[]
        for r in raw:
            if r["FORMULA"]!=form:continue
            z={k:float(r[k]) for k in ["OWN_RET24"]+FEATURES}
            z["TIME"]=int(float(r["TIME"]))
            forms[form].append(z)
        forms[form].sort(key=lambda x:x["TIME"])

    hdr,bars=read_xfbar(a.eurusd)
    close={int(b[0]):float(b[4]) for b in bars}
    event=[];hold=[]
    for form,rows in forms.items():
        times=[r["TIME"] for r in rows]
        enriched=[]
        for i,r in enumerate(rows):
            if any(i+h>=len(rows) for h in H):continue
            z=dict(r)
            ok=True
            for h in H:
                t2=times[i+h]
                if r["TIME"] not in close or t2 not in close:ok=False;break
                z["Y"+str(h)]=math.log(close[t2]/close[r["TIME"]])
            if ok:enriched.append(z)

        for h in H:
            yk="Y"+str(h)
            for feat in FEATURES:
                rr=[r for r in enriched if r[feat]!=0]
                fs=[sgn(r[feat])*r[yk]*10000 for r in rr]
                os=[sgn(r["OWN_RET24"])*r[yk]*10000 for r in rr if sgn(r["OWN_RET24"])!=0]
                # own list aligns because own zero is essentially absent; recompute paired deltas safely.
                paired=[(sgn(r[feat])*r[yk]*10000,sgn(r["OWN_RET24"])*r[yk]*10000)
                        for r in rr if sgn(r["OWN_RET24"])!=0]
                event.append({
                  "FORMULA":form,"HORIZON_H4":h,"FEATURE":feat,"N_EVENTS":len(rr),
                  "FEATURE_MEAN_SIGNED_BPS":avg(fs),
                  "FEATURE_ACCURACY":sum(x>0 for x in fs)/len(fs) if fs else None,
                  "OWN_SAME_EVENTS_MEAN_SIGNED_BPS":avg([b for _,b in paired]),
                  "OWN_SAME_EVENTS_ACCURACY":sum(b>0 for _,b in paired)/len(paired) if paired else None,
                  "DELTA_FEATURE_MINUS_OWN_BPS":(
                    avg([x-b for x,b in paired]) if paired else None)
                })

            train=[r for r in enriched if r["TIME"]<SPLIT_TS]
            test=[r for r in enriched if r["TIME"]>=SPLIT_TS]
            base=eval_model(train,test,["OWN_RET24"],yk)
            hold.append({"FORMULA":form,"HORIZON_H4":h,"MODEL":"PRICE_ONLY",
                         "ADDED_FEATURE":"",**base})
            for feat in FEATURES:
                m=eval_model(train,test,["OWN_RET24",feat],yk)
                hold.append({"FORMULA":form,"HORIZON_H4":h,"MODEL":"PRICE_PLUS_ONE",
                             "ADDED_FEATURE":feat,**m,
                             "DELTA_RMSE_VS_PRICE":m["RMSE_BPS"]-base["RMSE_BPS"],
                             "DELTA_R2_VS_PRICE":m["R2_TEST"]-base["R2_TEST"],
                             "DELTA_SIGN_ACC_VS_PRICE":m["SIGN_ACCURACY"]-base["SIGN_ACCURACY"]})
            m=eval_model(train,test,["OWN_RET24"]+FEATURES,yk)
            hold.append({"FORMULA":form,"HORIZON_H4":h,"MODEL":"PRICE_PLUS_ALL8",
                         "ADDED_FEATURE":"ALL8",**m,
                         "DELTA_RMSE_VS_PRICE":m["RMSE_BPS"]-base["RMSE_BPS"],
                         "DELTA_R2_VS_PRICE":m["R2_TEST"]-base["R2_TEST"],
                         "DELTA_SIGN_ACC_VS_PRICE":m["SIGN_ACCURACY"]-base["SIGN_ACCURACY"]})

    def write(name,data):
        keys=[]
        for r in data:
            for k in r:
                if k not in keys:keys.append(k)
        with (a.out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=keys,delimiter=";",extrasaction="ignore")
            w.writeheader();w.writerows(data)
    write("CS03_EVENT_AUDIT.csv",event);write("CS03_HOLDOUT.csv",hold)

    best={}
    for form in ("RAW","VOL"):
        best[form]={}
        for h in H:
            rr=[r for r in hold if r["FORMULA"]==form and r["HORIZON_H4"]==h and r["MODEL"]=="PRICE_PLUS_ONE"]
            rr=sorted(rr,key=lambda r:r["DELTA_R2_VS_PRICE"],reverse=True)
            best[form][str(h)]=rr[0] if rr else None

    meta={"block":"CS03","status":"PASS","split_utc":"2022-01-01",
          "best_single_feature_by_holdout_r2":best,
          "contract":{"trading_or_pnl":False,"parameter_optimization":False,
          "fixed_temporal_holdout":True,"baseline":"EURUSD own 24h return","models":"unregularized OLS"}}
    (a.out/"CS03.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    lines=["CURRENCY STRENGTH CS03 — INCREMENTAL INFORMATION AUDIT","STATUS: PASS",
           "HOLDOUT: 2022-01-01 onward","TRADING/PNL: NO","OPTIMIZATION: NO",""]
    for form in ("RAW","VOL"):
        lines.append(form+":")
        for h in H:
            b=next(r for r in hold if r["FORMULA"]==form and r["HORIZON_H4"]==h and r["MODEL"]=="PRICE_ONLY")
            full=next(r for r in hold if r["FORMULA"]==form and r["HORIZON_H4"]==h and r["MODEL"]=="PRICE_PLUS_ALL8")
            one=best[form][str(h)]
            lines.append(f" H{h}: PRICE R2={b['R2_TEST']:+.6f} RMSE={b['RMSE_BPS']:.4f} ACC={b['SIGN_ACCURACY']:.6f}")
            lines.append(f"     ALL8 R2={full['R2_TEST']:+.6f} dR2={full['DELTA_R2_VS_PRICE']:+.6f} dRMSE={full['DELTA_RMSE_VS_PRICE']:+.4f} dACC={full['DELTA_SIGN_ACC_VS_PRICE']:+.6f}")
            lines.append(f"     BEST1={one['ADDED_FEATURE']} dR2={one['DELTA_R2_VS_PRICE']:+.6f} dRMSE={one['DELTA_RMSE_VS_PRICE']:+.4f} dACC={one['DELTA_SIGN_ACC_VS_PRICE']:+.6f}")
        lines.append("")
    (a.out/"CS03.txt").write_text("\n".join(lines)+"\n",encoding="utf-8");print("\n".join(lines))
if __name__=="__main__": main()
