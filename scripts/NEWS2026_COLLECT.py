#!/usr/bin/env python3
"""
NEWS2026_COLLECT — scrape one Forex Factory calendar month in UTC.

The GitHub workflow runs one isolated runner per month to avoid repeated
requests from one IP/session. Selenium/Chrome timezone is forced to UTC before
loading the page. Only scheduled High-impact events for the eight FX
currencies are exported; Actual/Forecast/Previous are deliberately ignored.
"""
import argparse,csv,re,time
from datetime import datetime,timezone
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

CURS={"AUD","CAD","CHF","EUR","GBP","JPY","NZD","USD"}
MONTHS={m.lower():i for i,m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],1)}

def parse_date(text, year):
    # Forex Factory date cell examples: "Thu Jan 1", "Tue Sep 22"
    p=text.strip().split()
    if len(p)<3:
        raise ValueError("bad date "+repr(text))
    mon=MONTHS[p[-2].lower()]
    day=int(p[-1])
    return datetime(year,mon,day,tzinfo=timezone.utc).date()

def parse_clock(text):
    x=text.strip().lower().replace(" ","")
    if not x or x in {"allday","tentative"}:
        return None
    if not re.fullmatch(r"\d{1,2}:\d{2}(am|pm)",x):
        return None
    return datetime.strptime(x,"%I:%M%p").time()

def scrape(month_name, year, out):
    url=f"https://www.forexfactory.com/calendar?month={month_name.lower()}.{year}"
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
            d.execute_cdp_cmd("Emulation.setTimezoneOverride",{"timezoneId":"UTC"})
            d.set_page_load_timeout(45)
            d.get(url)
            WebDriverWait(d,30).until(EC.presence_of_element_located((By.CLASS_NAME,"calendar__table")))
            rows=d.find_elements(By.CSS_SELECTOR,"tr.calendar__row")
            body=d.find_element(By.TAG_NAME,"body").text
            tz_lines=[x.strip() for x in body.splitlines() if "Calendar Time Zone:" in x]
            print("URL",url,"ROWS",len(rows),"TZ",tz_lines[:2])
            if len(rows)<20:
                raise RuntimeError("too few rows")

            current_date=None
            current_time=None
            items=[]
            exact_month=MONTHS[month_name[:3].lower()]

            for row in rows:
                cls=row.get_attribute("class") or ""
                if "day-breaker" in cls:
                    continue

                # Date is present only on the first event row of a day.
                ds=row.find_elements(By.CSS_SELECTOR,".calendar__date")
                if ds:
                    txt=ds[0].text.strip()
                    if txt:
                        current_date=parse_date(txt,year)

                ts=row.find_elements(By.CSS_SELECTOR,".calendar__time")
                if ts:
                    txt=ts[0].text.strip()
                    if txt:
                        current_time=parse_clock(txt)

                if current_date is None or current_time is None:
                    continue
                if current_date.year!=year or current_date.month!=exact_month:
                    continue

                cs=row.find_elements(By.CSS_SELECTOR,".calendar__currency")
                ims=row.find_elements(By.CSS_SELECTOR,".calendar__impact span[title]")
                es=row.find_elements(By.CSS_SELECTOR,".calendar__event-title")
                if not cs or not ims or not es:
                    continue

                cur=cs[0].text.strip().upper()
                impact=(ims[0].get_attribute("title") or "").strip()
                event=es[0].text.strip()
                if cur not in CURS or impact!="High Impact Expected" or not event:
                    continue

                dt=datetime.combine(current_date,current_time,tzinfo=timezone.utc)
                items.append({
                    "UTC_TIME":dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "CURRENCY":cur,
                    "IMPACT":"HIGH",
                    "EVENT":event,
                    "SOURCE_EVENT_ID":row.get_attribute("data-event-id") or ""
                })

            # exact duplicate defense
            uniq={(r["UTC_TIME"],r["CURRENCY"],r["EVENT"]):r for r in items}
            items=sorted(uniq.values(),key=lambda r:(r["UTC_TIME"],r["CURRENCY"],r["EVENT"]))
            if not items:
                raise RuntimeError("no high-impact events parsed")

            out.parent.mkdir(parents=True,exist_ok=True)
            with out.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["UTC_TIME","CURRENCY","IMPACT","EVENT","SOURCE_EVENT_ID"],delimiter=";")
                w.writeheader();w.writerows(items)

            print("PASS",month_name,year,"HIGH",len(items),"FIRST",items[0]["UTC_TIME"],"LAST",items[-1]["UTC_TIME"])
            return
        except Exception as e:
            last=e
            print("ATTEMPT",attempt,"FAIL",type(e).__name__,str(e)[:300])
            time.sleep(20*attempt)
        finally:
            d.quit()
    raise SystemExit(f"scrape failed after retries: {last}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--month",required=True)
    ap.add_argument("--year",type=int,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    scrape(a.month,a.year,a.out)

if __name__=="__main__":
    main()
