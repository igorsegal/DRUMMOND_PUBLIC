#!/usr/bin/env python3
import argparse,bisect,csv,json,math
from collections import defaultdict,Counter
from pathlib import Path

from drummond_replay01 import S,stop,norm,SIDE_LONG,SIDE_SHORT
from mt4_hst_replay01 import read_hst

ENTRY_ACTIONS={"CLAIMED","ORDER_OPENED","ORDER_REJECTED","BLOCKED"}
TERMINAL_ACTIONS={"ORDER_OPENED","ORDER_REJECTED","BLOCKED"}

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(path,fields,rows):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";")
        w.writeheader();w.writerows(rows)

def side_int(s):
    if s=="LONG": return SIDE_LONG
    if s=="SHORT": return SIDE_SHORT
    return 0

def feq(a,b,tol=5e-7):
    return math.isfinite(a) and math.isfinite(b) and abs(a-b)<=tol

def replay(queue_path,execution_path,h1_path,out_dir,spread_points=20,rr_min=.75,rr_max=1.75,
           max_spread_risk_pct=10.0,max_drift_risk_pct=10.0,min_margin_level_pct=5000.0,
           buffer_points=1):
    queue=read_csv(queue_path); execution=read_csv(execution_path)
    h1h,h1=read_hst(h1_path)
    if h1h["period"]!=60: raise ValueError("Executor Replay 01 requires H1 HST")
    point=h1h["point"];digits=h1h["digits"];h1t=[b[0] for b in h1]

    qidx={}
    for r in queue:
        sid=r.get("SIGNAL_ID","").strip()
        if not sid: raise ValueError("queue contains empty SIGNAL_ID")
        if sid in qidx: raise ValueError(f"duplicate queue SIGNAL_ID {sid}")
        qidx[sid]=r

    by_signal=defaultdict(list)
    for i,r in enumerate(execution):
        sid=r.get("SIGNAL_ID","").strip()
        if sid: by_signal[sid].append((i,r))

    mismatches=[]
    entry_rows=[]
    trail_rows=[]
    def mm(kind,key,field,expected,actual):
        mismatches.append({"KIND":kind,"KEY":str(key),"FIELD":field,
                           "EXPECTED":str(expected),"ACTUAL":str(actual)})

    deterministic_pass=0
    exact_entry_price=0
    opened=blocked=rejected=0
    margin_values=[];lot_values=[];age_values=[]
    ticket_state={}

    for sid,q in qidx.items():
        rows=by_signal.get(sid,[])
        if not rows:
            mm("ENTRY",sid,"EXECUTION_ROWS",">=1","0")
            continue
        claimed=[r for _,r in rows if r.get("ACTION")=="CLAIMED"]
        terminals=[r for _,r in rows if r.get("ACTION") in TERMINAL_ACTIONS]
        if len(terminals)!=1:
            mm("ENTRY",sid,"TERMINAL_COUNT","1",len(terminals))
            continue
        term=terminals[0]
        action=term["ACTION"]
        if action=="ORDER_OPENED": opened+=1
        elif action=="ORDER_REJECTED": rejected+=1
        elif action=="BLOCKED": blocked+=1

        probe=claimed[0] if claimed else term
        created=int(q["CREATED_AT"]);server=int(probe["SERVER_TIME"])
        age=max(0,server-created);age_values.append(age)
        side=side_int(q["SIDE"])
        if side==0:
            mm("ENTRY",sid,"SIDE","LONG/SHORT",q["SIDE"]);continue

        ci=bisect.bisect_right(h1t,server)-1
        if ci<0:
            mm("ENTRY",sid,"H1_CONTEXT","available",server);continue
        current_open=h1[ci][0]
        bid=h1[ci][1];ask=bid+max(0,spread_points)*point
        expected_price=norm(ask if side==SIDE_LONG else bid,digits)

        entry=float(q["ENTRY_REFERENCE"]);sl=float(q["STOP_PRICE"]);tp=float(q["TARGET_PRICE"])
        risk=abs(entry-sl)
        spread=ask-bid
        spread_pct=100.0*spread/risk if risk>0 else math.inf
        drift_pct=100.0*abs(expected_price-entry)/risk if risk>0 else math.inf
        geometry=(sl<expected_price<tp) if side==SIDE_LONG else (tp<expected_price<sl)
        reward=abs(tp-expected_price)
        rr=reward/abs(expected_price-sl) if abs(expected_price-sl)>0 else -1.0
        det_ok=(age<=15*60 and risk>0 and spread_pct<=max_spread_risk_pct and
                drift_pct<=max_drift_risk_pct and geometry and rr>=rr_min and
                (rr_max<=0 or rr<rr_max))
        if det_ok: deterministic_pass+=1

        logged_price=float(probe["PRICE"])
        if feq(logged_price,expected_price,point*0.01): exact_entry_price+=1
        else: mm("ENTRY",sid,"PRICE",f"{expected_price:.{digits}f}",probe["PRICE"])
        if int(probe["SERVER_TIME"])!=created:
            mm("ENTRY",sid,"AGE_SEC","0",int(probe["SERVER_TIME"])-created)
        if current_open!=server:
            mm("ENTRY",sid,"H1_CURRENT_OPEN",server,current_open)
        if not det_ok:
            mm("ENTRY",sid,"DETERMINISTIC_GATES","PASS",
               f"age={age},risk={risk},spread_pct={spread_pct},drift_pct={drift_pct},geometry={geometry},rr={rr}")
        logged_rr=float(probe["RR_CURRENT"])
        if not feq(logged_rr,rr,5e-6):
            mm("ENTRY",sid,"RR_CURRENT",f"{rr:.6f}",probe["RR_CURRENT"])

        if probe.get("SL","") and not feq(float(probe["SL"]),sl,point*0.01):
            mm("ENTRY",sid,"SL",q["STOP_PRICE"],probe["SL"])
        if probe.get("TP","") and not feq(float(probe["TP"]),tp,point*0.01):
            mm("ENTRY",sid,"TP",q["TARGET_PRICE"],probe["TP"])

        lots=float(probe["LOTS"]);lot_values.append(lots)
        projected=float(probe["PROJECTED_MARGIN_LEVEL_PCT"]);margin_values.append(projected)
        broker_evidence="PASS" if action=="ORDER_OPENED" else action
        if action=="ORDER_OPENED" and projected<min_margin_level_pct:
            mm("BROKER_EVIDENCE",sid,"PROJECTED_MARGIN_LEVEL_PCT",f">={min_margin_level_pct}",projected)

        entry_rows.append({
          "SIGNAL_ID":sid,"SERVER_TIME":server,"H1_CURRENT_OPEN":current_open,
          "SIDE":q["SIDE"],"EXPECTED_PRICE":f"{expected_price:.{digits}f}","LOGGED_PRICE":probe["PRICE"],
          "AGE_SEC":age,"SPREAD_POINTS":spread_points,"SPREAD_RISK_PCT":f"{spread_pct:.6f}",
          "DRIFT_RISK_PCT":f"{drift_pct:.6f}","RR_REPLAY":f"{rr:.6f}","RR_LOGGED":probe["RR_CURRENT"],
          "DETERMINISTIC_GATES":"PASS" if det_ok else "FAIL","RUNTIME_TERMINAL":action,
          "LOTS":probe["LOTS"],"PROJECTED_MARGIN_LEVEL_PCT":probe["PROJECTED_MARGIN_LEVEL_PCT"],
          "BROKER_ACCEPTANCE_EVIDENCE":broker_evidence
        })

        if action=="ORDER_OPENED":
            ticket=int(term["TICKET"])
            ticket_state[ticket]={"side":side,"sl":float(term["SL"]),"tp":float(term["TP"]),"sid":sid}

    exact_trails=0;tighter_pass=0;geometry_pass=0
    trail_action_counts=Counter()
    for pos,r in enumerate(execution):
        action=r.get("ACTION","")
        if action=="ORDER_OPENED":
            ticket=int(r["TICKET"])
            if ticket not in ticket_state:
                ticket_state[ticket]={"side":side_int(r["SIDE"]),"sl":float(r["SL"]),"tp":float(r["TP"]),"sid":r["SIGNAL_ID"]}
            continue
        if action not in ("TRAIL_UPDATED","TRAIL_REJECTED"): continue
        trail_action_counts[action]+=1
        ticket=int(r["TICKET"])
        st=ticket_state.get(ticket)
        if not st:
            mm("TRAIL",ticket,"OPEN_TICKET","known","missing")
            continue
        server=int(r["SERVER_TIME"]);reference=float(r["PRICE"]);logged_sl=float(r["SL"])
        ci=bisect.bisect_right(h1t,server)-1
        if ci<0:
            mm("TRAIL",ticket,"H1_CONTEXT","available",server);continue
        state=S(h1,ci,point,digits)
        candidate=stop(state,st["side"],reference,buffer_points)
        if candidate is None:
            mm("TRAIL",ticket,"STRUCTURAL_STOP","resolved","None")
            continue
        exact=feq(candidate,logged_sl,point*0.01)
        if exact: exact_trails+=1
        else: mm("TRAIL",ticket,"SL",f"{candidate:.{digits}f}",r["SL"])
        old=st["sl"]
        if st["side"]==SIDE_LONG:
            geom=candidate<reference
            tighter=(old<=0 or candidate>old+point)
        else:
            geom=candidate>reference
            tighter=(old<=0 or candidate<old-point)
        if geom:geometry_pass+=1
        else:mm("TRAIL",ticket,"GEOMETRY","valid",f"reference={reference},candidate={candidate}")
        if tighter:tighter_pass+=1
        else:mm("TRAIL",ticket,"TIGHTER_THAN_OLD_SL","true",f"old={old},candidate={candidate}")
        if action=="TRAIL_UPDATED":st["sl"]=logged_sl
        trail_rows.append({
          "ROW_INDEX":pos,"SERVER_TIME":server,"TICKET":ticket,"SOURCE_SIGNAL_ID":st["sid"],
          "SIDE":"LONG" if st["side"]==SIDE_LONG else "SHORT",
          "REFERENCE_PRICE":f"{reference:.{digits}f}","OLD_SL":f"{old:.{digits}f}",
          "REPLAY_CANDIDATE_SL":f"{candidate:.{digits}f}","LOGGED_SL":f"{logged_sl:.{digits}f}",
          "EXACT_CANDIDATE_MATCH":"PASS" if exact else "FAIL",
          "GEOMETRY":"PASS" if geom else "FAIL","TIGHTER":"PASS" if tighter else "FAIL",
          "RUNTIME_ACTION":action
        })

    expected_signal_ids=set(qidx)
    runtime_signal_ids=set(by_signal)
    for sid in sorted(runtime_signal_ids-expected_signal_ids):
        mm("ENTRY",sid,"QUEUE_MEMBERSHIP","present","unexpected execution signal")

    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    write_csv(out/"EXECUTOR_REPLAY01_ENTRY_CHECKS.csv",
      ["SIGNAL_ID","SERVER_TIME","H1_CURRENT_OPEN","SIDE","EXPECTED_PRICE","LOGGED_PRICE","AGE_SEC",
       "SPREAD_POINTS","SPREAD_RISK_PCT","DRIFT_RISK_PCT","RR_REPLAY","RR_LOGGED","DETERMINISTIC_GATES",
       "RUNTIME_TERMINAL","LOTS","PROJECTED_MARGIN_LEVEL_PCT","BROKER_ACCEPTANCE_EVIDENCE"],entry_rows)
    write_csv(out/"EXECUTOR_REPLAY01_TRAIL_CHECKS.csv",
      ["ROW_INDEX","SERVER_TIME","TICKET","SOURCE_SIGNAL_ID","SIDE","REFERENCE_PRICE","OLD_SL",
       "REPLAY_CANDIDATE_SL","LOGGED_SL","EXACT_CANDIDATE_MATCH","GEOMETRY","TIGHTER","RUNTIME_ACTION"],trail_rows)
    write_csv(out/"EXECUTOR_REPLAY01_MISMATCHES.csv",
      ["KIND","KEY","FIELD","EXPECTED","ACTUAL"],mismatches)

    summary={
      "replay":"DRUMMOND EXECUTOR REPLAY 01",
      "status":"PASS" if not mismatches else "FAIL",
      "scope":"Deterministic Executor entry gates + exact structural trailing replay on MT4 H1 HST. Broker distance/margin/order acceptance are retained as captured MT4 evidence, not synthesized.",
      "inputs":{"queue":str(queue_path),"execution":str(execution_path),"h1_hst":str(h1_path)},
      "parameters":{"spread_points":spread_points,"rr_min":rr_min,"rr_max_exclusive":rr_max,
        "max_spread_risk_pct":max_spread_risk_pct,"max_drift_risk_pct":max_drift_risk_pct,
        "min_projected_margin_level_pct":min_margin_level_pct,"protection_buffer_points":buffer_points},
      "counts":{"queue_signals":len(queue),"execution_rows":len(execution),
        "deterministic_entry_pass":deterministic_pass,"exact_entry_price":exact_entry_price,
        "opened":opened,"rejected":rejected,"blocked":blocked,
        "trail_rows":len(trail_rows),"exact_trail_candidate":exact_trails,
        "trail_geometry_pass":geometry_pass,"trail_tighter_pass":tighter_pass,
        "mismatches":len(mismatches)},
      "broker_evidence":{"lot_values":sorted(set(round(x,8) for x in lot_values)),
        "projected_margin_level_min":min(margin_values) if margin_values else None,
        "projected_margin_level_max":max(margin_values) if margin_values else None,
        "order_opened_count":opened,"order_rejected_count":rejected,"blocked_count":blocked,
        "trail_action_counts":dict(sorted(trail_action_counts.items()))},
      "age_sec":{"min":min(age_values) if age_values else None,"max":max(age_values) if age_values else None}
    }
    (out/"EXECUTOR_REPLAY01_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["DRUMMOND EXECUTOR REPLAY 01",f"STATUS: {summary['status']}",
      f"QUEUE SIGNALS: {len(queue)}",f"DETERMINISTIC ENTRY PASS: {deterministic_pass}/{len(queue)}",
      f"EXACT ENTRY PRICE: {exact_entry_price}/{len(queue)}",
      f"OPENED/REJECTED/BLOCKED: {opened}/{rejected}/{blocked}",
      f"TRAIL CANDIDATE EXACT: {exact_trails}/{len(trail_rows)}",
      f"TRAIL GEOMETRY/TIGHTER: {geometry_pass}/{tighter_pass}",
      f"MISMATCHES: {len(mismatches)}",
      "BROKER NOTE: broker distances, projected margin mechanics and OrderSend/OrderModify acceptance remain MT4 evidence."]
    (out/"EXECUTOR_REPLAY01_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
    return 0 if not mismatches else 2

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--queue",type=Path,required=True)
    ap.add_argument("--execution",type=Path,required=True)
    ap.add_argument("--h1",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--spread-points",type=int,default=20)
    a=ap.parse_args()
    raise SystemExit(replay(a.queue,a.execution,a.h1,a.out,a.spread_points))

if __name__=="__main__":main()
