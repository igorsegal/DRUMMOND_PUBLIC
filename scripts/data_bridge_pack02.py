#!/usr/bin/env python3
import argparse,csv,hashlib,json,struct,zipfile
from datetime import datetime,timezone
from pathlib import Path

HDR=struct.Struct("<8siiiidqqqi")
MAGIC=b"XFBAR001"
REQUIRED_TFS=("H1","H4","M5")
PERIODS={"M5":300,"H1":3600,"H4":14400}

def sha256_file(path,chunk=8*1024*1024):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            b=f.read(chunk)
            if not b: break
            h.update(b)
    return h.hexdigest()

def read_header(path):
    p=Path(path)
    with p.open("rb") as f:
        fixed=f.read(HDR.size)
        if len(fixed)!=HDR.size: raise ValueError(f"{p}: short XFBAR header")
        magic,ver,rs,period,digits,point,n,first,last,slen=HDR.unpack(fixed)
        if magic!=MAGIC or ver!=1 or rs!=60: raise ValueError(f"{p}: invalid XFBAR contract")
        if slen<=0 or slen>4096: raise ValueError(f"{p}: invalid symbol length")
        raw=f.read(slen)
        if len(raw)!=slen: raise ValueError(f"{p}: truncated symbol")
        symbol=raw.decode("utf-8")
    expected=HDR.size+slen+n*rs
    if p.stat().st_size!=expected: raise ValueError(f"{p}: file size mismatch")
    return {"symbol":symbol,"period_seconds":period,"digits":digits,"point":point,
            "bar_count":n,"first_time":first,"last_time":last}

def status_for(root,sym):
    folder=root/sym
    missing=[tf for tf in REQUIRED_TFS if not (folder/f"{sym}_{tf}.bin").exists()]
    if not missing: status="READY"
    elif missing==["M5"]: status="SKIP_NO_M5"
    elif "H1" in missing: status="SKIP_NO_H1"
    elif "H4" in missing: status="SKIP_NO_H4"
    else: status="SKIP_INCOMPLETE"
    return status,missing

def discover(root):
    return sorted((p.name for p in root.iterdir() if p.is_dir()),key=lambda s:(s.casefold(),s))

def load_selection(args,root):
    cfg={}
    if args.config:
        cfg=json.loads(Path(args.config).read_text(encoding="utf-8"))
    if args.symbols:
        return [x.strip() for x in args.symbols.split(",") if x.strip()],cfg

    mode=cfg.get("mode","explicit")
    if mode=="explicit":
        syms=[str(x).strip() for x in cfg.get("symbols",[]) if str(x).strip()]
        if not syms: raise ValueError("explicit mode requires symbols")
        return syms,cfg
    if mode!="discover":
        raise ValueError(f"unsupported selection mode: {mode}")

    max_ready=int(cfg.get("max_ready_symbols",args.max_ready_symbols or 0))
    if max_ready<=0: raise ValueError("discover mode requires max_ready_symbols > 0")
    always=[str(x).strip() for x in cfg.get("always_include",[]) if str(x).strip()]
    include_incomplete=int(cfg.get("include_incomplete_symbols",0))

    all_syms=discover(root)
    selected=[];seen=set()
    def add(sym):
        if sym in seen or not (root/sym).is_dir(): return
        selected.append(sym);seen.add(sym)
    for sym in always: add(sym)

    ready_count=sum(1 for s in selected if status_for(root,s)[0]=="READY")
    incomplete_count=sum(1 for s in selected if status_for(root,s)[0]!="READY")
    for sym in all_syms:
        if sym in seen: continue
        st,_=status_for(root,sym)
        if st=="READY" and ready_count<max_ready:
            add(sym);ready_count+=1
        elif st!="READY" and incomplete_count<include_incomplete:
            add(sym);incomplete_count+=1
        if ready_count>=max_ready and incomplete_count>=include_incomplete:
            break
    return selected,cfg

def content_hash(records,symbol_status):
    h=hashlib.sha256()
    for r in sorted(records,key=lambda x:(x["symbol"],x["tf"])):
        h.update(f'{r["symbol"]}|{r["tf"]}|{r["bytes"]}|{r["sha256"]}|{r["period_seconds"]}|{r["bar_count"]}|{r["first_time"]}|{r["last_time"]}\n'.encode())
    for s in sorted(symbol_status,key=lambda x:x["symbol"]):
        h.update(f'STATUS|{s["symbol"]}|{s["status"]}|{",".join(s["missing_tfs"])}\n'.encode())
    return h.hexdigest()

def write_csv(path,fields,rows):
    with Path(path).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--canonical-root",type=Path,required=True)
    ap.add_argument("--out-root",type=Path,required=True)
    ap.add_argument("--config",type=Path)
    ap.add_argument("--symbols",default="")
    ap.add_argument("--max-ready-symbols",type=int,default=0)
    ap.add_argument("--target-shard-mb",type=int,default=400)
    a=ap.parse_args()

    root=a.canonical_root.resolve()
    if not root.exists(): raise SystemExit(f"canonical root not found: {root}")
    symbols,cfg=load_selection(a,root)
    if not symbols: raise SystemExit("no symbols selected")
    target=max(1,int(cfg.get("target_shard_mb",a.target_shard_mb)))*1024*1024

    records=[];symbol_status=[]
    for sym in symbols:
        status,missing=status_for(root,sym)
        folder=root/sym
        for tf in REQUIRED_TFS:
            p=folder/f"{sym}_{tf}.bin"
            if not p.exists(): continue
            h=read_header(p)
            if h["symbol"]!=sym: raise ValueError(f"{p}: header symbol {h['symbol']} != {sym}")
            if h["period_seconds"]!=PERIODS[tf]:
                raise ValueError(f"{p}: period {h['period_seconds']} != {PERIODS[tf]}")
            records.append({"symbol":sym,"tf":tf,"source_path":str(p),"relative_path":f"{sym}/{p.name}",
                            "bytes":p.stat().st_size,"sha256":sha256_file(p),**h})
        symbol_status.append({"symbol":sym,"status":status,"missing_tfs":missing})

    digest=content_hash(records,symbol_status)
    dataset_id=f"DRUMMOND_CANONICAL_{digest[:16].upper()}"
    out=a.out_root.resolve()/dataset_id
    out.mkdir(parents=True,exist_ok=True)

    by_symbol={}
    for r in records: by_symbol.setdefault(r["symbol"],[]).append(r)

    current_symbols=[];current_records=[];current_bytes=0;shards=[];shard_no=1
    def flush():
        nonlocal current_symbols,current_records,current_bytes,shard_no
        if not current_records:return
        name=f"shard_{shard_no:03d}.zip";zp=out/name
        with zipfile.ZipFile(zp,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
            for r in sorted(current_records,key=lambda x:(x["symbol"],x["tf"])):
                z.write(r["source_path"],arcname=r["relative_path"]);r["shard"]=name
        shards.append({"name":name,"bytes":zp.stat().st_size,"sha256":sha256_file(zp),
                       "file_count":len(current_records),"symbols":list(current_symbols),
                       "symbol_count":len(current_symbols),"oversize_symbol_group":current_bytes>target and len(current_symbols)==1})
        current_symbols=[];current_records=[];current_bytes=0;shard_no+=1

    for sym in symbols:
        group=sorted(by_symbol.get(sym,[]),key=lambda x:x["tf"])
        if not group: continue
        group_bytes=sum(int(r["bytes"]) for r in group)
        if current_records and current_bytes+group_bytes>target: flush()
        current_symbols.append(sym);current_records.extend(group);current_bytes+=group_bytes
    flush()

    # Hard invariant: all available required files for one symbol belong to exactly one shard.
    for sym,group in by_symbol.items():
        assigned={r.get("shard") for r in group}
        if len(assigned)!=1: raise RuntimeError(f"symbol split across shards: {sym} -> {assigned}")

    manifest={
      "schema":"DRUMMOND_DATA_BRIDGE_02","schema_version":2,
      "dataset_id":dataset_id,"content_sha256":digest,
      "created_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
      "canonical_root":str(root),"required_tfs":list(REQUIRED_TFS),
      "selection":{"mode":cfg.get("mode","cli"),"selected_symbols":symbols,
                   "max_ready_symbols":cfg.get("max_ready_symbols",a.max_ready_symbols or None),
                   "always_include":cfg.get("always_include",[])},
      "target_shard_bytes":target,"symbol_status":symbol_status,
      "files":[{k:v for k,v in r.items() if k!="source_path"} for r in sorted(records,key=lambda x:(x["symbol"],x["tf"]))],
      "shards":shards,
      "policy":{"source":"canonical RAW only","temp_raw_mirrors":False,
                "missing_m5":"SKIP_NO_M5","archive_compression":"ZIP_STORED",
                "sharding":"SYMBOL_ATOMIC"}
    }
    (out/"DATASET_MANIFEST.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    write_csv(out/"DATASET_MANIFEST.csv",
      ["symbol","tf","relative_path","bytes","sha256","period_seconds","digits","point","bar_count","first_time","last_time","shard"],
      [{k:r[k] for k in ["symbol","tf","relative_path","bytes","sha256","period_seconds","digits","point","bar_count","first_time","last_time","shard"]} for r in manifest["files"]])
    write_csv(out/"DATASET_SYMBOLS.csv",["symbol","status","missing_tfs"],
      [{"symbol":s["symbol"],"status":s["status"],"missing_tfs":"|".join(s["missing_tfs"])} for s in symbol_status])
    write_csv(out/"DATASET_SHARDS.csv",["name","bytes","sha256","file_count","symbol_count","symbols","oversize_symbol_group"],
      [{"name":s["name"],"bytes":s["bytes"],"sha256":s["sha256"],"file_count":s["file_count"],
        "symbol_count":s["symbol_count"],"symbols":"|".join(s["symbols"]),"oversize_symbol_group":s["oversize_symbol_group"]} for s in shards])

    latest={"dataset_id":dataset_id,"dataset_dir":str(out),"release_tag":"dataset02-"+dataset_id.lower()}
    a.out_root.mkdir(parents=True,exist_ok=True)
    (a.out_root/"LATEST.json").write_text(json.dumps(latest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    counts={}
    for s in symbol_status: counts[s["status"]]=counts.get(s["status"],0)+1
    print("CLOUD DATA BRIDGE SCALE 02 PACK")
    print(f"DATASET_ID: {dataset_id}")
    print(f"SELECTED: {len(symbols)}")
    for k in sorted(counts): print(f"{k}: {counts[k]}")
    print(f"FILES: {len(records)}")
    print(f"SHARDS: {len(shards)}")
    print(f"OUTPUT: {out}")
    print("DATA BRIDGE SCALE 02 PACK PASS")

if __name__=="__main__":
    main()
