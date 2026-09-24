#!/usr/bin/env python3
import argparse,csv,json,sys
from collections import Counter,defaultdict
from pathlib import Path

TERMINAL_ACTIONS={"BLOCKED","ORDER_OPENED","ORDER_REJECTED"}

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(path,fields,rows):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";");w.writeheader();w.writerows(rows)

def make_queue(src,dst,start,end,symbol="XAUUSD"):
    rows=[r for r in read_csv(src)
          if r.get("SYMBOL")==symbol and start<=int(r["CREATED_AT"])<=end]
    if not rows: raise SystemExit("EXECUTOR EQ01: no signals in requested window")
    fields=["SIGNAL_ID","CREATED_AT","SYMBOL","DECISION_TIME","SIDE","ENTRY_REFERENCE",
            "STOP_PRICE","TARGET_PRICE","RR","SIGNAL_NAME","DECISION_TF","HTP_TF"]
    write_csv(dst,fields,[{k:r.get(k,"") for k in fields} for r in rows])
    print(f"EXECUTOR EQ01 QUEUE PASS: {len(rows)} signals")
    print(f"FIRST: {rows[0]['SIGNAL_ID']} @ {rows[0]['CREATED_AT']}")
    print(f"LAST : {rows[-1]['SIGNAL_ID']} @ {rows[-1]['CREATED_AT']}")

def numeq(a,b,tol=5e-7):
    try:return abs(float(a)-float(b))<=tol
    except:return False

def analyze(queue_path,execution_path,out_dir,max_age_minutes=15):
    q=read_csv(queue_path); ex=read_csv(execution_path)
    qi={r["SIGNAL_ID"]:r for r in q}
    violations=[]
    def v(kind,sid,detail):
        violations.append({"KIND":kind,"SIGNAL_ID":sid,"DETAIL":detail})
    per=defaultdict(list);trail=[]
    for i,r in enumerate(ex):
        sid=r.get("SIGNAL_ID","").strip()
        if sid: per[sid].append((i,r))
        else: trail.append((i,r))
    for sid in per:
        if sid not in qi: v("UNEXPECTED_SIGNAL_ID",sid,"execution contains signal not in frozen queue")
    action_counts=Counter();reason_counts=Counter()
    opened=rejected=blocked=claimed=0
    ages=[]
    for sid,s in qi.items():
        rows=per.get(sid,[])
        if not rows:
            v("MISSING_SIGNAL",sid,"no execution record")
            continue
        terms=[x for x in rows if x[1].get("ACTION") in TERMINAL_ACTIONS]
        claims=[x for x in rows if x[1].get("ACTION")=="CLAIMED"]
        if len(terms)!=1:
            v("TERMINAL_ACTION_COUNT",sid,f"expected 1 terminal action, got {len(terms)}")
        if len(claims)>1:
            v("CLAIM_COUNT",sid,f"expected <=1 CLAIMED, got {len(claims)}")
        for idx,r in rows:
            action=r.get("ACTION","");reason=r.get("REASON","")
            action_counts[action]+=1;reason_counts[reason]+=1
            for fld in ("SYMBOL","DECISION_TIME","SIDE"):
                if str(r.get(fld,"")).strip()!=str(s.get(fld,"")).strip():
                    v("FIELD_MISMATCH",sid,f"{fld}: queue={s.get(fld,'')} execution={r.get(fld,'')}")
            for ef,qf in (("SL","STOP_PRICE"),("TP","TARGET_PRICE")):
                if not numeq(r.get(ef,""),s.get(qf,"")):
                    v("PRICE_MISMATCH",sid,f"{ef}: queue={s.get(qf,'')} execution={r.get(ef,'')}")
        if terms:
            tidx,tr=terms[0];act=tr["ACTION"]
            if act=="BLOCKED":
                blocked+=1
                if claims:v("CLAIM_BEFORE_BLOCK",sid,"BLOCKED signal must not be CLAIMED")
            elif act=="ORDER_OPENED":
                opened+=1
                if len(claims)!=1:v("OPEN_WITHOUT_SINGLE_CLAIM",sid,f"CLAIMED rows={len(claims)}")
                else:
                    if claims[0][0]>tidx:v("CLAIM_ORDER",sid,"CLAIMED appears after ORDER_OPENED")
                try:
                    if int(tr.get("TICKET","-1"))<=0:v("OPEN_BAD_TICKET",sid,tr.get("TICKET",""))
                    if int(tr.get("ERROR","0"))!=0:v("OPEN_ERROR_NONZERO",sid,tr.get("ERROR",""))
                except:v("OPEN_NUMERIC_PARSE",sid,"bad ticket/error")
            elif act=="ORDER_REJECTED":
                rejected+=1
                if len(claims)!=1:v("REJECT_WITHOUT_SINGLE_CLAIM",sid,f"CLAIMED rows={len(claims)}")
                else:
                    if claims[0][0]>tidx:v("CLAIM_ORDER",sid,"CLAIMED appears after ORDER_REJECTED")
            try:
                age=int(tr["SERVER_TIME"])-int(s["CREATED_AT"]);ages.append(age)
                if age<0:v("NEGATIVE_AGE",sid,str(age))
                if act!="BLOCKED" or tr.get("REASON")!="SIGNAL_EXPIRED":
                    if max_age_minutes>0 and age>max_age_minutes*60:
                        v("LATE_PROCESSING",sid,f"age_sec={age}")
            except:v("AGE_PARSE",sid,"bad SERVER_TIME/CREATED_AT")
        claimed+=len(claims)
    for _,r in trail:
        if r.get("ACTION") not in ("TRAIL_UPDATED","TRAIL_REJECTED"):
            v("EMPTY_ID_NON_TRAIL","",f"action={r.get('ACTION','')}")
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    write_csv(out/"MT4_EXEC_EQ01_VIOLATIONS.csv",["KIND","SIGNAL_ID","DETAIL"],violations)
    summary={
      "block":"MT4 EXECUTOR CAPTURE 01",
      "status":"PASS" if not violations else "FAIL",
      "queue_signals":len(q),"execution_rows":len(ex),"signals_seen":len(per),
      "terminal":{"opened":opened,"rejected":rejected,"blocked":blocked,"claimed":claimed},
      "trailing_rows":len(trail),"violation_count":len(violations),
      "action_counts":dict(sorted(action_counts.items())),
      "reason_counts":dict(sorted(reason_counts.items())),
      "age_sec":{"min":min(ages) if ages else None,"max":max(ages) if ages else None}
    }
    (out/"MT4_EXEC_EQ01_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["MT4 EXECUTOR CAPTURE 01",f"STATUS: {summary['status']}",f"QUEUE SIGNALS: {len(q)}",
           f"EXECUTION ROWS: {len(ex)}",f"OPENED/REJECTED/BLOCKED: {opened}/{rejected}/{blocked}",
           f"CLAIMED: {claimed}",f"TRAIL ROWS: {len(trail)}",f"VIOLATIONS: {len(violations)}"]
    (out/"MT4_EXEC_EQ01_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
    return 0 if not violations else 2

def selftest(tmp):
    p=Path(tmp);p.mkdir(parents=True,exist_ok=True)
    qf=p/"q.csv";ef=p/"e.csv";out=p/"out"
    qfields=["SIGNAL_ID","CREATED_AT","SYMBOL","DECISION_TIME","SIDE","ENTRY_REFERENCE","STOP_PRICE","TARGET_PRICE","RR","SIGNAL_NAME","DECISION_TF","HTP_TF"]
    q=[
      {"SIGNAL_ID":"A","CREATED_AT":"1000","SYMBOL":"XAUUSD","DECISION_TIME":"900","SIDE":"SHORT","ENTRY_REFERENCE":"100","STOP_PRICE":"102","TARGET_PRICE":"97","RR":"1.5","SIGNAL_NAME":"X","DECISION_TF":"60","HTP_TF":"240"},
      {"SIGNAL_ID":"B","CREATED_AT":"2000","SYMBOL":"XAUUSD","DECISION_TIME":"1900","SIDE":"SHORT","ENTRY_REFERENCE":"100","STOP_PRICE":"102","TARGET_PRICE":"97","RR":"1.5","SIGNAL_NAME":"X","DECISION_TF":"60","HTP_TF":"240"},
      {"SIGNAL_ID":"C","CREATED_AT":"3000","SYMBOL":"XAUUSD","DECISION_TIME":"2900","SIDE":"SHORT","ENTRY_REFERENCE":"100","STOP_PRICE":"102","TARGET_PRICE":"97","RR":"1.5","SIGNAL_NAME":"X","DECISION_TF":"60","HTP_TF":"240"}]
    write_csv(qf,qfields,q)
    eflds=["SIGNAL_ID","SERVER_TIME","ACTION","REASON","SYMBOL","DECISION_TIME","SIDE","LOTS","PRICE","SL","TP","RR_CURRENT","PROJECTED_MARGIN_LEVEL_PCT","TICKET","ERROR"]
    e=[
      {"SIGNAL_ID":"A","SERVER_TIME":"1000","ACTION":"CLAIMED","REASON":"CLAIMED_BEFORE_ORDERSEND","SYMBOL":"XAUUSD","DECISION_TIME":"900","SIDE":"SHORT","LOTS":"0.01","PRICE":"100","SL":"102","TP":"97","RR_CURRENT":"1.5","PROJECTED_MARGIN_LEVEL_PCT":"9999","TICKET":"-1","ERROR":"0"},
      {"SIGNAL_ID":"A","SERVER_TIME":"1001","ACTION":"ORDER_OPENED","REASON":"ORDER_OPENED","SYMBOL":"XAUUSD","DECISION_TIME":"900","SIDE":"SHORT","LOTS":"0.01","PRICE":"100","SL":"102","TP":"97","RR_CURRENT":"1.5","PROJECTED_MARGIN_LEVEL_PCT":"9999","TICKET":"123","ERROR":"0"},
      {"SIGNAL_ID":"B","SERVER_TIME":"2000","ACTION":"BLOCKED","REASON":"SPREAD_TOO_LARGE_VS_RISK","SYMBOL":"XAUUSD","DECISION_TIME":"1900","SIDE":"SHORT","LOTS":"0.01","PRICE":"100","SL":"102","TP":"97","RR_CURRENT":"1.5","PROJECTED_MARGIN_LEVEL_PCT":"0","TICKET":"-1","ERROR":"0"},
      {"SIGNAL_ID":"C","SERVER_TIME":"3000","ACTION":"CLAIMED","REASON":"CLAIMED_BEFORE_ORDERSEND","SYMBOL":"XAUUSD","DECISION_TIME":"2900","SIDE":"SHORT","LOTS":"0.01","PRICE":"100","SL":"102","TP":"97","RR_CURRENT":"1.5","PROJECTED_MARGIN_LEVEL_PCT":"9999","TICKET":"-1","ERROR":"0"},
      {"SIGNAL_ID":"C","SERVER_TIME":"3001","ACTION":"ORDER_REJECTED","REASON":"ORDERSEND_ERROR_130","SYMBOL":"XAUUSD","DECISION_TIME":"2900","SIDE":"SHORT","LOTS":"0.01","PRICE":"100","SL":"102","TP":"97","RR_CURRENT":"1.5","PROJECTED_MARGIN_LEVEL_PCT":"9999","TICKET":"-1","ERROR":"130"},
      {"SIGNAL_ID":"","SERVER_TIME":"3100","ACTION":"TRAIL_UPDATED","REASON":"TRAIL_UPDATED","SYMBOL":"XAUUSD","DECISION_TIME":"0","SIDE":"SHORT","LOTS":"0.01","PRICE":"99","SL":"101","TP":"97","RR_CURRENT":"0","PROJECTED_MARGIN_LEVEL_PCT":"0","TICKET":"123","ERROR":"0"}]
    write_csv(ef,eflds,e)
    rc=analyze(qf,ef,out)
    if rc:raise SystemExit("EXECUTOR CAPTURE SELFTEST FAIL")
    print("MT4 EXECUTOR CAPTURE 01 SELFTEST PASS")

def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest="cmd",required=True)
    q=sub.add_parser("make-queue");q.add_argument("--source",required=True);q.add_argument("--out",required=True);q.add_argument("--start",type=int,required=True);q.add_argument("--end",type=int,required=True)
    a=sub.add_parser("analyze");a.add_argument("--queue",required=True);a.add_argument("--execution",required=True);a.add_argument("--out",required=True);a.add_argument("--max-age-minutes",type=int,default=15)
    s=sub.add_parser("selftest");s.add_argument("--tmp",required=True)
    x=ap.parse_args()
    if x.cmd=="make-queue":make_queue(x.source,x.out,x.start,x.end)
    elif x.cmd=="analyze":raise SystemExit(analyze(x.queue,x.execution,x.out,x.max_age_minutes))
    else:selftest(x.tmp)

if __name__=="__main__":main()
