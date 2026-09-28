#!/usr/bin/env python3
import csv
from datetime import date, timedelta
from pathlib import Path
from N26 import scrape_range

START=date(2026,9,28)
END=date(2026,10,4)
OUT=Path("out/ND31_NEWS.csv")

rows=[]
s=START
while s<=END:
    e=min(s+timedelta(days=6),END)
    rows.extend(scrape_range(s,e))
    s=e+timedelta(days=1)

uniq={}
for r in rows:
    k=(r["UTC_TIME"],r["CURRENCY"],r["EVENT"])
    uniq[k]=r
rows=sorted(uniq.values(),key=lambda r:(r["UTC_TIME"],r["CURRENCY"],r["EVENT"]))

OUT.parent.mkdir(parents=True,exist_ok=True)
with OUT.open("w",encoding="utf-8",newline="") as f:
    w=csv.writer(f,delimiter=";")
    w.writerow(["UTC_TIME","CURRENCY","IMPACT","EVENT"])
    for r in rows:
        w.writerow([r["UTC_TIME"],r["CURRENCY"],"HIGH",r["EVENT"]])

print("ND31_NEWS_PASS",len(rows))
for r in rows:
    print("NEWS",r["UTC_TIME"],r["CURRENCY"],r["EVENT"],sep=";")
