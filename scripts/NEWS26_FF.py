#!/usr/bin/env python3
"""
NEWS26_FF — one-week Forex Factory scraper with explicit timezone conversion.

Each GitHub job requests exactly one historical week. The page timezone name
is read from HTML, then row timestamps are converted with Python zoneinfo to
UTC including DST. Only the 8 target FX currencies and High Impact Expected
rows are exported. Actual/Forecast/Previous are ignored.
"""
import argparse
import csv
import re
import time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

CURS={"AUD","CAD","CHF","EUR","GBP","JPY","NZD","USD"}
MONTHS={m.lower():i for i,m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],1)}

def ffdate(d):
    return d.strftime("%b").lower()+str(d.day)+"."+str(d.year)

def parse_date(text, fallback_year):
    p=text.strip().split()
    if len(p)<3:
        raise ValueError("bad date "+repr(text))
    mon=MONTHS[p[-2].lower()]
    day=int(re.sub(r"\D","",p[-1]))
    return date(fallback_year,mon,day)

def parse_clock(text):
    x=text.strip().lower().replace(" ","")
    if not x:
        return "SAME"
    if x=="allday" or x=="tentative" or x.startswith("day"):
        return None
    return datetime.strptime(x,"%I:%M%p").time()

def one_week(start,out):
    end=start+timedelta(days=6)
    url=f"https://www.forexfactory.com/calendar?range={ffdate(start)}-{ffdate(end)}"
    last=None

    for attempt in range(1,4):
        opt=webdriver.ChromeOptions()
        opt.add_argument("--headless=new")
        opt.add_argument("--no-sandbox")
        opt.add_argument("--disable-dev-shm-usage")
        opt.add_argument("--disable-gpu")
        opt.add_argument("--window-size=1920,1080")
        opt.add_argument("--lang=en-US")
        opt.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36")

        d=webdriver.Chrome(options=opt)
        try:
            d.set_page_load_timeout(45)
            d.get(url)
            WebDriverWait(d,30).until(
                EC.presence_of_element_located((By.CLASS_NAME,"calendar__table"))
            )

            src=d.page_source
            m=re.search(r"timezone_name\s*:\s*['\"]([^'\"]+)['\"]",src)
            if not m:
                m=re.search(r"['\"]timezone_name['\"]\s*:\s*['\"]([^'\"]+)['\"]",src)
            if not m:
                raise RuntimeError("timezone_name not found")

            tzname=m.group(1)
            zone=ZoneInfo(tzname)

            rows=d.find_elements(By.CSS_SELECTOR,"tr.calendar__row")
            if len(rows)<10:
                raise RuntimeError("too few rows")
            print("URL",url,"ROWS",len(rows),"TZ",tzname)

            cur_date=None
            cur_time=None
            items=[]
            impacts={"red":0,"ora":0,"yel":0,"other":0}

            for row in rows:
                cls=row.get_attribute("class") or ""
                if "day-breaker" in cls:
                    txt=row.text.strip()
                    if txt:
                        try:
                            cur_date=parse_date(txt,start.year)
                        except Exception:
                            pass
                    continue

                event_id=row.get_attribute("data-event-id") or ""
                if not event_id:
                    continue

                ds=row.find_elements(By.CSS_SELECTOR,".calendar__date")
                if ds:
                    txt=ds[0].text.strip()
                    if txt:
                        cur_date=parse_date(txt,start.year)

                ts=row.find_elements(By.CSS_SELECTOR,".calendar__time")
                if ts:
                    txt=ts[0].text.strip()
                    if txt:
                        pc=parse_clock(txt)
                        if pc=="SAME":
                            pass
                        else:
                            cur_time=pc

                if cur_date is None or cur_time is None:
                    continue
                if not (start<=cur_date<=end):
                    continue

                cs=row.find_elements(By.CSS_SELECTOR,".calendar__currency")
                ims=row.find_elements(By.CSS_SELECTOR,".calendar__impact span")
                es=row.find_elements(By.CSS_SELECTOR,".calendar__event-title")
                if not cs or not ims or not es:
                    continue

                icls=ims[0].get_attribute("class") or ""
                if "ff-impact-red" in icls:
                    impacts["red"]+=1
                elif "ff-impact-ora" in icls:
                    impacts["ora"]+=1
                elif "ff-impact-yel" in icls:
                    impacts["yel"]+=1
                else:
                    impacts["other"]+=1

                cur=cs[0].text.strip().upper()
                event=es[0].text.strip()
                if cur not in CURS or "ff-impact-red" not in icls or not event:
                    continue

                local=datetime.combine(cur_date,cur_time,tzinfo=zone)
                utc=local.astimezone(timezone.utc)
                items.append({
                    "UTC_TIME":utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "CURRENCY":cur,
                    "IMPACT":"HIGH",
                    "EVENT":event,
                    "SOURCE_EVENT_ID":event_id,
                    "SOURCE_TZ":tzname
                })

            uniq={(r["UTC_TIME"],r["CURRENCY"],r["EVENT"]):r for r in items}
            items=sorted(
                uniq.values(),
                key=lambda r:(r["UTC_TIME"],r["CURRENCY"],r["EVENT"])
            )

            out.parent.mkdir(parents=True,exist_ok=True)
            with out.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(
                    f,
                    fieldnames=[
                        "UTC_TIME","CURRENCY","IMPACT","EVENT",
                        "SOURCE_EVENT_ID","SOURCE_TZ"
                    ],
                    delimiter=";"
                )
                w.writeheader()
                w.writerows(items)

            print("PASS",start,end,"IMPACTS",impacts,"HIGH8",len(items))
            if items:
                print("FIRST",items[0]["UTC_TIME"],items[0]["CURRENCY"],items[0]["EVENT"])
                print("LAST",items[-1]["UTC_TIME"],items[-1]["CURRENCY"],items[-1]["EVENT"])
            return

        except Exception as e:
            last=e
            print("ATTEMPT",attempt,"FAIL",type(e).__name__,str(e)[:400])
            time.sleep(15*attempt)
        finally:
            d.quit()

    raise SystemExit("week failed: "+repr(last))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start",required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    start=datetime.strptime(a.start,"%Y-%m-%d").date()
    one_week(start,a.out)

if __name__=="__main__":
    main()
