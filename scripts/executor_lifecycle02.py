#!/usr/bin/env python3
import argparse,bisect,csv,json,math,tempfile
from collections import Counter,defaultdict
from pathlib import Path

from mt4_hst_replay01 import read_hst,HST_HEADER,HST_REC

SIDE_LONG=1
SIDE_SHORT=-1

def read_csv(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter=";"))

def write_csv(path,fields,rows):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=";");w.writeheader();w.writerows(rows)

def side_int(s):
    return SIDE_LONG if s=="LONG" else SIDE_SHORT if s=="SHORT" else 0

def feq(a,b,tol):
    return math.isfinite(a) and math.isfinite(b) and abs(a-b)<=tol

def bar_trigger(side,o,hi,lo,sl,tp,spread):
    if side==SIDE_LONG:
        open_q=o; hi_q=hi; lo_q=lo
        if sl>0 and open_q<=sl:
            return ("SL",sl,open_q,"OPEN_GAP")
        if tp>0 and open_q>=tp:
            return ("TP",tp,open_q,"OPEN_GAP")
        sl_hit=(sl>0 and lo_q<=sl)
        tp_hit=(tp>0 and hi_q>=tp)
        if sl_hit and tp_hit:
            return ("AMBIGUOUS",0.0,open_q,"BOTH_LEVELS_IN_BAR")
        if sl_hit:
            return ("SL",sl,lo_q,"BAR_RANGE")
        if tp_hit:
            return ("TP",tp,hi_q,"BAR_RANGE")
        return None
    if side==SIDE_SHORT:
        open_q=o+spread; hi_q=hi+spread; lo_q=lo+spread
        if sl>0 and open_q>=sl:
            return ("SL",sl,open_q,"OPEN_GAP")
        if tp>0 and open_q<=tp:
            return ("TP",tp,open_q,"OPEN_GAP")
        sl_hit=(sl>0 and hi_q>=sl)
        tp_hit=(tp>0 and lo_q<=tp)
        if sl_hit and tp_hit:
            return ("AMBIGUOUS",0.0,open_q,"BOTH_LEVELS_IN_BAR")
        if sl_hit:
            return ("SL",sl,hi_q,"BAR_RANGE")
        if tp_hit:
            return ("TP",tp,lo_q,"BAR_RANGE")
        return None
    return None

def simulate_ticket(info,m5,m5t,point,spread_points,trails,horizon,period_seconds):
    side=info["side"];sl=info["sl"];tp=info["tp"];open_time=info["open_time"]
    spread=max(0,spread_points)*point
    trail_by_time=defaultdict(list)
    for x in trails:
        trail_by_time[x["time"]].append(x)

    i=bisect.bisect_right(m5t,open_time)
    while i<len(m5):
        t,o,hi,lo,c,tv,sp,rv=m5[i]
        if horizon and t>horizon:
            break

        # Existing SL/TP can gap at the next modeled M5 open before the EA gets control.
        open_only=bar_trigger(side,o,o,o,sl,tp,spread)
        if open_only:
            reason,level,quote,mode=open_only
            return {"status":"AMBIGUOUS" if reason=="AMBIGUOUS" else "CLOSED",
                    "time":t,"reason":reason,"trigger_quote":quote,"trigger_level":level,
                    "trigger_mode":mode,"sl":sl,"tp":tp}

        # OnTick runs at the bar open. Proven TRAIL_UPDATED rows therefore become
        # active before the remainder of that M5 bar is modeled.
        for x in trail_by_time.get(t,[]):
            sl=x["sl"]

        hit=bar_trigger(side,o,hi,lo,sl,tp,spread)
        if hit:
            reason,level,quote,mode=hit
            event_time=t+period_seconds
            # MT4 Open-prices-only records an SL/TP reached by the modeled bar
            # at that bar's completion/next-bar timestamp, not at the bar-open stamp.
            # A test ending inside the bar must not consume its full future range.
            if horizon and event_time>horizon:
                break
            return {"status":"AMBIGUOUS" if reason=="AMBIGUOUS" else "CLOSED",
                    "time":event_time,"reason":reason,"trigger_quote":quote,"trigger_level":level,
                    "trigger_mode":mode,"sl":sl,"tp":tp}
        i+=1

    return {"status":"OPEN_AT_HORIZON","time":horizon or (m5[-1][0] if m5 else 0),"reason":"",
            "trigger_quote":0.0,"trigger_level":0.0,"trigger_mode":"",
            "sl":sl,"tp":tp}

def analyze(queue_path,execution_path,lifecycle_path,m5_path,out_dir,spread_points=20):
    queue=read_csv(queue_path);execution=read_csv(execution_path);life=read_csv(lifecycle_path)
    h,m5=read_hst(m5_path)
    if h["period"]!=5:
        raise ValueError(f"expected M5 HST, got period={h['period']}")
    point=h["point"];digits=h["digits"];m5t=[b[0] for b in m5]

    qids={r["SIGNAL_ID"] for r in queue}
    tickets={}
    trails=defaultdict(list)
    for pos,r in enumerate(execution):
        a=r.get("ACTION","")
        if a=="ORDER_OPENED":
            t=int(r["TICKET"])
            tickets[t]={"ticket":t,"sid":r["SIGNAL_ID"],"side":side_int(r["SIDE"]),
                        "open_time":int(r["SERVER_TIME"]),"open_price":float(r["PRICE"]),
                        "sl":float(r["SL"]),"tp":float(r["TP"]),"lots":float(r["LOTS"])}
        elif a in ("TRAIL_UPDATED","TRAIL_REJECTED"):
            trails[int(r["TICKET"])].append({"time":int(r["SERVER_TIME"]),"sl":float(r["SL"]),
                                             "action":a,"row":pos})

    life_open={};life_close={}
    for r in life:
        t=int(r["TICKET"]);ev=r["EVENT"]
        if ev=="OPEN": life_open[t]=r
        elif ev=="CLOSE": life_close[t]=r
    close_times=[int(r["CLOSE_TIME"]) for r in life if r.get("EVENT")=="CLOSE" and r.get("CLOSE_TIME")]
    max_close_time=max(close_times) if close_times else 0

    mism=[];checks=[]
    def mm(kind,key,field,expected,actual):
        mism.append({"KIND":kind,"KEY":str(key),"FIELD":field,
                     "EXPECTED":str(expected),"ACTUAL":str(actual)})

    reasons=Counter();fill_modes=Counter();trigger_modes=Counter()
    matched=0;forced_end=0;ambiguous=0
    for ticket,info in sorted(tickets.items()):
        sid=info["sid"]
        if sid not in qids:
            mm("LIFECYCLE",ticket,"QUEUE_SIGNAL_ID","present",sid)
        op=life_open.get(ticket)
        if op is None:
            mm("LIFECYCLE",ticket,"OPEN_EVENT","present","missing")
        else:
            for fld,expected in (("SIGNAL_ID",sid),("SYMBOL","XAUUSD"),
                                 ("SIDE","LONG" if info["side"]==SIDE_LONG else "SHORT")):
                if str(op.get(fld,""))!=str(expected):
                    mm("OPEN",ticket,fld,expected,op.get(fld,""))
            if int(op["OPEN_TIME"])!=info["open_time"]:
                mm("OPEN",ticket,"OPEN_TIME",info["open_time"],op["OPEN_TIME"])
            if not feq(float(op["OPEN_PRICE"]),info["open_price"],point*0.01):
                mm("OPEN",ticket,"OPEN_PRICE",info["open_price"],op["OPEN_PRICE"])

        cl=life_close.get(ticket)
        actual_status="CLOSED" if cl else "OPEN_AT_TEST_END"
        actual_time=int(cl["CLOSE_TIME"]) if cl else 0
        actual_reason=cl["CLOSE_REASON"] if cl else ""
        actual_price=float(cl["CLOSE_PRICE"]) if cl else 0.0
        updates=[x for x in trails.get(ticket,[]) if x["action"]=="TRAIL_UPDATED"]
        horizon=actual_time if cl else max_close_time
        sim=simulate_ticket(info,m5,m5t,point,spread_points,updates,horizon,h["period"]*60)

        time_match=False;reason_match=False;fill_mode="";classification=""
        if cl and actual_reason in ("SL","TP"):
            if sim["status"]=="AMBIGUOUS":
                ambiguous+=1
                mm("CLOSE",ticket,"M5_RANGE_ORDER","unambiguous",f"both SL/TP touched at {sim['time']}")
            elif sim["status"]!="CLOSED":
                mm("CLOSE",ticket,"SIM_TRIGGER",f"{actual_reason}@{actual_time}","not reached by actual close")
            else:
                time_match=(actual_time==sim["time"])
                reason_match=(actual_reason==sim["reason"])
                if not time_match:
                    mm("CLOSE",ticket,"CLOSE_TIME",sim["time"],actual_time)
                if not reason_match:
                    mm("CLOSE",ticket,"CLOSE_REASON",sim["reason"],actual_reason)
                if time_match and reason_match:
                    matched+=1
                if feq(actual_price,sim["trigger_level"],point*0.01):
                    fill_mode="AT_TRIGGER_LEVEL"
                elif feq(actual_price,sim["trigger_quote"],point*0.01):
                    fill_mode="AT_TRIGGER_QUOTE"
                else:
                    fill_mode="OTHER"
                fill_modes[fill_mode]+=1
                trigger_modes[sim["trigger_mode"]]+=1
                classification="STOP_OR_TARGET"

        elif cl and actual_reason=="OTHER":
            # EQ02 has no OrderClose path. If no stop/target was reachable before
            # the final history close and this is the run's final close timestamp,
            # classify it as the Strategy Tester's forced end-of-test liquidation.
            no_prior_trigger=(sim["status"]=="OPEN_AT_HORIZON")
            at_test_end=(actual_time==max_close_time)
            away_from_levels=(not feq(actual_price,float(cl["FINAL_SL"]),point*0.01) and
                              not feq(actual_price,float(cl["TP"]),point*0.01))
            if no_prior_trigger and at_test_end and away_from_levels:
                time_match=True;reason_match=True;fill_mode="TEST_END_MARKET"
                classification="TEST_END_FORCED_CLOSE";forced_end+=1;matched+=1
                fill_modes[fill_mode]+=1
            else:
                mm("CLOSE",ticket,"OTHER_CLASSIFICATION","TEST_END_FORCED_CLOSE",
                   f"sim={sim['status']}@{sim['time']}, max_close={max_close_time}, price={actual_price}")
        elif cl:
            mm("CLOSE",ticket,"CLOSE_REASON","SL/TP/OTHER",actual_reason)
        else:
            mm("CLOSE",ticket,"CLOSE_EVENT","present","missing")

        if cl:
            reasons[actual_reason]+=1
        checks.append({
          "TICKET":ticket,"SIGNAL_ID":sid,"SIDE":"LONG" if info["side"]==SIDE_LONG else "SHORT",
          "OPEN_TIME":info["open_time"],"OPEN_PRICE":f"{info['open_price']:.{digits}f}",
          "TRAIL_UPDATES":len(updates),"SIM_STATUS":sim["status"],
          "SIM_CLOSE_TIME":sim["time"] if sim["status"] in ("CLOSED","AMBIGUOUS") else "",
          "SIM_REASON":sim["reason"],
          "SIM_TRIGGER_LEVEL":f"{sim['trigger_level']:.{digits}f}" if sim["status"]=="CLOSED" else "",
          "SIM_TRIGGER_QUOTE":f"{sim['trigger_quote']:.{digits}f}" if sim["status"]=="CLOSED" else "",
          "SIM_TRIGGER_MODE":sim["trigger_mode"],"ACTUAL_STATUS":actual_status,
          "ACTUAL_CLOSE_TIME":actual_time if cl else "","ACTUAL_REASON":actual_reason,
          "ACTUAL_CLOSE_PRICE":f"{actual_price:.{digits}f}" if cl else "",
          "TIME_MATCH":"PASS" if time_match else "FAIL",
          "REASON_MATCH":"PASS" if reason_match else "FAIL",
          "FILL_MODE":fill_mode,"CLASSIFICATION":classification
        })

    for ticket in sorted(set(life_open)-set(tickets)):
        mm("LIFECYCLE",ticket,"UNEXPECTED_OPEN","none","present")
    for ticket in sorted(set(life_close)-set(tickets)):
        mm("LIFECYCLE",ticket,"UNEXPECTED_CLOSE","none","present")

    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    write_csv(out/"EXECUTOR_LIFECYCLE02_CHECKS.csv",
      ["TICKET","SIGNAL_ID","SIDE","OPEN_TIME","OPEN_PRICE","TRAIL_UPDATES","SIM_STATUS","SIM_CLOSE_TIME",
       "SIM_REASON","SIM_TRIGGER_LEVEL","SIM_TRIGGER_QUOTE","SIM_TRIGGER_MODE","ACTUAL_STATUS",
       "ACTUAL_CLOSE_TIME","ACTUAL_REASON","ACTUAL_CLOSE_PRICE","TIME_MATCH","REASON_MATCH",
       "FILL_MODE","CLASSIFICATION"],checks)
    write_csv(out/"EXECUTOR_LIFECYCLE02_MISMATCHES.csv",
      ["KIND","KEY","FIELD","EXPECTED","ACTUAL"],mism)

    summary={"block":"EXECUTOR LIFECYCLE 02","status":"PASS" if not mism else "FAIL",
      "scope":"Causal MT4 Open-prices-only lifecycle replay using exact MT4 M5 OHLC ranges, fixed spread and previously-proven trail updates. Broker fill price and money PnL remain captured evidence.",
      "counts":{"queue_signals":len(queue),"opened_tickets":len(tickets),
                "lifecycle_open_events":len(life_open),"lifecycle_close_events":len(life_close),
                "matched_lifecycle_closes":matched,"forced_test_end_closes":forced_end,
                "ambiguous_range_bars":ambiguous,"mismatches":len(mism)},
      "close_reason_distribution":dict(sorted(reasons.items())),
      "fill_mode_distribution":dict(sorted(fill_modes.items())),
      "trigger_mode_distribution":dict(sorted(trigger_modes.items())),
      "parameters":{"spread_points":spread_points,
                    "execution_model":"MT4 Open prices only / M5 with tester-managed intrabar SL/TP range checks"}}
    (out/"EXECUTOR_LIFECYCLE02_SUMMARY.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["EXECUTOR LIFECYCLE 02",f"STATUS: {summary['status']}",
      f"OPENED TICKETS: {len(tickets)}",f"LIFECYCLE OPEN/CLOSE: {len(life_open)}/{len(life_close)}",
      f"MATCHED CLOSES: {matched}/{len(tickets)}",f"FORCED TEST-END CLOSES: {forced_end}",
      f"AMBIGUOUS RANGE BARS: {ambiguous}",f"MISMATCHES: {len(mism)}",
      f"CLOSE REASONS: {dict(sorted(reasons.items()))}",
      f"FILL MODES: {dict(sorted(fill_modes.items()))}",
      f"TRIGGER MODES: {dict(sorted(trigger_modes.items()))}"]
    (out/"EXECUTOR_LIFECYCLE02_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
    return 0 if not mism else 2

def selftest():
    with tempfile.TemporaryDirectory() as td:
        p=Path(td);m5p=p/"XAUUSD5.hst"
        hdr=HST_HEADER.pack(401,b"(C) MetaQuotes Software Corp.".ljust(64,b"\0"),
            b"XAUUSD".ljust(12,b"\0"),5,2,0,0,*([0]*13))
        bars=[
          HST_REC.pack(1000,100.00,99.80,100.20,100.00,100,20,0),
          HST_REC.pack(1300,100.00,99.70,101.00,100.50,100,20,0),
          HST_REC.pack(1600,101.00,100.50,102.50,102.00,100,20,0),
          HST_REC.pack(1900,101.00,100.80,101.20,101.00,100,20,0)]
        m5p.write_bytes(hdr+b"".join(bars))
        q=p/"q.csv";e=p/"e.csv";l=p/"l.csv";out=p/"out"
        qf=["SIGNAL_ID","CREATED_AT","SYMBOL","DECISION_TIME","SIDE","ENTRY_REFERENCE",
            "STOP_PRICE","TARGET_PRICE","RR","SIGNAL_NAME","DECISION_TF","HTP_TF"]
        write_csv(q,qf,[
          {"SIGNAL_ID":"A","CREATED_AT":"1000","SYMBOL":"XAUUSD","DECISION_TIME":"900","SIDE":"SHORT",
           "ENTRY_REFERENCE":"100.00","STOP_PRICE":"105.00","TARGET_PRICE":"95.00","RR":"1","SIGNAL_NAME":"X","DECISION_TF":"60","HTP_TF":"240"},
          {"SIGNAL_ID":"B","CREATED_AT":"1900","SYMBOL":"XAUUSD","DECISION_TIME":"1800","SIDE":"SHORT",
           "ENTRY_REFERENCE":"101.00","STOP_PRICE":"105.00","TARGET_PRICE":"95.00","RR":"1","SIGNAL_NAME":"X","DECISION_TF":"60","HTP_TF":"240"}])
        ef=["SIGNAL_ID","SERVER_TIME","ACTION","REASON","SYMBOL","DECISION_TIME","SIDE","LOTS","PRICE","SL","TP",
            "RR_CURRENT","PROJECTED_MARGIN_LEVEL_PCT","TICKET","ERROR"]
        write_csv(e,ef,[
          {"SIGNAL_ID":"A","SERVER_TIME":"1000","ACTION":"ORDER_OPENED","REASON":"ORDER_OPENED","SYMBOL":"XAUUSD","DECISION_TIME":"900","SIDE":"SHORT","LOTS":"0.1","PRICE":"100.00","SL":"105.00","TP":"95.00","RR_CURRENT":"1","PROJECTED_MARGIN_LEVEL_PCT":"10000","TICKET":"1","ERROR":"0"},
          {"SIGNAL_ID":"","SERVER_TIME":"1300","ACTION":"TRAIL_UPDATED","REASON":"TRAIL_UPDATED","SYMBOL":"XAUUSD","DECISION_TIME":"0","SIDE":"SHORT","LOTS":"0.1","PRICE":"100.20","SL":"102.00","TP":"95.00","RR_CURRENT":"0","PROJECTED_MARGIN_LEVEL_PCT":"0","TICKET":"1","ERROR":"0"},
          {"SIGNAL_ID":"B","SERVER_TIME":"1900","ACTION":"ORDER_OPENED","REASON":"ORDER_OPENED","SYMBOL":"XAUUSD","DECISION_TIME":"1800","SIDE":"SHORT","LOTS":"0.1","PRICE":"101.00","SL":"105.00","TP":"95.00","RR_CURRENT":"1","PROJECTED_MARGIN_LEVEL_PCT":"10000","TICKET":"2","ERROR":"0"}])
        lf=["EVENT","SERVER_TIME","SIGNAL_ID","TICKET","SYMBOL","SIDE","OPEN_TIME","OPEN_PRICE","CLOSE_TIME",
            "CLOSE_PRICE","FINAL_SL","TP","LOTS","PROFIT","SWAP","COMMISSION","CLOSE_REASON"]
        write_csv(l,lf,[
          {"EVENT":"OPEN","SERVER_TIME":"1000","SIGNAL_ID":"A","TICKET":"1","SYMBOL":"XAUUSD","SIDE":"SHORT","OPEN_TIME":"1000","OPEN_PRICE":"100.00","CLOSE_TIME":"0","CLOSE_PRICE":"0","FINAL_SL":"105","TP":"95","LOTS":"0.1","PROFIT":"0","SWAP":"0","COMMISSION":"0","CLOSE_REASON":""},
          {"EVENT":"CLOSE","SERVER_TIME":"1900","SIGNAL_ID":"A","TICKET":"1","SYMBOL":"XAUUSD","SIDE":"SHORT","OPEN_TIME":"1000","OPEN_PRICE":"100.00","CLOSE_TIME":"1900","CLOSE_PRICE":"102.00","FINAL_SL":"102","TP":"95","LOTS":"0.1","PROFIT":"-2","SWAP":"0","COMMISSION":"0","CLOSE_REASON":"SL"},
          {"EVENT":"OPEN","SERVER_TIME":"1900","SIGNAL_ID":"B","TICKET":"2","SYMBOL":"XAUUSD","SIDE":"SHORT","OPEN_TIME":"1900","OPEN_PRICE":"101.00","CLOSE_TIME":"0","CLOSE_PRICE":"0","FINAL_SL":"105","TP":"95","LOTS":"0.1","PROFIT":"0","SWAP":"0","COMMISSION":"0","CLOSE_REASON":""},
          {"EVENT":"CLOSE","SERVER_TIME":"2199","SIGNAL_ID":"B","TICKET":"2","SYMBOL":"XAUUSD","SIDE":"SHORT","OPEN_TIME":"1900","OPEN_PRICE":"101.00","CLOSE_TIME":"2199","CLOSE_PRICE":"101.00","FINAL_SL":"105","TP":"95","LOTS":"0.1","PROFIT":"0","SWAP":"0","COMMISSION":"0","CLOSE_REASON":"OTHER"}])
        rc=analyze(q,e,l,m5p,out,20)
        if rc:
            raise SystemExit("LIFECYCLE02 SELFTEST FAIL")
        s=json.loads((out/"EXECUTOR_LIFECYCLE02_SUMMARY.json").read_text(encoding="utf-8"))
        if s["counts"]["matched_lifecycle_closes"]!=2 or s["counts"]["forced_test_end_closes"]!=1:
            raise SystemExit("LIFECYCLE02 SELFTEST COUNTS FAIL")
    print("EXECUTOR LIFECYCLE 02 SELFTEST PASS")

def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    a=sub.add_parser("analyze")
    a.add_argument("--queue",type=Path,required=True);a.add_argument("--execution",type=Path,required=True)
    a.add_argument("--lifecycle",type=Path,required=True);a.add_argument("--m5",type=Path,required=True)
    a.add_argument("--out",type=Path,required=True);a.add_argument("--spread-points",type=int,default=20)
    x=ap.parse_args()
    if x.cmd=="selftest":
        selftest();return
    raise SystemExit(analyze(x.queue,x.execution,x.lifecycle,x.m5,x.out,x.spread_points))

if __name__=="__main__":main()
