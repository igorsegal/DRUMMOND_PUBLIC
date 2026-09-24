#property strict

#include <DT02_Common.mqh>

// DRUMMOND C01 FORWARD SHADOW 14
// Forward-only DEMO capture. No orders, no queue, no historical replay.
// Frozen research rule:
//   LONG base signal AND entry_reference < decision_pldot
// Equivalent to ENTRY_PLDOT_R < 0 because initial risk is strictly positive.

input bool            InpEnableCapture=true;
input string          InpSymbolsCSV="";
input string          InpExcludeSymbolsCSV="";
input ENUM_TIMEFRAMES InpDecisionTF=PERIOD_H1;
input ENUM_TIMEFRAMES InpHTPTF=PERIOD_H4;
input double          InpRRMin=0.75;
input double          InpRRMax=1.75;
input int             InpProtectionBufferPoints=1;
input int             InpTimerSeconds=10;
input string          InpCaptureFile="DRUMMOND_C01_FORWARD14.csv";
input string          InpAuditFile="DRUMMOND_C01_FORWARD14_AUDIT.csv";

#define C01_FROZEN_SHA "a9a00478647d73e147ee0c7e7a063adc5b0fe96b97d403b81af49b3937a57b3e"

string   g_c01_symbols[];
datetime g_c01_lastClosedDecision[];

string C01_Trim(string s)
{
   s=StringTrimLeft(s);
   s=StringTrimRight(s);
   return(s);
}

bool C01_IsExcluded(string sym)
{
   string src=C01_Trim(InpExcludeSymbolsCSV);
   if(src=="") return(false);
   string parts[];
   int n=StringSplit(src,StringGetCharacter(",",0),parts);
   for(int i=0;i<n;i++)
   {
      string x=C01_Trim(parts[i]);
      if(x==sym) return(true);
   }
   return(false);
}

bool C01_LoadUniverse()
{
   ArrayResize(g_c01_symbols,0);
   ArrayResize(g_c01_lastClosedDecision,0);

   if(StringLen(C01_Trim(InpSymbolsCSV))>0)
   {
      string parts[];
      int n=StringSplit(InpSymbolsCSV,StringGetCharacter(",",0),parts);
      if(n<=0) return(false);
      for(int i=0;i<n;i++)
      {
         string sym=C01_Trim(parts[i]);
         if(sym=="" || C01_IsExcluded(sym)) continue;
         if(!SymbolSelect(sym,true)) continue;
         int k=ArraySize(g_c01_symbols);
         ArrayResize(g_c01_symbols,k+1);
         ArrayResize(g_c01_lastClosedDecision,k+1);
         g_c01_symbols[k]=sym;
         // Forward purity: never replay the currently closed H1 on attach.
         g_c01_lastClosedDecision[k]=iTime(sym,InpDecisionTF,1);
      }
   }
   else
   {
      int total=SymbolsTotal(true);
      for(int i=0;i<total;i++)
      {
         string sym=SymbolName(i,true);
         if(sym=="" || C01_IsExcluded(sym)) continue;
         int k=ArraySize(g_c01_symbols);
         ArrayResize(g_c01_symbols,k+1);
         ArrayResize(g_c01_lastClosedDecision,k+1);
         g_c01_symbols[k]=sym;
         // Forward purity: never replay the currently closed H1 on attach.
         g_c01_lastClosedDecision[k]=iTime(sym,InpDecisionTF,1);
      }
   }
   return(ArraySize(g_c01_symbols)>0);
}

int C01_OpenAppendCSV(string filename)
{
   int flags=FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON;
   int h=FileOpen(filename,flags,';');
   if(h==INVALID_HANDLE) return(INVALID_HANDLE);
   FileSeek(h,0,SEEK_END);
   return(h);
}

void C01_WriteCaptureHeaderIfNeeded(int h)
{
   if(h==INVALID_HANDLE || FileSize(h)>0) return;
   FileWrite(h,
      "SERVER_TIME","SYMBOL","DECISION_TIME","SIGNAL_ID","SIDE",
      "ENTRY_REFERENCE","DECISION_PLDOT","INITIAL_RISK","ENTRY_PLDOT_R",
      "STOP_PRICE","TARGET_PRICE","RR","FROZEN_SHA256");
}

void C01_WriteAuditHeaderIfNeeded(int h)
{
   if(h==INVALID_HANDLE || FileSize(h)>0) return;
   FileWrite(h,
      "SERVER_TIME","SYMBOL","DECISION_TIME","SIGNAL_ID","STATUS",
      "ENTRY_REFERENCE","DECISION_PLDOT","INITIAL_RISK","ENTRY_PLDOT_R",
      "STOP_PRICE","TARGET_PRICE","RR","FROZEN_SHA256");
}

bool C01_WriteRow(string filename,bool capture,D2TradePlan &plan,string signalId,string status,double risk,double feature)
{
   int h=C01_OpenAppendCSV(filename);
   if(h==INVALID_HANDLE)
   {
      Print("C01 FORWARD: cannot open ",filename,", err=",GetLastError());
      return(false);
   }

   if(capture) C01_WriteCaptureHeaderIfNeeded(h);
   else        C01_WriteAuditHeaderIfNeeded(h);

   int d=D2_Digits(plan.symbol);
   FileSeek(h,0,SEEK_END);
   if(capture)
   {
      FileWrite(h,
         (int)TimeCurrent(),plan.symbol,(int)plan.decision_time,signalId,"LONG",
         DoubleToString(plan.entry_reference,d),
         DoubleToString(plan.decision_pldot,d),
         DoubleToString(risk,d),
         DoubleToString(feature,10),
         DoubleToString(plan.stop_price,d),
         DoubleToString(plan.target_price,d),
         DoubleToString(plan.rr,6),
         C01_FROZEN_SHA);
   }
   else
   {
      FileWrite(h,
         (int)TimeCurrent(),plan.symbol,(int)plan.decision_time,signalId,status,
         DoubleToString(plan.entry_reference,d),
         DoubleToString(plan.decision_pldot,d),
         DoubleToString(risk,d),
         DoubleToString(feature,10),
         DoubleToString(plan.stop_price,d),
         DoubleToString(plan.target_price,d),
         DoubleToString(plan.rr,6),
         C01_FROZEN_SHA);
   }
   FileFlush(h);
   FileClose(h);
   return(true);
}

void C01_ProcessSymbol(int idx)
{
   if(idx<0 || idx>=ArraySize(g_c01_symbols)) return;

   string sym=g_c01_symbols[idx];
   datetime closed=iTime(sym,InpDecisionTF,1);
   if(closed<=0) return;
   if(closed==g_c01_lastClosedDecision[idx]) return;

   // Advance first: fail-closed, never process this decision twice.
   g_c01_lastClosedDecision[idx]=closed;

   D2TradePlan plan;
   D2_ResetPlan(plan);
   string reason="";
   int passed=0,total=0;

   // Frozen candidate is LONG only.
   bool full=D2_EvaluateSymbol(sym,InpDecisionTF,InpHTPTF,InpProtectionBufferPoints,
                               D2_DIR_LONG_ONLY,InpRRMin,InpRRMax,
                               plan,reason,passed,total);
   if(!full) return;

   double risk=MathAbs(plan.entry_reference-plan.stop_price);
   if(risk<=0.0 || plan.decision_pldot<=0.0) return;

   double entryPLdotR=(plan.entry_reference-plan.decision_pldot)/risk;
   string signalId=D2_SignalId(sym,plan.decision_time,plan.side);

   // EXACT frozen C01 condition. Do not optimize or add another filter here.
   bool c01=(plan.side==D2_SIDE_LONG && entryPLdotR<0.0);
   C01_WriteRow(InpAuditFile,false,plan,signalId,c01?"C01_MATCH":"C01_REJECT",risk,entryPLdotR);

   if(!c01) return;

   if(C01_WriteRow(InpCaptureFile,true,plan,signalId,"C01_MATCH",risk,entryPLdotR))
      Print("C01 FORWARD MATCH | ",signalId,
            " | entryPLdotR=",DoubleToString(entryPLdotR,6),
            " | RR=",DoubleToString(plan.rr,3));
}

int OnInit()
{
   // Forward shadow is intentionally unavailable in Strategy Tester.
   if(IsTesting())
   {
      Print("C01 FORWARD INIT BLOCKED: STRATEGY_TESTER_FORBIDDEN");
      return(INIT_FAILED);
   }
   if(!IsDemo())
   {
      Print("C01 FORWARD INIT BLOCKED: ACCOUNT_NOT_DEMO");
      return(INIT_FAILED);
   }
   if(InpTimerSeconds<1)
   {
      Print("C01 FORWARD INIT BLOCKED: TIMER_TOO_SMALL");
      return(INIT_FAILED);
   }
   if(!C01_LoadUniverse())
   {
      Print("C01 FORWARD INIT BLOCKED: EMPTY_UNIVERSE");
      return(INIT_FAILED);
   }

   EventSetTimer(InpTimerSeconds);

   Print("=====================================================");
   Print("DRUMMOND C01 FORWARD SHADOW 14");
   Print("Mode          = DEMO FORWARD ONLY");
   Print("Symbols       = ",ArraySize(g_c01_symbols));
   Print("Decision TF   = ",InpDecisionTF);
   Print("HTP TF        = ",InpHTPTF);
   Print("RR            = [",DoubleToString(InpRRMin,2),", ",DoubleToString(InpRRMax,2),")");
   Print("Frozen rule   = LONG && entry_reference < decision_pldot");
   Print("Frozen SHA256 = ",C01_FROZEN_SHA);
   Print("Capture       = Common\\Files\\",InpCaptureFile);
   Print("Audit         = Common\\Files\\",InpAuditFile);
   Print("Trading       = DISABLED BY DESIGN");
   Print("History replay= DISABLED BY DESIGN");
   Print("=====================================================");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("C01 FORWARD DEINIT reason=",reason);
}

void OnTimer()
{
   if(!InpEnableCapture) return;
   for(int i=0;i<ArraySize(g_c01_symbols);i++)
      C01_ProcessSymbol(i);
}

void OnTick()
{
   // No tick-driven historical/tester path by design.
}
