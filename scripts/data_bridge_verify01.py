#!/usr/bin/env python3
import argparse,hashlib,json,struct,zipfile
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

def validate_header_bytes(data,record):
    if len(data)<HDR.size: raise ValueError(f'{record["relative_path"]}: short header')
    magic,ver,rs,period,digits,point,n,first,last,slen=HDR.unpack_from(data,0)
    if magic!=MAGIC or ver!=1 or rs!=60:
        raise ValueError(f'{record["relative_path"]}: bad XFBAR contract')
    off=HDR.size+slen
    if slen<=0 or off>len(data): raise ValueError(f'{record["relative_path"]}: bad symbol length')
    sym=data[HDR.size:off].decode("utf-8")
    if sym!=record["symbol"]: raise ValueError(f'{record["relative_path"]}: symbol mismatch')
    if period!=record["period_seconds"] or digits!=record["digits"] or abs(point-record["point"])>1e-15:
        raise ValueError(f'{record["relative_path"]}: header metadata mismatch')
    if n!=record["bar_count"] or first!=record["first_time"] or last!=record["last_time"]:
        raise ValueError(f'{record["relative_path"]}: header range mismatch')
    if len(data)!=off+n*rs: raise ValueError(f'{record["relative_path"]}: byte size mismatch')

def safe_member(name):
    p=Path(name)
    return not p.is_absolute() and ".." not in p.parts and chr(92) not in name

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--package-dir",type=Path,required=True)
    ap.add_argument("--out-root",type=Path,required=True)
    ap.add_argument("--expected-dataset-id",default="")
    a=ap.parse_args()

    pkg=a.package_dir.resolve()
    manifest_path=pkg/"DATASET_MANIFEST.json"
    if not manifest_path.exists(): raise SystemExit(f"missing manifest: {manifest_path}")
    m=json.loads(manifest_path.read_text(encoding="utf-8"))
    if m.get("schema")!="DRUMMOND_DATA_BRIDGE_01" or int(m.get("schema_version",0))!=1:
        raise SystemExit("unsupported Data Bridge manifest")
    if a.expected_dataset_id and m["dataset_id"]!=a.expected_dataset_id:
        raise SystemExit(f'dataset id mismatch: {m["dataset_id"]} != {a.expected_dataset_id}')
    calc=content_hash(m["files"],m["symbol_status"])
    expected_id=f"DRUMMOND_CANONICAL_{calc[:16].upper()}"
    if calc!=m["content_sha256"] or expected_id!=m["dataset_id"]:
        raise SystemExit("dataset content identity mismatch")

    shard_map={s["name"]:s for s in m["shards"]}
    for name,s in shard_map.items():
        p=pkg/name
        if not p.exists(): raise SystemExit(f"missing shard: {name}")
        if p.stat().st_size!=int(s["bytes"]): raise SystemExit(f"shard size mismatch: {name}")
        if sha256_file(p)!=s["sha256"]: raise SystemExit(f"shard SHA256 mismatch: {name}")

    out=a.out_root.resolve()
    if out.exists():
        import shutil
        shutil.rmtree(out)
    out.mkdir(parents=True,exist_ok=True)

    by_shard={}
    for r in m["files"]:
        by_shard.setdefault(r["shard"],[]).append(r)

    verified=0
    for shard,records in sorted(by_shard.items()):
        zp=pkg/shard
        with zipfile.ZipFile(zp,"r") as z:
            names=set(z.namelist())
            expected={r["relative_path"] for r in records}
            if names!=expected:
                extra=sorted(names-expected)[:5];missing=sorted(expected-names)[:5]
                raise SystemExit(f"{shard}: member set mismatch missing={missing} extra={extra}")
            for r in records:
                name=r["relative_path"]
                if not safe_member(name): raise SystemExit(f"unsafe archive member: {name}")
                data=z.read(name)
                if len(data)!=int(r["bytes"]): raise SystemExit(f"{name}: size mismatch")
                if hashlib.sha256(data).hexdigest()!=r["sha256"]: raise SystemExit(f"{name}: SHA256 mismatch")
                validate_header_bytes(data,r)
                dest=out/name
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(data)
                verified+=1

    verified_manifest={
      "dataset_id":m["dataset_id"],"content_sha256":m["content_sha256"],
      "verified_files":verified,"verified_shards":len(m["shards"]),
      "output_root":str(out),"symbol_status":m["symbol_status"]
    }
    (out/"VERIFIED_DATASET.json").write_text(json.dumps(verified_manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("CLOUD DATA BRIDGE 01 VERIFY")
    print(f'DATASET_ID: {m["dataset_id"]}')
    print(f"SHARDS: {len(m['shards'])}")
    print(f"FILES: {verified}")
    print(f"OUTPUT: {out}")
    print("DATA BRIDGE VERIFY PASS")

if __name__=="__main__":
    main()
