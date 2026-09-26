#!/usr/bin/env python3
"""
N26 — reliable 2026 Forex Factory High-Impact calendar collector.

Key change vs the failed month scraper:
- collect one month as 7-day historical ranges;
- no dependence on month-page lazy loading;
- keep only scheduled event time/currency/name/impact;
- never use Actual/Forecast/Previous;
- force browser timezone to UTC and record the page timezone text;
- exact deduplication and month-boundary validation.
"""
import argparse,csv,re,time
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

CURS={"AUD","CAD","CHF","EUR","GBP","JPY","NZD","USD"}
MON={"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
     "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
MON_REV={v:k for k,v in MON.items()}

def ff_date(d:date)->str:
    return f"{MON_REV[d.month]}{d.day}.{d.year}"

def parse_date(text:str, year:int):
    # Typical FF date cell/day-breaker: "Mon Jan 5"
    p=text.strip().split()
    for i,x in enumerate(p):
        key=x[:3].lower()
        if key in MON and i+1<len(p):
            day=re.sub(r"\D","",p[i+1])
            if day:
                return date(year,MON[key],int(day))
    raise ValueError(f"bad date text {text!r}")

def parse_clock(text:str):
    x=text.strip().lower().replace(" ","")
    if not x or x in {"allday","tentative"}:
        return None
    if not re.fullmatch(r"\d{1,2}:\d{2}(am|pm)",x):
        return None
    return datetime.strptime(x,"%I:%M%p").time()

def detect_source_timezone(html:str)->str:
    m=re.search(r"timezone_name:\s*['\"]([^'\"]+)['\"]",html)
    if not m:
        raise RuntimeError("Forex Factory timezone_name not found in page HTML")
    tz=m.group(1).strip()
    try:
        ZoneInfo(tz)
    except Exception as e:
        raise RuntimeError(f"unsupported Forex Factory timezone {tz!r}: {e}")
    return tz

def driver():
    opt=webdriver.ChromeOptions()
    opt.add_argument("--headless=new")
    opt.add_argument("--no-sandbox")
    opt.add_argument("--disable-dev-shm-usage")
    opt.add_argument("--disable-gpu")
    opt.add_argument("--window-size=1920,2400")
    opt.add_argument("--lang=en-US")
    opt.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36")
    opt.page_load_strategy="eager"
    d=webdriver.Chrome(options=opt)
    d.execute_cdp_cmd("Emulation.setTimezoneOverride",{"timezoneId":"UTC"})
    d.set_page_load_timeout(35)
    return d

def scrape_range(start:date, end:date):
    url=f"https://www.forexfactory.com/calendar?range={ff_date(start)}-{ff_date(end)}"
    last_err=None

    for attempt in range(1,3):
        d=driver()
        try:
            try:
                d.get(url)
            except Exception as load_err:
                # Chrome may time out on ads/secondary resources after the
                # calendar HTML is already present. Stop loading and inspect.
                print("PAGE_LOAD_WARN",start,end,type(load_err).__name__)
                try:
                    d.execute_script("window.stop();")
                except Exception:
                    pass

            WebDriverWait(d,20).until(
                EC.presence_of_element_located((By.CLASS_NAME,"calendar__table"))
            )
            time.sleep(1.0)

            # Week/range pages should already be complete, but one short scroll
            # protects against viewport-triggered rendering without using month lazy-load.
            d.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.8)
            d.execute_script("window.scrollTo(0, 0)")
            time.sleep(0.3)

            rows=d.find_elements(By.CSS_SELECTOR,"tr.calendar__row")
            source_tz_name=detect_source_timezone(d.page_source)
            source_tz=ZoneInfo(source_tz_name)
            print("RANGE",start,end,"ROWS",len(rows),
                  "SOURCE_TZ",source_tz_name,"URL",d.current_url)

            if len(rows)<5:
                raise RuntimeError(f"too few rows: {len(rows)}")

            current_date=None
            current_time=None
            out=[]

            for row in rows:
                cls=(row.get_attribute("class") or "").lower()

                if "day-breaker" in cls:
                    txt=row.text.strip()
                    if txt:
                        current_date=parse_date(txt,start.year)
                    current_time=None
                    continue

                ds=row.find_elements(By.CSS_SELECTOR,".calendar__date")
                if ds:
                    txt=ds[0].text.strip()
                    if txt:
                        current_date=parse_date(txt,start.year)

                ts=row.find_elements(By.CSS_SELECTOR,".calendar__time")
                if ts:
                    txt=ts[0].text.strip()
                    if txt:
                        parsed=parse_clock(txt)
                        if parsed is not None:
                            current_time=parsed

                if current_date is None or current_time is None:
                    continue
                if not (start <= current_date <= end):
                    continue

                cs=row.find_elements(By.CSS_SELECTOR,".calendar__currency")
                ims=row.find_elements(By.CSS_SELECTOR,".calendar__impact span")
                es=row.find_elements(By.CSS_SELECTOR,".calendar__event-title")
                if not cs or not ims or not es:
                    continue

                cur=cs[0].text.strip().upper()
                title=(ims[0].get_attribute("title") or "").strip()
                klass=(ims[0].get_attribute("class") or "").lower()
                event=es[0].text.strip()

                high=("high impact expected" in title.lower()
                      or "ff-impact-red" in klass)
                if cur not in CURS or not high or not event:
                    continue

                local_dt=datetime.combine(current_date,current_time,tzinfo=source_tz)
                utc_dt=local_dt.astimezone(timezone.utc)
                out.append({
                    "UTC_TIME":utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "CURRENCY":cur,
                    "IMPACT":"HIGH",
                    "EVENT":event,
                    "SOURCE_EVENT_ID":row.get_attribute("data-event-id") or "",
                    "SOURCE_TIME_LOCAL":local_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                    "SOURCE_TIMEZONE":source_tz_name,
                    "SOURCE_RANGE":f"{start.isoformat()}..{end.isoformat()}",
                })

            print("RANGE_PASS",start,end,"HIGH",len(out))
            return out

        except Exception as e:
            last_err=e
            print("RANGE_FAIL",start,end,"attempt",attempt,type(e).__name__,str(e)[:300])
            if attempt<2:
                time.sleep(20)
        finally:
            d.quit()

    raise RuntimeError(f"range {start}..{end} failed: {last_err}")

def month_bounds(year:int, month:int, through:date|None):
    start=date(year,month,1)
    if month==12:
        end=date(year+1,1,1)-timedelta(days=1)
    else:
        end=date(year,month+1,1)-timedelta(days=1)
    if through is not None:
        end=min(end,through)
    if end<start:
        return None,None
    return start,end

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--year",type=int,default=2026)
    ap.add_argument("--month",required=True,choices=list(MON))
    ap.add_argument("--through",default="2026-09-26")
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()

    through=datetime.strptime(a.through,"%Y-%m-%d").date() if a.through else None
    m=MON[a.month]
    m0,m1=month_bounds(a.year,m,through)
    if m0 is None:
        raise SystemExit("month is after --through")

    all_rows=[]
    s=m0
    part=0
    while s<=m1:
        e=min(s+timedelta(days=6),m1)
        part+=1
        rows=scrape_range(s,e)
        all_rows.extend(rows)
        s=e+timedelta(days=1)
        if s<=m1:
            time.sleep(15)

    uniq={}
    for r in all_rows:
        k=(r["UTC_TIME"],r["CURRENCY"],r["EVENT"])
        uniq[k]=r
    rows=sorted(uniq.values(),key=lambda r:(r["UTC_TIME"],r["CURRENCY"],r["EVENT"]))

    if not rows:
        raise SystemExit("no High Impact rows in month")

    # Contract checks
    for r in rows:
        dt=datetime.fromisoformat(r["UTC_TIME"].replace("Z","+00:00"))
        assert dt.year==a.year and dt.month==m
        assert r["CURRENCY"] in CURS and r["IMPACT"]=="HIGH"
        assert r["SOURCE_TIMEZONE"]

    # Independent UTC sanity check. These US releases are conventionally 08:30
    # America/New_York. We do NOT assume the Forex Factory display timezone;
    # instead the page's own timezone_name is used above and the final UTC time
    # must match 08:30 New York for these anchor events.
    anchors={"Non-Farm Employment Change","Unemployment Claims",
             "CPI m/m","Core CPI m/m","PPI m/m","Core PPI m/m"}
    ny=ZoneInfo("America/New_York")
    checked=0
    for r in rows:
        if r["CURRENCY"]=="USD" and r["EVENT"] in anchors:
            got=datetime.fromisoformat(r["UTC_TIME"].replace("Z","+00:00"))
            local_day=got.astimezone(ny).date()
            expected=datetime.combine(local_day,datetime.strptime("08:30","%H:%M").time(),tzinfo=ny).astimezone(timezone.utc)
            if got!=expected:
                raise SystemExit(
                    f"UTC_ANCHOR_FAIL {r['EVENT']} got={got.isoformat()} "
                    f"expected={expected.isoformat()} source_tz={r['SOURCE_TIMEZONE']} "
                    f"source_local={r['SOURCE_TIME_LOCAL']}"
                )
            checked+=1
    if checked==0:
        print("UTC_ANCHOR_WARN no standard USD 08:30 ET anchor in month")
    else:
        print("UTC_ANCHOR_PASS anchors",checked)

    tz_counts={}
    for r in rows:
        tz_counts[r["SOURCE_TIMEZONE"]]=tz_counts.get(r["SOURCE_TIMEZONE"],0)+1
    print("SOURCE_TIMEZONES",tz_counts)

    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=[
            "UTC_TIME","CURRENCY","IMPACT","EVENT","SOURCE_EVENT_ID",
            "SOURCE_TIME_LOCAL","SOURCE_TIMEZONE","SOURCE_RANGE"
        ],delimiter=";")
        w.writeheader();w.writerows(rows)

    print("N26_MONTH_PASS",a.month,a.year,
          "HIGH",len(rows),
          "FIRST",rows[0]["UTC_TIME"],
          "LAST",rows[-1]["UTC_TIME"])
    for cur in sorted(CURS):
        n=sum(r["CURRENCY"]==cur for r in rows)
        if n:
            print("CUR",cur,n)

if __name__=="__main__":
    main()
