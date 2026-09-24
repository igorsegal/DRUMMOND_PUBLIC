#property strict

#include "DT02_Common.mqh"

enum D2_WATCHER_RUN_MODE
{
   D2_WATCHER_TESTER = 0,
   D2_WATCHER_DEMO   = 1
};

input D2_WATCHER_RUN_MODE InpRunMode=D2_WATCHER_DEMO;
input bool              InpEnableWatcher=true;
input string            InpSymbolsCSV=""; // Пусто = все символы из Market Watch
input string            InpExcludeSymbolsCSV=""; // Например XAUUSD, если DEMO 01 продолжает торговать золотом
input ENUM_TIMEFRAMES   InpDecisionTF=PERIOD_H1;
input ENUM_TIMEFRAMES   InpHTPTF=PERIOD_H4;
input D2_DIRECTION_MODE InpDirectionMode=D2_DIR_SHORT_ONLY;
input double            InpRRMin=0.75;
input double            InpRRMax=1.75;
input int               InpProtectionBufferPoints=1;
input int               InpTimerSeconds=10;
input string            InpQueueFile="DRUMMOND_DEMO02_SIGNALS.csv";
input string            InpAuditFile="DRUMMOND_DEMO02_WATCHER.csv";
input bool              InpClearTesterOutputOnInit=true;

string   g_symbols[];
datetime g_lastClosedDecision[];

string D2_Trim(string s)
{
   s=StringTrimLeft(s);
   s=StringTrimRight(s);
   return(s);
}


bool D2_IsExcluded(string sym)
{
   string src=D2_Trim(InpExcludeSymbolsCSV);
   if(src=="") return(false);
   string parts[];
   int n=StringSplit(src,StringGetCharacter(",",0),parts);
   for(int i=0;i<n;i++)
   {
      string x=D2_Trim(parts[i]);
      if(x==sym) return(true);
   }
   return(false);
}

bool D2_LoadUniverse()
{
   ArrayResize(g_symbols,0);
   ArrayResize(g_lastClosedDecision,0);

   // В Strategy Tester MT4 тестируем только текущий символ.
   // Это намеренно: мультисимвольный live-контур проверяется уже на DEMO/VPS.
   if(InpRunMode==D2_WATCHER_TESTER)
   {
      string sym=Symbol();
      if(sym=="") return(false);
      ArrayResize(g_symbols,1);
      ArrayResize(g_lastClosedDecision,1);
      g_symbols[0]=sym;
      g_lastClosedDecision[0]=0;
      return(true);
   }

   if(StringLen(D2_Trim(InpSymbolsCSV))>0)
   {
      string parts[];
      int n=StringSplit(InpSymbolsCSV,StringGetCharacter(",",0),parts);
      if(n<=0) return(false);
      for(int i=0;i<n;i++)
      {
         string sym=D2_Trim(parts[i]);
         if(sym=="") continue;
         if(D2_IsExcluded(sym)) continue;
         if(!SymbolSelect(sym,true)) continue;
         int k=ArraySize(g_symbols);
         ArrayResize(g_symbols,k+1);
         ArrayResize(g_lastClosedDecision,k+1);
         g_symbols[k]=sym;
         g_lastClosedDecision[k]=iTime(sym,InpDecisionTF,1); // fail-closed: текущий закрытый H1 не переигрываем
      }
   }
   else
   {
      int total=SymbolsTotal(true);
      for(int i=0;i<total;i++)
      {
         string sym=SymbolName(i,true);
         if(sym=="") continue;
         if(D2_IsExcluded(sym)) continue;
         int k=ArraySize(g_symbols);
         ArrayResize(g_symbols,k+1);
         ArrayResize(g_lastClosedDecision,k+1);
         g_symbols[k]=sym;
         g_lastClosedDecision[k]=iTime(sym,InpDecisionTF,1);
      }
   }

   return(ArraySize(g_symbols)>0);
}

int D2_OpenAppendCSV(string filename)
{
   int flags=FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE;
   if(InpRunMode==D2_WATCHER_DEMO) flags|=FILE_COMMON;
   int h=FileOpen(filename,flags,';');
   if(h==INVALID_HANDLE) return(INVALID_HANDLE);
   FileSeek(h,0,SEEK_END);
   return(h);
}

void D2_WriteAuditHeaderIfNeeded(int h)
{
   if(h==INVALID_HANDLE) return;
   if(FileSize(h)>0) return;
   FileWrite(h,
      "SERVER_TIME","SYMBOL","DECISION_TIME","STATUS","REASON",
      "GATES_PASSED","GATES_TOTAL","MATCH_PCT","SIDE",
      "ENTRY_REFERENCE","STOP_PRICE","TARGET_PRICE","RR","SIGNAL_ID");
}

void D2_WriteQueueHeaderIfNeeded(int h)
{
   if(h==INVALID_HANDLE) return;
   if(FileSize(h)>0) return;
   FileWrite(h,
      "SIGNAL_ID","CREATED_AT","SYMBOL","DECISION_TIME","SIDE",
      "ENTRY_REFERENCE","STOP_PRICE","TARGET_PRICE","RR","SIGNAL_NAME",
      "DECISION_TF","HTP_TF");
}

void D2_WatcherAudit(string sym,datetime decisionTime,string status,string reason,
                     int passed,int total,D2TradePlan &plan,string signalId)
{
   int h=D2_OpenAppendCSV(InpAuditFile);
   if(h==INVALID_HANDLE)
   {
      Print("WATCHER: cannot open audit file, err=",GetLastError());
      return;
   }
   D2_WriteAuditHeaderIfNeeded(h);
   double pct=(total>0?100.0*passed/total:0.0);
   FileSeek(h,0,SEEK_END);
   FileWrite(h,
      (int)TimeCurrent(),sym,(int)decisionTime,status,reason,
      passed,total,DoubleToString(pct,2),D2_SideText(plan.side),
      DoubleToString(plan.entry_reference,D2_Digits(sym)),
      DoubleToString(plan.stop_price,D2_Digits(sym)),
      DoubleToString(plan.target_price,D2_Digits(sym)),
      DoubleToString(plan.rr,6),signalId);
   FileFlush(h);
   FileClose(h);
}

bool D2_QueueSignal(D2TradePlan &plan,string signalId)
{
   int h=D2_OpenAppendCSV(InpQueueFile);
   if(h==INVALID_HANDLE)
   {
      Print("WATCHER: cannot open signal queue, err=",GetLastError());
      return(false);
   }
   D2_WriteQueueHeaderIfNeeded(h);
   FileSeek(h,0,SEEK_END);
   FileWrite(h,
      signalId,(int)TimeCurrent(),plan.symbol,(int)plan.decision_time,D2_SideText(plan.side),
      DoubleToString(plan.entry_reference,D2_Digits(plan.symbol)),
      DoubleToString(plan.stop_price,D2_Digits(plan.symbol)),
      DoubleToString(plan.target_price,D2_Digits(plan.symbol)),
      DoubleToString(plan.rr,6),plan.signal_name,(int)InpDecisionTF,(int)InpHTPTF);
   FileFlush(h);
   FileClose(h);
   return(true);
}

void D2_ProcessSymbol(int idx)
{
   if(idx<0 || idx>=ArraySize(g_symbols)) return;
   string sym=g_symbols[idx];
   datetime closed=iTime(sym,InpDecisionTF,1);
   if(closed<=0) return;
   if(closed==g_lastClosedDecision[idx]) return;
   g_lastClosedDecision[idx]=closed;

   D2TradePlan plan;
   D2_ResetPlan(plan);
   string reason="";
   int passed=0,total=0;
   bool full=D2_EvaluateSymbol(sym,InpDecisionTF,InpHTPTF,InpProtectionBufferPoints,
                               InpDirectionMode,InpRRMin,InpRRMax,
                               plan,reason,passed,total);

   if(!full)
   {
      if(plan.decision_time<=0) plan.decision_time=closed;
      D2_WatcherAudit(sym,closed,"NO_TRADE",reason,passed,total,plan,"");
      return;
   }

   string signalId=D2_SignalId(sym,plan.decision_time,plan.side);
   bool queued=D2_QueueSignal(plan,signalId);
   D2_WatcherAudit(sym,closed,queued?"QUEUED":"QUEUE_ERROR",
                   queued?"FULL_PASS":"QUEUE_WRITE_FAILED",passed,total,plan,signalId);

   if(queued)
      Print("WATCHER QUEUED | ",signalId," | ",D2_SideText(plan.side),
            " | RR=",DoubleToString(plan.rr,3));
}

int OnInit()
{
   if(InpRunMode==D2_WATCHER_TESTER)
   {
      if(!IsTesting())
      {
         Print("WATCHER INIT BLOCKED: TESTER_MODE_OUTSIDE_STRATEGY_TESTER");
         return(INIT_FAILED);
      }
      if(InpClearTesterOutputOnInit)
      {
         FileDelete(InpQueueFile,0);
         FileDelete(InpAuditFile,0);
      }
   }
   else
   {
      if(IsTesting())
      {
         Print("WATCHER INIT BLOCKED: DEMO_MODE_INSIDE_STRATEGY_TESTER");
         return(INIT_FAILED);
      }
      if(!IsDemo())
      {
         Print("WATCHER INIT BLOCKED: ACCOUNT_NOT_DEMO");
         return(INIT_FAILED);
      }
      if(InpTimerSeconds<1)
      {
         Print("WATCHER INIT BLOCKED: TIMER_TOO_SMALL");
         return(INIT_FAILED);
      }
   }

   if(!D2_LoadUniverse())
   {
      Print("WATCHER INIT BLOCKED: EMPTY_UNIVERSE");
      return(INIT_FAILED);
   }

   if(InpRunMode==D2_WATCHER_DEMO)
      EventSetTimer(InpTimerSeconds);

   Print("=====================================================");
   Print("DRUMMOND WATCHER DEMO 02 FIX1");
   Print("Run mode      = ",InpRunMode==D2_WATCHER_TESTER?"TESTER":"DEMO");
   Print("Symbols       = ",ArraySize(g_symbols));
   if(InpRunMode==D2_WATCHER_TESTER)
      Print("Tester symbol = ",g_symbols[0]," (single-symbol by design)");
   else
      Print("Excluded      = ",InpExcludeSymbolsCSV);
   Print("Decision TF   = ",InpDecisionTF);
   Print("HTP TF        = ",InpHTPTF);
   Print("Direction     = ",D2_DirectionModeText(InpDirectionMode));
   Print("RR            = [",DoubleToString(InpRRMin,2),", ",DoubleToString(InpRRMax,2),")");
   if(InpRunMode==D2_WATCHER_TESTER)
   {
      Print("Queue         = tester\\files\\",InpQueueFile);
      Print("Audit         = tester\\files\\",InpAuditFile);
      Print("Trading       = DISABLED BY DESIGN");
      Print("Driver        = OnTick (tester)");
   }
   else
   {
      Print("Queue         = Common\\Files\\",InpQueueFile);
      Print("Audit         = Common\\Files\\",InpAuditFile);
      Print("Trading       = DISABLED BY DESIGN");
      Print("Driver        = OnTimer (demo)");
   }
   Print("=====================================================");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   if(InpRunMode==D2_WATCHER_DEMO)
      EventKillTimer();
   Print("WATCHER DEINIT reason=",reason);
}

void OnTimer()
{
   if(InpRunMode!=D2_WATCHER_DEMO) return;
   if(!InpEnableWatcher) return;
   int n=ArraySize(g_symbols);
   for(int i=0;i<n;i++) D2_ProcessSymbol(i);
}

void OnTick()
{
   // В тестере используем OnTick: так тест не зависит от поддержки таймеров
   // и анализирует только текущий тестируемый символ.
   if(InpRunMode!=D2_WATCHER_TESTER) return;
   if(!InpEnableWatcher) return;
   if(ArraySize(g_symbols)!=1) return;
   D2_ProcessSymbol(0);
}
