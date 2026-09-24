#!/usr/bin/env python3
# D23 — recovered Drummond energy-zone geometry.
# This module contains no trading outcomes and no parameter fitting.

from D17 import line_features,envelope_proxy,env_pos,static_dot

NEAR_SUP=("L11_FROM_LOW","L52_UP","L59_UP")
NEAR_RES=("L11_FROM_HIGH","L52_DOWN","L59_DOWN")
FAR_SUP=("L52_UP","L59_UP")
FAR_RES=("L52_DOWN","L59_DOWN")

def _vals(vals,names,pred):
    return [vals[n] for n in names if n in vals and vals[n]>0 and pred(vals[n])]

def zones(bars,idx,point,price):
    lf,vals,sup_n,res_n=line_features(bars,idx,point)
    ns=_vals(vals,NEAR_SUP,lambda x:x<price)
    nr=_vals(vals,NEAR_RES,lambda x:x>price)
    fs=_vals(vals,FAR_SUP,lambda x:x<price)
    fr=_vals(vals,FAR_RES,lambda x:x>price)
    return {
      "near_sup":max(ns) if ns else None,
      "near_res":min(nr) if nr else None,
      "far_sup_low":min(fs) if fs else None,
      "far_sup_high":max(fs) if fs else None,
      "far_res_low":min(fr) if fr else None,
      "far_res_high":max(fr) if fr else None,
      "lf":lf,"vals":vals,"sup_n":sup_n,"res_n":res_n
    }

def lesson16_map(bars,idx,point):
    # Uses the project's explicitly labeled RECOVERED_PROXY ET/EB only to
    # reproduce the recovered Lesson-16 placement table. It must remain
    # tagged proxy until the exact primary ET/EB numerical formula is recovered.
    eb,et=envelope_proxy(bars,idx)
    pl=static_dot(bars,idx)
    if eb is None or et is None or pl is None:return None
    c1=bars[idx-1][4]
    z=zones(bars,idx,point,c1)
    out={
      "position":None,"near_support":None,"near_resistance":None,
      "far_support":None,"far_resistance":None,
      "envelope_status":"RECOVERED_PROXY",
      "energy_rule_status":"RECOVERED_LESSON16"
    }
    if c1>et:
        out["position"]="ABOVE_ET"
        out["near_support"]=(min(et,pl),max(et,pl))
        cand=[z["vals"][n] for n in NEAR_RES if n in z["vals"]]
        if cand:out["near_resistance"]=(min(cand),max(cand))
    elif c1>=pl:
        out["position"]="ET_TO_PL"
        out["near_support"]=(min(pl,eb),max(pl,eb))
        out["near_resistance"]=(et,et)
    elif c1>=eb:
        out["position"]="PL_TO_EB"
        out["near_support"]=(eb,eb)
        out["near_resistance"]=(min(pl,et),max(pl,et))
    else:
        out["position"]="BELOW_EB"
        fs=[z["vals"][n] for n in FAR_SUP if n in z["vals"]]
        if fs:out["far_support"]=(min(fs),max(fs))
        out["near_resistance"]=(min(eb,pl),max(eb,pl))
    return out

def stop_further_out(bars,idx,point,entry,direction):
    z=zones(bars,idx,point,entry)
    if direction>0 and z["far_sup_low"] is not None:
        return z["far_sup_low"]-point
    if direction<0 and z["far_res_high"] is not None:
        return z["far_res_high"]+point
    return None

def nearby_target(bars,idx,point,entry,direction):
    m=lesson16_map(bars,idx,point)
    if m is None:return None
    zone=m["near_resistance"] if direction>0 else m["near_support"]
    if zone is None:return None
    if direction>0:
        vals=[v for v in zone if v>entry+point]
        return min(vals) if vals else None
    vals=[v for v in zone if v<entry-point]
    return max(vals) if vals else None

def further_target(bars,idx,point,entry,direction):
    z=zones(bars,idx,point,entry)
    if direction>0:
        vals=[v for v in (z["far_res_low"],z["far_res_high"]) if v is not None and v>entry+point]
        return max(vals) if vals else None
    vals=[v for v in (z["far_sup_low"],z["far_sup_high"]) if v is not None and v<entry-point]
    return min(vals) if vals else None

def selftest():
    # Contract-level test: Further Out family is frozen to 5/2 + 5/9 only.
    assert FAR_SUP==("L52_UP","L59_UP")
    assert FAR_RES==("L52_DOWN","L59_DOWN")
    forbidden={"L51_UP","L53_UP","L11_FROM_LOW","L61_UP","L65_UP","L67_UP","L66_UP",
               "L51_DOWN","L53_DOWN","L11_FROM_HIGH","L61_DOWN","L65_DOWN","L67_DOWN","L66_DOWN"}
    assert not (set(FAR_SUP+FAR_RES)&forbidden)
    print("D23 PASS")
    print("FURTHER_OUT: 5/2 + 5/9 ONLY")
    print("NEARBY LINE COMPONENTS: 1-1 + 5/2 + 5/9")
    print("ET/EB: RECOVERED_PROXY")
    print("OUTCOMES USED: NO")

if __name__=="__main__":
    selftest()
