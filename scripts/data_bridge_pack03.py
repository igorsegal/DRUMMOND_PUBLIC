#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--canonical-root",type=Path,required=True)
    ap.add_argument("--out-root",type=Path,required=True)
    ap.add_argument("--config",type=Path,required=True)
    a=ap.parse_args()

    root=a.canonical_root.resolve()
    if not root.exists():
        raise SystemExit(f"canonical root not found: {root}")

    cfg=json.loads(a.config.read_text(encoding="utf-8"))
    if cfg.get("schema")!="DRUMMOND_DATA_BRIDGE_03_FULL":
        raise SystemExit("unsupported Scale 03 config")
    if cfg.get("mode")!="discover_all":
        raise SystemExit("Scale 03 requires mode=discover_all")

    symbols=sorted((p.name for p in root.iterdir() if p.is_dir()),key=lambda s:(s.casefold(),s))
    if not symbols:
        raise SystemExit("no symbol directories discovered in canonical RAW")

    target=int(cfg.get("target_shard_mb",750))
    if target<=0 or target>=1900:
        raise SystemExit("target_shard_mb must be between 1 and 1899")

    a.out_root.mkdir(parents=True,exist_ok=True)
    selection=a.out_root/"DATA_BRIDGE03_SELECTION.json"
    selection.write_text(json.dumps({
        "schema":"DRUMMOND_DATA_BRIDGE_03_FULL_SELECTION",
        "mode":"explicit",
        "symbols":symbols,
        "target_shard_mb":target,
        "always_include":["XAUUSD"] if "XAUUSD" in symbols else [],
        "source":"all directories discovered directly under canonical RAW",
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    packer=Path(__file__).with_name("data_bridge_pack02.py")
    cmd=[
        sys.executable,str(packer),
        "--canonical-root",str(root),
        "--out-root",str(a.out_root),
        "--config",str(selection),
    ]
    p=subprocess.run(cmd)
    if p.returncode!=0:
        raise SystemExit(p.returncode)

    latest=json.loads((a.out_root/"LATEST.json").read_text(encoding="utf-8"))
    dataset_dir=Path(latest["dataset_dir"])
    manifest=json.loads((dataset_dir/"DATASET_MANIFEST.json").read_text(encoding="utf-8"))
    selected=manifest.get("selection",{}).get("selected_symbols",[])
    declared=[s.get("symbol") for s in manifest.get("symbol_status",[])]

    if selected!=symbols:
        raise SystemExit("Scale 03 full selection mismatch: manifest selected_symbols != canonical directory discovery")
    if declared!=symbols:
        raise SystemExit("Scale 03 full selection mismatch: symbol_status != canonical directory discovery")

    status_counts={}
    for s in manifest["symbol_status"]:
        st=s["status"]
        status_counts[st]=status_counts.get(st,0)+1

    audit={
        "block":"CLOUD DATA BRIDGE SCALE 03 FULL PACK",
        "status":"PASS",
        "dataset_id":manifest["dataset_id"],
        "canonical_symbol_directories":len(symbols),
        "manifest_symbols":len(declared),
        "files":len(manifest["files"]),
        "shards":len(manifest["shards"]),
        "target_shard_mb":target,
        "status_counts":status_counts,
        "full_coverage":True,
    }
    (dataset_dir/"DATASET_FULL03_AUDIT.json").write_text(
        json.dumps(audit,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
    )
    print("")
    print("CLOUD DATA BRIDGE SCALE 03 FULL PACK")
    print("STATUS: PASS")
    print(f"DATASET_ID: {manifest['dataset_id']}")
    print(f"CANONICAL SYMBOL DIRECTORIES: {len(symbols)}")
    print(f"MANIFEST SYMBOLS: {len(declared)}")
    print(f"FILES: {len(manifest['files'])}")
    print(f"SHARDS: {len(manifest['shards'])}")
    print(f"STATUS COUNTS: {status_counts}")
    print("FULL COVERAGE: YES")
    print("DATA BRIDGE SCALE 03 FULL PACK PASS")

if __name__=="__main__":
    main()
