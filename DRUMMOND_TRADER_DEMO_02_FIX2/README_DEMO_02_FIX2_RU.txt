DRUMMOND TRADER DEMO 02 FIX2
============================

ИСПРАВЛЕНИЕ FIX2
----------------
По журналу второго теста Executor все 29 сигналов дошли до своего исторического времени,
но были заблокированы причиной SYMBOL_SELECT_FAILED.

Причина: в FIX1 Executor безусловно вызывал SymbolSelect(sym,true).
В MT4 Strategy Tester тестируемый символ уже задаётся самим тестером, а SymbolSelect()
может вернуть false даже для этого текущего символа.

FIX2:
- в режиме TESTER SymbolSelect() больше не вызывается;
- в TESTER разрешён только текущий Symbol() тестера;
- если очередь содержит другой символ, причина будет TESTER_SYMBOL_MISMATCH;
- в режиме DEMO старое поведение сохранено: SymbolSelect() и MODE_TRADEALLOWED проверяются;
- InpOnePositionPerSymbol по умолчанию = false: число позиций ограничивается не счётчиком,
  а маржинальным шлюзом InpMinProjectedMarginLevelPct = 5000%;
- Watcher не менялся: его FIX1 уже прошёл тест.

ПОВТОРНЫЙ ТЕСТ EXECUTOR
-----------------------
Strategy Tester MT4:
- Expert: DrummondExecutor_DEMO_02
- Symbol: XAUUSD
- Period: M5
- период: 30.03.2026 -> 04.07.2026
- InpRunMode = D2_EXECUTOR_TESTER
- InpEnableTesterTrading = true
- InpEnableDemoTrading = false
- InpMinProjectedMarginLevelPct = 5000
- InpOnePositionPerSymbol = false
- InpSignalMaxAgeMinutes = 15

В tester\files должен лежать файл сигналов, созданный уже прошедшим Watcher:
DRUMMOND_DEMO02_SIGNALS.csv

Результат Executor:
DRUMMOND_DEMO02_EXECUTION.csv

LIVE/DEMO НА VPS
----------------
Watcher:
- InpRunMode = D2_WATCHER_DEMO
- InpEnableWatcher = true

Executor:
- InpRunMode = D2_EXECUTOR_DEMO
- InpEnableDemoTrading = true
- InpEnableTesterTrading = false
- InpMinProjectedMarginLevelPct = 5000
- InpOnePositionPerSymbol = false

В DEMO оба агента используют Terminal\Common\Files.
