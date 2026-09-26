ND02 — MT4 STRATEGY TESTER
===========================

Назначение
----------
Исторический тест торговой версии NEWS x CROSS-MARKET DISLOCATION.

ВАЖНО: MT4 Strategy Tester тестирует один торговый символ за один прогон.
Поэтому ND02:
- торгует ТОЛЬКО символом, выбранным в Strategy Tester;
- но для расчета сигнала читает весь комплекс из 28 FX-кроссов;
- после этого тот же EA можно прогнать по каждому из 28 символов.

Это правильнее, чем пытаться открыть 28 разных символов из одного MT4-теста:
MT4 tester является односивольным торговым движком.

Файлы
-----
ND02.mq4
ND02.mqh
NEWS26.csv

Куда положить
-------------
ND02.mq4 и ND02.mqh:
MQL4\Experts\ND02\

NEWS26.csv:
Terminal\Common\Files\NEWS26.csv

Сигнал
------
High Impact news
-> ждем 30 минут
-> считаем весь 28-парный M5 cross-market комплекс
-> целевая пара исключена из external strength
-> prior volatility = 288 M5 returns = 24 часа
-> DISLOCATION = EXTERNAL_GAP - TARGET_Z
-> |DISLOCATION| >= 2 sigma
-> D > 0 BUY
-> D < 0 SELL

Торговля
--------
InpTrade=true по умолчанию.
Ордер реально открывается в Strategy Tester через OrderSend().

Лот по умолчанию: 0.01.
SL/TP нет.
Позиция закрывается по времени:
InpHoldMinutes=90.
Исследовательские варианты: 30 или 90 минут.

Одновременно на тестовом символе только одна позиция ND02.

Временная зона
--------------
NEWS26.csv хранит время UTC.

По умолчанию ND02 переводит UTC во время брокера:
зима UTC+2
лето UTC+3
с европейским DST (последнее воскресенье марта/октября).

Параметры:
InpUtcWinterOffsetHours=2
InpUtcSummerOffsetHours=3
InpUseEuropeDST=true

Если сервер брокера использует другую временную зону, эти два значения надо
поставить по брокеру ДО теста.

Как тестировать
---------------
1. Скомпилировать ND02.mq4.
2. Открыть MT4 Strategy Tester.
3. Expert Advisor: ND02.
4. Symbol: любой из 28 FX-кроссов, например EURUSD.
5. Period: M5.
6. Model: Every tick / наиболее точный доступный.
7. Период теста: 2026.
8. InpTrade=true.
9. Lot=0.01.
10. Запустить.

После EURUSD можно тем же ND02 прогнать GBPUSD, USDJPY и остальные пары.

Журнал
------
Common\Files\ND02.csv

Он содержит:
TEST_TIME
EVENT_UTC
EVENT_SERVER
CURRENCY
EVENT
TARGET
TARGET_Z30
EXTERNAL_GAP_Z30
DISLOCATION_Z
ACTION
TICKET
ERROR
BID
ASK
SPREAD_POINTS

Безопасность
------------
По умолчанию ND02 разрешен только внутри Strategy Tester:
InpAllowOutsideTester=false.

То есть случайно поставить его на живой график и открыть ордер нельзя.
