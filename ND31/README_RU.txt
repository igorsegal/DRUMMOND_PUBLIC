ND31 — DEMO MULTI-SYMBOL + EXECUTION TELEMETRY
================================================

НАЗНАЧЕНИЕ
----------
ND31 — версия ND30 для живого DEMO-наблюдения у брокера.
Торговая логика ND30 НЕ изменена. Добавлена полная телеметрия исполнения.

Замороженные параметры первого запуска:
- High Impact news only
- Decision delay = 30 минут
- Signal threshold = |D| >= 2.0
- Hold = 30 минут
- One open ND31 position per symbol
- Minimum margin level for a new entry = 5000%
- Lots = 0.10
- 44 инструмента
- DEMO ACCOUNT ONLY

ФАЙЛЫ
-----
1. ND31.mq4
   Положить в:
   <MT4 Data Folder>\MQL4\Experts\ND31\ND31.mq4

2. NEWS.csv
   Положить в ОБЩУЮ папку MetaTrader:
   %APPDATA%\MetaQuotes\Terminal\Common\Files\NEWS.csv

3. ND31_EXECUTION.csv
   Создаётся советником автоматически в:
   %APPDATA%\MetaQuotes\Terminal\Common\Files\ND31_EXECUTION.csv

ВАЖНО:
NEWS.csv читается с флагом FILE_COMMON.
Не класть NEWS.csv в MQL4\Files.

УСТАНОВКА
---------
1. В MT4: File -> Open Data Folder.
2. Открыть MQL4\Experts.
3. Создать папку ND31.
4. Скопировать туда ND31.mq4.
5. Открыть ND31.mq4 в MetaEditor.
6. Нажать F7 / Compile.
7. Требование: 0 errors.
8. Вернуться в MT4 и обновить Navigator -> Expert Advisors.
9. Открыть один ликвидный график, рекомендуется M5.
10. В Market Watch желательно Right click -> Show All.
11. Убедиться, что счёт DEMO.
12. Включить AutoTrading.
13. Перетащить ND31 на ОДИН график.
14. На первом запуске параметры не менять.

КОНТРОЛЬ СТАРТА
---------------
В Experts должны появиться строки примерно такого вида:

ND31 DEMO START
mode=TRADE_ONLY instruments=44 missing=...
sigma=2.0 delay=30 hold=30 min_margin_level=5000%
NEWS clusters=...
demo=true
telemetry=ND31_EXECUTION.csv

Если счёт не DEMO:
ND31 INIT FAIL: DEMO ACCOUNT ONLY.
Советник не запускается.

ТЕЛЕМЕТРИЯ
-----------
ND31_EXECUTION.csv пишет отдельные записи для:
- SYMBOL_READY
- SYMBOL_MISSING
- FX_DATA_WAIT
- CALC_FAIL
- NO_SIGNAL
- POSITION_BLOCKED
- MARGIN_BLOCKED
- FREE_MARGIN_BLOCKED
- QUOTE_OR_LOT_FAIL
- ORDER_FAILED
- ORDER_OPENED
- EXIT_QUOTE_FAIL
- EXIT_FAILED
- ORDER_CLOSED

Для каждого кандидата/ордера сохраняются:
- UTC и server time
- время/валюта/название новости
- инструмент
- LONG / SHORT
- TARGET_Z30
- EXTERNAL_Z30
- D
- sigma
- Bid / Ask / Spread
- lot
- margin level
- free margin до входа
- free margin after AccountFreeMarginCheck
- ticket
- broker error
- реальная цена открытия
- реальная цена закрытия
- profit / swap / commission
- фактическое время удержания

ЧТО МЫ БУДЕМ БРАТЬ С VPS
------------------------
Основной файл:
%APPDATA%\MetaQuotes\Terminal\Common\Files\ND31_EXECUTION.csv

По нему будем отдельно проверять:
1. Какие из 44 символов реально существуют у брокера.
2. Где хватает M5-истории.
3. Где формируются сигналы.
4. Какие заявки брокер принимает/отклоняет.
5. Реальный spread.
6. Реальный margin impact.
7. Реальное исполнение цены.
8. Фактический hold.
9. P/L после broker costs.
10. Какие инструменты имеют смысл оставить для дальнейшей DEMO/production-валидации.

БЕЗОПАСНОСТЬ
------------
ND31 жёстко запрещает запуск на REAL account.
Версия исследовательская: SL/TP не используются; выход по времени через 30 минут.
Новый вход блокируется, если текущий Margin Level ниже 5000%.
