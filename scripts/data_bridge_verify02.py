#!/usr/bin/env python3
import argparse,hashlib,json,struct,zipfile,shutil
from pathlib import Path

HDR=struct.Struct("<8siiiidqqqi")
MAGIC=b"XFBAR001"

def sha256_file(path,chunk=8*1024*1024):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            b=f.read(chunk)
            if not b: break
            h.update(b)
    return h.hexdigest()

def content_hash(records,symbol_status):
    h=hashlib.sha256()
    for r in sorted(records,key=lambda x:(x["symbol"],x["tf"])):
        h.update(f'{r["symbol"]}|{r["tf"]}|{r["bytes"]}|{r["sha256"]}|{r["period_seconds"]}|{r["bar_count"]}|{r["first_time"]}|{r["last_time"]}\n'.encode())
    for s in sorted(symbol_status,key=lambda x:x["symbol"]):
        h.update(f'STATUS|{s["symbol"]}|{s["status"]}|{",".join(s["missing_tfs"])}\n'.encode())
    return h.hexdigest()

def validate_header(data,r):
    if len(data)<HDR.size: raise ValueError(f'{r["relative_path"]}: short header')
    magic,ver,rs,period,digits,point,n,first,last,slen=HDR.unpack_from(data,0)
    if magic!=MAGIC or ver!=1 or rs!=60: raise ValueError(f'{r["relative_path"]}: bad XFBAR contract')
    off=HDR.size+slen
    if slen<=0 or off>len(data): raise ValueError(f'{r["relative_path"]}: bad symbol length')
    sym=data[HDR.size:off].decode("utf-8")
    if sym!=r["symbol"]: raise ValueError(f'{r["relative_path"]}: symbol mismatch')
    if period!=r["period_seconds"] or digits!=r["digits"] or abs(point-r["point"])>1e-15:
        raise ValueError(f'{r["relative_path"]}: header metadata mismatch')
    if n!=r["bar_count"] or first!=r["first_time"] or last!=r["last_time"]:
        raise ValueError(f'{r["relative_path"]}: header range mismatch')
    if len(data)!=off+n*rs: raise ValueError(f'{r["relative_path"]}: byte size mismatch')

def safe_member(name):
    p=Path(name)
    return not p.is_absolute() and ".." not in p.parts and chr(92) not in name

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--package-dir",type=Path,required=True)
    ap.add_argument("--out-root",type=Path,required=True)
    ap.add_argument("--expected-dataset-id",default="")
    ap.add_argument("--shard",default="",help="Verify/extract only one shard; manifest still covers whole dataset")
    ap.add_argument("--manifest-only",action="store_true")
    a=ap.parse_args()

    pkg=a.package_dir.resolve();mp=pkg/"DATASET_MANIFEST.json"
    if not mp.exists(): raise SystemExit(f"missing manifest: {mp}")
    m=json.loads(mp.read_text(encoding="utf-8"))
    if m.get("schema")!="DRUMMOND_DATA_BRIDGE_02" or int(m.get("schema_version",0))!=2:
        raise SystemExit("unsupported Data Bridge 02 manifest")
    if a.expected_dataset_id and m["dataset_id"]!=a.expected_dataset_id:
        raise SystemExit(f'dataset id mismatch: {m["dataset_id"]} != {a.expected_dataset_id}')
    calc=content_hash(m["files"],m["symbol_status"])
    expected=f"DRUMMOND_CANONICAL_{calc[:16].upper()}"
    if calc!=m["content_sha256"] or expected!=m["dataset_id"]:
        raise SystemExit("dataset content identity mismatch")

    # Verify symbol atomicity from manifest before touching archives.
    shards_by_symbol={}
    for r in m["files"]:
        shards_by_symbol.setdefault(r["symbol"],set()).add(r["shard"])
    split={s:sorted(x) for s,x in shards_by_symbol.items() if len(x)>1}
    if split: raise SystemExit(f"symbol split across shards: {split}")

    if a.manifest_only:
        print("DATA BRIDGE SCALE 02 MANIFEST PASS")
        print(f'DATASET_ID: {m["dataset_id"]}')
        print(f'SHARDS: {len(m["shards"])}')
        print(f'SYMBOLS: {len(m["symbol_status"])}')
        return

    shard_map={s["name"]:s for s in m["shards"]}
    selected=[a.shard] if a.shard else sorted(shard_map)
    for name in selected:
        if name not in shard_map: raise SystemExit(f"unknown shard: {name}")
        p=pkg/name;s=shard_map[name]
        if not p.exists(): raise SystemExit(f"missing shard: {name}")
        if p.stat().st_size!=int(s["bytes"]): raise SystemExit(f"shard size mismatch: {name}")
        if sha256_file(p)!=s["sha256"]: raise SystemExit(f"shard SHA256 mismatch: {name}")

    out=a.out_root.resolve()
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True,exist_ok=True)

    by_shard={}
    for r in m["files"]: by_shard.setdefault(r["shard"],[]).append(r)
    verified=0;symbols=set()
    for shard in selected:
        records=by_shard.get(shard,[])
        with zipfile.ZipFile(pkg/shard,"r") as z:
            names=set(z.namelist());expected_names={r["relative_path"] for r in records}
            if names!=expected_names:
                raise SystemExit(f"{shard}: archive member set mismatch")
            for r in records:
                name=r["relative_path"]
                if not safe_member(name): raise SystemExit(f"unsafe member: {name}")
                data=z.read(name)
                if len(data)!=int(r["bytes"]): raise SystemExit(f"{name}: size mismatch")
                if hashlib.sha256(data).hexdigest()!=r["sha256"]: raise SystemExit(f"{name}: SHA256 mismatch")
                validate_header(data,r)
                dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
                verified+=1;symbols.add(r["symbol"])

    meta={"dataset_id":m["dataset_id"],"content_sha256":m["content_sha256"],
          "verified_files":verified,"verified_shards":len(selected),"selected_shards":selected,
          "symbols":sorted(symbols),"output_root":str(out)}
    (out/"VERIFIED_DATASET.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("CLOUD DATA BRIDGE SCALE 02 VERIFY")
    print(f'DATASET_ID: {m["dataset_id"]}')
    print(f'SHARDS: {len(selected)}')
    print(f'FILES: {verified}')
    print(f'SYMBOLS: {len(symbols)}')
    print("DATA BRIDGE SCALE 02 VERIFY PASS")

if __name__=="__main__":
    main()
