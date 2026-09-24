#!/usr/bin/env python3
import argparse,csv,json,subprocess,sys
from pathlib import Path

FIELDS=["SYMBOL","STATUS","DECISIONS","SIGNALS","TP","SL","AMBIGUOUS","OPEN_AT_DATA_END",
        "SIGNAL_SHA256","ERROR"]

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";")
        w.writeheader();w.writerows(rows)

def discover(root,symbols=None):
    root=Path(root)
    if symbols:
        return [(s,root/s) for s in symbols]
    return sorted((p.name,p) for p in root.iterdir() if p.is_dir())

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--symbols",default="")
    ap.add_argument("--direction",choices=("BOTH","SHORT_ONLY","LONG_ONLY"),default="SHORT_ONLY")
    ap.add_argument("--rr-min",type=float,default=.75)
    ap.add_argument("--rr-max",type=float,default=1.75)
    ap.add_argument("--buffer-points",type=int,default=1)
    ap.add_argument("--max-symbols",type=int,default=0)
    a=ap.parse_args()

    script=Path(__file__).with_name("drummond_replay01.py")
    selected=[x.strip() for x in a.symbols.split(",") if x.strip()]
    items=discover(a.data_root,selected or None)
    if a.max_symbols>0:
        items=items[:a.max_symbols]

    rows=[];processed=skipped_no_m5=skipped_other=errors=0
    totals={"decisions":0,"signals":0,"TP":0,"SL":0,"AMBIGUOUS_SAME_M5":0,"OPEN_AT_DATA_END":0}
    for sym,folder in items:
        h1=folder/f"{sym}_H1.bin"
        h4=folder/f"{sym}_H4.bin"
        m5=folder/f"{sym}_M5.bin"
        base={"SYMBOL":sym,"STATUS":"","DECISIONS":"","SIGNALS":"","TP":"","SL":"",
              "AMBIGUOUS":"","OPEN_AT_DATA_END":"","SIGNAL_SHA256":"","ERROR":""}
        if not h1.exists():
            base["STATUS"]="SKIP_NO_H1";skipped_other+=1;rows.append(base);continue
        if not h4.exists():
            base["STATUS"]="SKIP_NO_H4";skipped_other+=1;rows.append(base);continue
        if not m5.exists():
            base["STATUS"]="SKIP_NO_M5";skipped_no_m5+=1;rows.append(base);continue

        sym_out=a.out/"symbols"/sym
        cmd=[sys.executable,str(script),"--fixture",str(folder),"--symbol",sym,"--out",str(sym_out),
             "--direction",a.direction,"--rr-min",str(a.rr_min),"--rr-max",str(a.rr_max),
             "--buffer-points",str(a.buffer_points)]
        p=subprocess.run(cmd,capture_output=True,text=True)
        summary_path=sym_out/f"{sym}_REPLAY_SUMMARY.json"
        if p.returncode!=0 or not summary_path.exists():
            base["STATUS"]="ERROR"
            base["ERROR"]=(p.stderr or p.stdout or "replay failed").strip().replace("\n"," | ")[:1000]
            errors+=1;rows.append(base);continue

        try:
            s=json.loads(summary_path.read_text(encoding="utf-8"))
            c=s["counts"];oc=c.get("static_outcomes",{})
            base.update(
                STATUS="PROCESSED",
                DECISIONS=c.get("decisions",0),
                SIGNALS=c.get("signals",0),
                TP=oc.get("TP",0),
                SL=oc.get("SL",0),
                AMBIGUOUS=oc.get("AMBIGUOUS_SAME_M5",0),
                OPEN_AT_DATA_END=oc.get("OPEN_AT_DATA_END",0),
                SIGNAL_SHA256=s.get("signal_sha256",""))
            if s.get("status")!="PASS":
                base["STATUS"]="ERROR";base["ERROR"]="replay summary status is not PASS";errors+=1
            else:
                processed+=1
                totals["decisions"]+=int(base["DECISIONS"])
                totals["signals"]+=int(base["SIGNALS"])
                for k,col in (("TP","TP"),("SL","SL"),("AMBIGUOUS_SAME_M5","AMBIGUOUS"),
                              ("OPEN_AT_DATA_END","OPEN_AT_DATA_END")):
                    totals[k]+=int(base[col])
        except Exception as e:
            base["STATUS"]="ERROR";base["ERROR"]=f"summary parse: {e}";errors+=1
        rows.append(base)

    a.out.mkdir(parents=True,exist_ok=True)
    write_csv(a.out/"FACTORY01_SYMBOLS.csv",rows)
    summary={
      "block":"CLOUD FACTORY 01",
      "status":"PASS" if processed>0 and errors==0 else "FAIL",
      "data_root":str(a.data_root),
      "parameters":{"direction":a.direction,"rr_min":a.rr_min,"rr_max_exclusive":a.rr_max,
                    "protection_buffer_points":a.buffer_points},
      "counts":{"discovered":len(items),"processed":processed,"skip_no_m5":skipped_no_m5,
                "skip_other_required_tf":skipped_other,"errors":errors,**totals},
      "policy":{"missing_m5":"SKIP_NO_M5, never fail the run",
                "canonical_raw":"caller supplies data root; no TEMP/AppData RAW mirrors are created"}
    }
    (a.out/"FACTORY01_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["CLOUD FACTORY 01",f"STATUS: {summary['status']}",
           f"DISCOVERED: {len(items)}",f"PROCESSED: {processed}",
           f"SKIP_NO_M5: {skipped_no_m5}",f"SKIP_OTHER_TF: {skipped_other}",
           f"ERRORS: {errors}",f"DECISIONS: {totals['decisions']}",f"SIGNALS: {totals['signals']}",
           f"STATIC OUTCOMES TP/SL/AMBIGUOUS/OPEN: {totals['TP']}/{totals['SL']}/{totals['AMBIGUOUS_SAME_M5']}/{totals['OPEN_AT_DATA_END']}"]
    (a.out/"FACTORY01_SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
    raise SystemExit(0 if summary["status"]=="PASS" else 2)

if __name__=="__main__":
    main()
