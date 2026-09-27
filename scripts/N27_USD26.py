#!/usr/bin/env python3
import csv, glob, sys
from collections import Counter
from datetime import datetime
from pathlib import Path

MONTHS = list(range(1,10))
FIELDS = [
    "UTC_TIME","CURRENCY","IMPACT","EVENT","SOURCE_EVENT_ID",
    "SOURCE_TIME_LOCAL","SOURCE_TIMEZONE","SOURCE_RANGE"
]

def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: N27_USD26.py INPUT_ROOT OUTPUT_CSV")
    root = Path(sys.argv[1])
    out = Path(sys.argv[2])

    files = sorted(root.glob("**/N26_*.csv"))
    if not files:
        raise SystemExit("no N26 CSV files found")

    rows = []
    month_files = {}
    for fn in files:
        part = fn.stem.lower().replace("n26_","")
        aliases = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9}
        if part not in aliases:
            continue
        month = aliases[part]
        if month in month_files:
            raise SystemExit(f"duplicate month artifact: {month}: {month_files[month]} and {fn}")
        month_files[month] = str(fn)

        with fn.open(encoding="utf-8-sig", newline="") as f:
            rr = list(csv.DictReader(f, delimiter=";"))
        if not rr:
            raise SystemExit(f"empty artifact: {fn}")
        for r in rr:
            if r.get("IMPACT") != "HIGH":
                raise SystemExit(f"non-HIGH row in {fn}")
            dt = datetime.fromisoformat(r["UTC_TIME"].replace("Z","+00:00"))
            if dt.year != 2026 or dt.month != month:
                raise SystemExit(f"month mismatch in {fn}: {r['UTC_TIME']}")
            if r.get("CURRENCY") == "USD":
                rows.append(r)

    missing = [m for m in MONTHS if m not in month_files]
    if missing:
        raise SystemExit(f"missing months: {missing}")

    keys = [(r["UTC_TIME"], r["CURRENCY"], r["EVENT"]) for r in rows]
    if len(keys) != len(set(keys)):
        dup = [k for k,n in Counter(keys).items() if n > 1][:10]
        raise SystemExit(f"duplicate USD event keys: {dup}")

    rows.sort(key=lambda r:(r["UTC_TIME"],r["EVENT"]))
    if not rows:
        raise SystemExit("no USD HIGH rows")

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";")
        w.writeheader()
        w.writerows(rows)

    by_month = Counter(datetime.fromisoformat(r["UTC_TIME"].replace("Z","+00:00")).month for r in rows)
    print("N27 USD26 PASS")
    print("FILES", len(files))
    print("MONTHS", sorted(month_files))
    print("USD_HIGH_TOTAL", len(rows))
    print("BY_MONTH", dict(sorted(by_month.items())))
    print("FIRST", rows[0]["UTC_TIME"], rows[0]["EVENT"])
    print("LAST", rows[-1]["UTC_TIME"], rows[-1]["EVENT"])

if __name__ == "__main__":
    main()
