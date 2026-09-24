#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
from pathlib import Path

ANCHOR_END = 1787731200
ANCHOR_SIGNALS = 509
ANCHOR_SHA256 = "8411a05a1ca5a4a771c74e3e87d37d2562b370681258ec4b246fa3818f29cd40"

def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()

def normalize_json(path, obj):
    name = path.name
    if name == "FACTORY01_SUMMARY.json" and isinstance(obj, dict):
        obj = dict(obj)
        if "data_root" in obj:
            obj["data_root"] = "<VERIFIED_DATASET_ROOT>"
    if name.endswith("_REPLAY_SUMMARY.json") and isinstance(obj, dict):
        obj = dict(obj)
        data = obj.get("data")
        if isinstance(data, dict):
            clean = {}
            for tf, meta in data.items():
                if isinstance(meta, dict):
                    meta = dict(meta)
                    if "path" in meta:
                        meta["path"] = f"<VERIFIED_DATASET_ROOT>/{obj.get('symbol','SYMBOL')}/{obj.get('symbol','SYMBOL')}_{tf}.bin"
                clean[tf] = meta
            obj["data"] = clean
    return obj

def canonical_bytes(path):
    raw = path.read_bytes()
    if path.suffix.lower() != ".json":
        return raw
    obj = json.loads(raw.decode("utf-8"))
    obj = normalize_json(path, obj)
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

def inventory(root):
    root = Path(root)
    result = {}
    for p in sorted((x for x in root.rglob("*") if x.is_file()), key=lambda x: x.relative_to(root).as_posix()):
        rel = p.relative_to(root).as_posix()
        result[rel] = sha256_bytes(canonical_bytes(p))
    return result

def aggregate_digest(inv):
    h = hashlib.sha256()
    for rel in sorted(inv):
        h.update(f"{rel}|{inv[rel]}\n".encode("utf-8"))
    return h.hexdigest()

def load_verified(path):
    return json.loads((Path(path) / "VERIFIED_DATASET.json").read_text(encoding="utf-8"))

def verified_contract(meta):
    return {
        "dataset_id": meta.get("dataset_id"),
        "content_sha256": meta.get("content_sha256"),
        "verified_files": meta.get("verified_files"),
        "verified_shards": meta.get("verified_shards"),
        "selected_shards": meta.get("selected_shards"),
        "symbols": meta.get("symbols"),
    }

def anchor_contract(run_root):
    p = Path(run_root) / "anchor" / "XAUUSD_REPLAY_SUMMARY.json"
    if not p.exists():
        return None
    s = json.loads(p.read_text(encoding="utf-8"))
    return {
        "status": s.get("status"),
        "end": s.get("common_period", {}).get("end"),
        "signals": s.get("counts", {}).get("signals"),
        "signal_sha256": s.get("signal_sha256"),
    }

def write_csv(path, rows):
    fields = ["PATH", "SHA256_A", "SHA256_B", "STATUS"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        w.writeheader()
        w.writerows(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-a", type=Path, required=True)
    ap.add_argument("--run-b", type=Path, required=True)
    ap.add_argument("--verified-a", type=Path, required=True)
    ap.add_argument("--verified-b", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--expected-dataset-id", required=True)
    a = ap.parse_args()

    for p in (a.run_a, a.run_b, a.verified_a, a.verified_b):
        if not p.exists():
            raise SystemExit(f"missing required path: {p}")

    va = verified_contract(load_verified(a.verified_a))
    vb = verified_contract(load_verified(a.verified_b))
    dataset_ok = va == vb and va.get("dataset_id") == a.expected_dataset_id

    ia = inventory(a.run_a)
    ib = inventory(a.run_b)
    all_paths = sorted(set(ia) | set(ib))
    rows = []
    mismatch_count = 0
    for rel in all_paths:
        ha = ia.get(rel, "")
        hb = ib.get(rel, "")
        status = "MATCH" if ha and hb and ha == hb else ("ONLY_A" if ha and not hb else "ONLY_B" if hb and not ha else "MISMATCH")
        if status != "MATCH":
            mismatch_count += 1
        rows.append({"PATH": rel, "SHA256_A": ha, "SHA256_B": hb, "STATUS": status})

    digest_a = aggregate_digest(ia)
    digest_b = aggregate_digest(ib)
    outputs_ok = mismatch_count == 0 and digest_a == digest_b and len(ia) > 0

    aa = anchor_contract(a.run_a)
    ab = anchor_contract(a.run_b)
    if aa is None and ab is None:
        anchor_ok = True
        anchor_state = "NOT_PRESENT"
    else:
        expected_anchor = {
            "status": "PASS",
            "end": ANCHOR_END,
            "signals": ANCHOR_SIGNALS,
            "signal_sha256": ANCHOR_SHA256,
        }
        anchor_ok = aa == ab == expected_anchor
        anchor_state = "PASS" if anchor_ok else "FAIL"

    status = "PASS" if dataset_ok and outputs_ok and anchor_ok else "FAIL"
    a.out.mkdir(parents=True, exist_ok=True)
    write_csv(a.out / "REPRO02_FILES.csv", rows)

    summary = {
        "block": "CLOUD DATA BRIDGE REPRO 02",
        "status": status,
        "expected_dataset_id": a.expected_dataset_id,
        "dataset_contract_match": dataset_ok,
        "verified_contract_a": va,
        "verified_contract_b": vb,
        "run_a_files": len(ia),
        "run_b_files": len(ib),
        "file_mismatches": mismatch_count,
        "normalized_digest_a": digest_a,
        "normalized_digest_b": digest_b,
        "outputs_match": outputs_ok,
        "anchor_state": anchor_state,
        "anchor_a": aa,
        "anchor_b": ab,
        "normalization_policy": {
            "FACTORY01_SUMMARY.json": ["data_root"],
            "*_REPLAY_SUMMARY.json": ["data.*.path"],
            "all_other_files": "byte-for-byte SHA256",
        },
    }
    (a.out / "REPRO02_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "CLOUD DATA BRIDGE REPRO 02",
        f"STATUS: {status}",
        f"DATASET_ID: {a.expected_dataset_id}",
        f"DATASET CONTRACT MATCH: {dataset_ok}",
        f"RUN A FILES: {len(ia)}",
        f"RUN B FILES: {len(ib)}",
        f"FILE MISMATCHES: {mismatch_count}",
        f"DIGEST A: {digest_a}",
        f"DIGEST B: {digest_b}",
        f"OUTPUTS MATCH: {outputs_ok}",
        f"FROZEN XAUUSD ANCHOR: {anchor_state}",
    ]
    (a.out / "REPRO02_SUMMARY.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    if status != "PASS":
        raise SystemExit(2)
    print("CLOUD DATA BRIDGE REPRO 02 PASS")

if __name__ == "__main__":
    main()
