ND01
===========================

Назначение
----------
Первый MT4-адаптер лабораторной конструкции NEWS03/NEWS05.
Это не готовая подтвержденная прибыльная система, а боевой DEMO-прототип.

Что делает EA
-------------
1. Работает с 8 валютами:
   AUD CAD CHF EUR GBP JPY NZD USD

2. Использует все 28 FX-кроссов:
   AUDCAD AUDCHF AUDJPY AUDNZD AUDUSD
   CADCHF CADJPY CHFJPY
   EURAUD EURCAD EURCHF EURGBP EURJPY EURNZD EURUSD
   GBPAUD GBPCAD GBPCHF GBPJPY GBPNZD GBPUSD
   NZDCAD NZDCHF NZDJPY NZDUSD
   USDCAD USDCHF USDJPY

3. После High Impact новости ждет 30 минут.

4. Для каждой пары, содержащей валюту новости:
   - считает 30-минутное движение самой пары;
   - считает внешний cross-market gap по шести третьим валютам;
   - целевая пара в external strength не входит;
   - нормирует движения на предыдущие 24 часа M5;
   - DISLOCATION = external_gap - target_z.

5. Сигнал:
   |DISLOCATION| >= 2 sigma.
   DISLOCATION > 0 -> LONG.
   DISLOCATION < 0 -> SHORT.

6. Выход:
   фиксированное время после входа.
   InpHoldMinutes = 30 или 90.
   По умолчанию 90.

7. На один символ одновременно разрешена только одна позиция данного EA.

Установка
---------
Скопировать папку ND01 в:
MQL4\Experts\ND01\

Файлы:
ND01.mq4
ND01.mqh

Скомпилировать ND01.mq4 в MetaEditor.

EA ставится ТОЛЬКО НА ОДИН график.
Он сам работает со всеми 28 символами.

Важно
-----
Точный исследовательский контракт требует наличия всех 28 FX-кроссов.
EA сам ищет брокерские суффиксы:
EURUSD
EURUSD.s
EURUSDm
и т.п.

Если хотя бы один из 28 символов отсутствует, EA не стартует.
Это сделано специально, чтобы live-формула не отличалась от лабораторной.

Режимы
------
ND_MODE_DISABLED
  Новые сигналы не обрабатываются.

ND_MODE_SIGNAL_ONLY
  Режим по умолчанию.
  Сделки НЕ открываются.
  Сигналы пишутся в журнал.

ND_MODE_DEMO
  Открываются реальные ордера терминала.
  По умолчанию реальный счет заблокирован.

InpAllowRealAccount=false
  НЕ МЕНЯТЬ на первом этапе.

Новостной файл
--------------
EA читает:
Common\Files\NEWS.csv

Формат:
UTC_TIME;CURRENCY;IMPACT;EVENT
2026-09-26T12:30:00Z;USD;HIGH;Example event

Одновременные события одной валюты с одинаковым временем
объединяются в один кластер и обрабатываются один раз.

EA читает ТОЛЬКО impact=HIGH.
Actual / Forecast / Previous ему не нужны.

Журнал
------
Common\Files\ND01.csv

В журнал попадают:
- время события;
- валюта новости;
- целевая пара;
- target Z;
- external gap;
- dislocation;
- направление;
- текущий spread;
- действие;
- ticket / error.

Быстрый smoke-test без Data Bridge
----------------------------------
InpMode = ND_MODE_SIGNAL_ONLY
InpManualSmoke = true
InpManualCurrency = USD

После запуска EA один раз создаст синтетическое событие
"30 минут назад" и прогонит текущий рынок через всю формулу.
Ордера в SIGNAL_ONLY не открываются.

После проверки:
InpManualSmoke = false

Для DEMO
--------
1. Убедиться, что журнал SIGNAL_ONLY корректен.
2. Поставить InpMode = ND_MODE_DEMO.
3. Оставить InpAllowRealAccount = false.
4. InpLots = 0.01.
5. AutoTrading должен быть включен.

Исследовательские параметры
---------------------------
InpDislocationSigma = 2.0
InpDecisionDelayMinutes = 30
InpHoldMinutes = 30 или 90

Изменение этих параметров означает уже другую систему
и должно исследоваться отдельно.
