#!/usr/bin/env python3
import argparse,csv,json,math,sys
from collections import Counter
from pathlib import Path

PRICE_FIELDS=("ENTRY_REFERENCE","STOP_PRICE","TARGET_PRICE")
RR_FIELDS=("RR",)
AUDIT_TEXT=("STATUS","REASON","GATES_PASSED","GATES_TOTAL","SIDE","SIGNAL_ID")
SIGNAL_TEXT=("SYMBOL","DECISION_TIME","SIDE","SIGNAL_NAME","DECISION_TF","HTP_TF")
SIGNAL_NUM=("ENTRY_REFERENCE","STOP_PRICE","TARGET_PRICE","RR")

def read_csv(path):
    path=Path(path)
    if not path.exists(): raise FileNotFoundError(path)
    with path.open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(path,fields,rows):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";")
        w.writeheader(); w.writerows(rows)

def as_int(v,name):
    try:return int(str(v).strip())
    except Exception:raise ValueError(f"bad integer {name}={v!r}")

def as_float(v,name):
    try:return float(str(v).strip())
    except Exception:raise ValueError(f"bad number {name}={v!r}")

def num_equal(a,b,field):
    x,y=as_float(a,field),as_float(b,field)
    tol=5e-7 if field=="RR" else 5e-7
    return math.isfinite(x) and math.isfinite(y) and abs(x-y)<=tol

def index_unique(rows,key,label):
    out={}
    for r in rows:
        k=str(r.get(key,"")).strip()
        if not k: raise ValueError(f"{label}: empty {key}")
        if k in out: raise ValueError(f"{label}: duplicate {key}={k}")
        out[k]=r
    return out

def decision_index(rows,label):
    out={}
    for r in rows:
        k=as_int(r.get("DECISION_TIME",""),"DECISION_TIME")
        if k in out: raise ValueError(f"{label}: duplicate DECISION_TIME={k}")
        out[k]=r
    return out

def add_mismatch(dst,kind,key,field,expected,actual):
    dst.append({"KIND":kind,"KEY":key,"FIELD":field,"EXPECTED":expected,"ACTUAL":actual})

def compare(replay_dir,watcher_path,signals_path,out_dir,replay_audit=None,replay_signals=None):
    replay_dir=Path(replay_dir); out_dir=Path(out_dir)
    audit_path=Path(replay_audit) if replay_audit else replay_dir/"XAUUSD_REPLAY_AUDIT.csv"
    signal_path=Path(replay_signals) if replay_signals else replay_dir/"XAUUSD_REPLAY_SIGNALS.csv"
    exp_a=read_csv(audit_path)
    exp_s=read_csv(signal_path)
    mt_a=read_csv(watcher_path); mt_s=read_csv(signals_path)
    if not exp_a: raise ValueError("Replay audit is empty")
    exp_idx=decision_index(exp_a,"replay audit")
    lo,hi=min(exp_idx),max(exp_idx)
    mt_a=[r for r in mt_a if str(r.get("SYMBOL","XAUUSD")).strip()=="XAUUSD" and lo<=as_int(r.get("DECISION_TIME","0"),"DECISION_TIME")<=hi]
    mt_s=[r for r in mt_s if str(r.get("SYMBOL","")).strip()=="XAUUSD" and lo<=as_int(r.get("DECISION_TIME","0"),"DECISION_TIME")<=hi]
    mt_idx=decision_index(mt_a,"MT4 watcher")
    mism=[]
    exp_keys=set(exp_idx); mt_keys=set(mt_idx)
    for k in sorted(exp_keys-mt_keys): add_mismatch(mism,"AUDIT_MISSING_MT4",k,"DECISION_TIME",k,"")
    for k in sorted(mt_keys-exp_keys): add_mismatch(mism,"AUDIT_EXTRA_MT4",k,"DECISION_TIME","",k)
    common=sorted(exp_keys & mt_keys)
    field_mismatch=Counter()
    for k in common:
        e,m=exp_idx[k],mt_idx[k]
        for fld in AUDIT_TEXT:
            ev,mv=str(e.get(fld,"")).strip(),str(m.get(fld,"")).strip()
            if ev!=mv:
                add_mismatch(mism,"AUDIT_FIELD",k,fld,ev,mv);field_mismatch[fld]+=1
        for fld in PRICE_FIELDS+RR_FIELDS:
            ev,mv=e.get(fld,""),m.get(fld,"")
            if not num_equal(ev,mv,fld):
                add_mismatch(mism,"AUDIT_FIELD",k,fld,ev,mv);field_mismatch[fld]+=1
    exp_sig=index_unique(exp_s,"SIGNAL_ID","replay signals")
    mt_sig=index_unique(mt_s,"SIGNAL_ID","MT4 signals")
    exp_ids=set(exp_sig); mt_ids=set(mt_sig)
    for k in sorted(exp_ids-mt_ids): add_mismatch(mism,"SIGNAL_MISSING_MT4",k,"SIGNAL_ID",k,"")
    for k in sorted(mt_ids-exp_ids): add_mismatch(mism,"SIGNAL_EXTRA_MT4",k,"SIGNAL_ID","",k)
    sig_field_mismatch=Counter()
    for k in sorted(exp_ids & mt_ids):
        e,m=exp_sig[k],mt_sig[k]
        for fld in SIGNAL_TEXT:
            ev,mv=str(e.get(fld,"")).strip(),str(m.get(fld,"")).strip()
            if ev!=mv:
                add_mismatch(mism,"SIGNAL_FIELD",k,fld,ev,mv);sig_field_mismatch[fld]+=1
        for fld in SIGNAL_NUM:
            if not num_equal(e.get(fld,""),m.get(fld,""),fld):
                add_mismatch(mism,"SIGNAL_FIELD",k,fld,e.get(fld,""),m.get(fld,""));sig_field_mismatch[fld]+=1
    reason_exp=Counter(str(r.get("REASON","")).strip() for r in exp_a)
    reason_mt=Counter(str(r.get("REASON","")).strip() for r in mt_a)
    status="PASS" if not mism else "FAIL"
    summary={
      "equivalence":"MT4 EQUIVALENCE 01","status":status,"symbol":"XAUUSD",
      "decision_range":{"first":lo,"last":hi},
      "counts":{"replay_audit":len(exp_a),"mt4_audit_in_range":len(mt_a),"matched_audit_keys":len(common),
                "replay_signals":len(exp_s),"mt4_signals_in_range":len(mt_s),
                "audit_missing_mt4":len(exp_keys-mt_keys),"audit_extra_mt4":len(mt_keys-exp_keys),
                "signal_missing_mt4":len(exp_ids-mt_ids),"signal_extra_mt4":len(mt_ids-exp_ids),
                "field_mismatches":sum(field_mismatch.values()),"signal_field_mismatches":sum(sig_field_mismatch.values()),
                "total_mismatches":len(mism)},
      "field_mismatches":dict(sorted(field_mismatch.items())),
      "signal_field_mismatches":dict(sorted(sig_field_mismatch.items())),
      "reason_distribution_replay":dict(sorted(reason_exp.items())),
      "reason_distribution_mt4":dict(sorted(reason_mt.items()))
    }
    out_dir.mkdir(parents=True,exist_ok=True)
    write_csv(out_dir/"MT4_EQ01_MISMATCHES.csv",["KIND","KEY","FIELD","EXPECTED","ACTUAL"],mism)
    (out_dir/"MT4_EQ01_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["MT4 EQUIVALENCE 01",f"STATUS: {status}","SYMBOL: XAUUSD",
           f"REPLAY AUDIT: {len(exp_a)}",f"MT4 AUDIT IN RANGE: {len(mt_a)}",
           f"REPLAY SIGNALS: {len(exp_s)}",f"MT4 SIGNALS IN RANGE: {len(mt_s)}",
           f"AUDIT MISSING/EXTRA: {len(exp_keys-mt_keys)}/{len(mt_keys-exp_keys)}",
           f"SIGNAL MISSING/EXTRA: {len(exp_ids-mt_ids)}/{len(mt_ids-exp_ids)}",
           f"AUDIT FIELD MISMATCHES: {sum(field_mismatch.values())}",
           f"SIGNAL FIELD MISMATCHES: {sum(sig_field_mismatch.values())}",
           f"TOTAL MISMATCHES: {len(mism)}"]
    (out_dir/"MT4_EQ01_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
    return 0 if status=="PASS" else 2

def make_self_fixture(replay_dir,out_dir):
    replay_dir=Path(replay_dir);out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    ra=read_csv(replay_dir/"XAUUSD_REPLAY_AUDIT.csv")
    rs=read_csv(replay_dir/"XAUUSD_REPLAY_SIGNALS.csv")
    wa=[]
    for r in ra:
        wa.append({"SERVER_TIME":r["EVAL_TIME"],"SYMBOL":"XAUUSD","DECISION_TIME":r["DECISION_TIME"],
                   "STATUS":r["STATUS"],"REASON":r["REASON"],"GATES_PASSED":r["GATES_PASSED"],
                   "GATES_TOTAL":r["GATES_TOTAL"],"MATCH_PCT":r["MATCH_PCT"],"SIDE":r["SIDE"],
                   "ENTRY_REFERENCE":r["ENTRY_REFERENCE"],"STOP_PRICE":r["STOP_PRICE"],
                   "TARGET_PRICE":r["TARGET_PRICE"],"RR":r["RR"],"SIGNAL_ID":r["SIGNAL_ID"]})
    sf=["SIGNAL_ID","CREATED_AT","SYMBOL","DECISION_TIME","SIDE","ENTRY_REFERENCE","STOP_PRICE","TARGET_PRICE","RR","SIGNAL_NAME","DECISION_TF","HTP_TF"]
    ss=[{k:r.get(k,"") for k in sf} for r in rs]
    wf=["SERVER_TIME","SYMBOL","DECISION_TIME","STATUS","REASON","GATES_PASSED","GATES_TOTAL","MATCH_PCT","SIDE","ENTRY_REFERENCE","STOP_PRICE","TARGET_PRICE","RR","SIGNAL_ID"]
    write_csv(out_dir/"DRUMMOND_DEMO02_WATCHER.csv",wf,wa)
    write_csv(out_dir/"DRUMMOND_DEMO02_SIGNALS.csv",sf,ss)
    print(f"SELF FIXTURE PASS: {len(wa)} audit rows, {len(ss)} signals")

def main():
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest="cmd",required=True)
    p=sub.add_parser("compare")
    p.add_argument("--replay-dir",type=Path,required=True)
    p.add_argument("--mt4-watcher",type=Path,required=True)
    p.add_argument("--mt4-signals",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--replay-audit",type=Path)
    p.add_argument("--replay-signals",type=Path)
    s=sub.add_parser("make-self-fixture")
    s.add_argument("--replay-dir",type=Path,required=True);s.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    if a.cmd=="make-self-fixture":
        make_self_fixture(a.replay_dir,a.out);return
    raise SystemExit(compare(a.replay_dir,a.mt4_watcher,a.mt4_signals,a.out,a.replay_audit,a.replay_signals))

if __name__=="__main__":main()
