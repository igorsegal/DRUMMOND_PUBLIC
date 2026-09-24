#property strict

#include <AuthorEngine\AE_All.mqh>

// DRUMMOND AUTHOR SHADOW 16
// Full observation engine: static + live PLDot, 5/x, 6/x, 1-1,
// HTP/LTP state, energy/congestion evidence and research signals.
// NO ORDER EXECUTION. NO HISTORY REPLAY ON ATTACH.

input bool              InpEnable=true;
input string            InpSymbolsCSV="";
input string            InpExcludeSymbolsCSV="";
input ENUM_TIMEFRAMES   InpDecisionTF=PERIOD_H1;
input ENUM_TIMEFRAMES   InpHTPTF=PERIOD_H4;
input int               InpTimerSeconds=10;
input int               InpLiveSnapshotSeconds=300;
input bool              InpCaptureLiveAllSymbols=true;
input string            InpClosedFile="DRUMMOND_AUTHOR16_H1.csv";
input string            InpLiveFile="DRUMMOND_AUTHOR16_LIVE.csv";
input string            InpAuditFile="DRUMMOND_AUTHOR16_AUDIT.csv";

string   g_ae_symbols[];
datetime g_ae_lastClosed[];
long     g_ae_lastLiveBucket=-1;

string AE16_Trim(string s)
{
   s=StringTrimLeft(s);
   s=StringTrimRight(s);
   return(s);
}

bool AE16_IsExcluded(string sym)
{
   string src=AE16_Trim(InpExcludeSymbolsCSV);
   if(src=="") return(false);
   string parts[];
   int n=StringSplit(src,StringGetCharacter(",",0),parts);
   for(int i=0;i<n;i++)
   {
      string x=AE16_Trim(parts[i]);
      if(x==sym) return(true);
   }
   return(false);
}

bool AE16_LoadUniverse()
{
   ArrayResize(g_ae_symbols,0);
   ArrayResize(g_ae_lastClosed,0);

   if(StringLen(AE16_Trim(InpSymbolsCSV))>0)
   {
      string parts[];
      int n=StringSplit(InpSymbolsCSV,StringGetCharacter(",",0),parts);
      for(int i=0;i<n;i++)
      {
         string sym=AE16_Trim(parts[i]);
         if(sym=="" || AE16_IsExcluded(sym)) continue;
         if(!SymbolSelect(sym,true)) continue;
         int k=ArraySize(g_ae_symbols);
         ArrayResize(g_ae_symbols,k+1);
         ArrayResize(g_ae_lastClosed,k+1);
         g_ae_symbols[k]=sym;
         g_ae_lastClosed[k]=iTime(sym,InpDecisionTF,1);
      }
   }
   else
   {
      int total=SymbolsTotal(true);
      for(int i=0;i<total;i++)
      {
         string sym=SymbolName(i,true);
         if(sym=="" || AE16_IsExcluded(sym)) continue;
         int k=ArraySize(g_ae_symbols);
         ArrayResize(g_ae_symbols,k+1);
         ArrayResize(g_ae_lastClosed,k+1);
         g_ae_symbols[k]=sym;
         g_ae_lastClosed[k]=iTime(sym,InpDecisionTF,1);
      }
   }
   return(ArraySize(g_ae_symbols)>0);
}

int AE16_Open(string file)
{
   int h=FileOpen(file,FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON,';');
   if(h==INVALID_HANDLE) return(INVALID_HANDLE);
   FileSeek(h,0,SEEK_END);
   return(h);
}

void AE16_ClosedHeader(int h)
{
   if(h==INVALID_HANDLE || FileSize(h)>0) return;
   FileWrite(h,
      "SERVER_TIME","SYMBOL","EVENT_TIME","TF","HTP_TF",
      "STATIC_PLDOT","LIVE_PLDOT","REFRESH_LOW","REFRESH_HIGH",
      "DOT_DIR","DOT_DISTANCE","DOT_IN_RANGE","MCLINE",
      "STATE","HTP_STATE","HTP_STATIC_PLDOT","HTP_LIVE_PLDOT",
      "L51_UP","L51_DOWN","L52_UP","L52_DOWN","L53_UP","L53_DOWN",
      "L59_UP","L59_DOWN","L11_FROM_LOW","L11_FROM_HIGH",
      "L61_UP","L65_DOWN","L61_DOWN","L65_UP","L67_UP","L67_DOWN","L66_UP","L66_DOWN",
      "ENV_EB","ENV_ET","ENV_COMPLIANCE",
      "NEAR_SUPPORT_LOW","NEAR_SUPPORT_HIGH","NEAR_RESIST_LOW","NEAR_RESIST_HIGH",
      "FAR_SUPPORT_LOW","FAR_SUPPORT_HIGH","FAR_RESIST_LOW","FAR_RESIST_HIGH",
      "BLOCK_LOW","BLOCK_HIGH","BLOCK_COMPLIANCE",
      "HTP_ALIGNED","POWER_UP","POWER_DOWN","EXHAUST_UP","EXHAUST_DOWN",
      "LIVE_REFRESH_UP","LIVE_REFRESH_DOWN","PRIMARY_RESEARCH_SIGNAL",
      "TRADING_ENABLED","CLOSED_51_STATUS","CLOSED_59_STATUS","JAWS_59_STATUS","ENGINE_VERSION");
}

void AE16_LiveHeader(int h)
{
   if(h==INVALID_HANDLE || FileSize(h)>0) return;
   FileWrite(h,
      "SERVER_TIME","SYMBOL","BAR_TIME","TF",
      "PRICE","STATIC_PLDOT","LIVE_PLDOT","REFRESH_LOW","REFRESH_HIGH",
      "LIVE_MINUS_STATIC","PRICE_MINUS_LIVE","IN_REFRESH",
      "HTP_STATIC_PLDOT","HTP_LIVE_PLDOT","ENGINE_VERSION");
}

void AE16_AuditHeader(int h)
{
   if(h==INVALID_HANDLE || FileSize(h)>0) return;
   FileWrite(h,"SERVER_TIME","ENGINE_VERSION","STATUS","DETAIL");
}

void AE16_Audit(string status,string detail)
{
   int h=AE16_Open(InpAuditFile);
   if(h==INVALID_HANDLE) return;
   AE16_AuditHeader(h);
   FileWrite(h,(int)TimeCurrent(),AE_VERSION,status,detail);
   FileFlush(h);FileClose(h);
}

string AE16_LineValue(string sym,ENUM_TIMEFRAMES tf,AE_LINE_ID id)
{
   double v;int d;string n,c;
   if(!AE_GetLine(sym,tf,id,v,d,n,c)) return("");
   return(DoubleToString(v,AE_Digits(sym)));
}

string AE16_ZoneValue(bool valid,double v,string sym)
{
   if(!valid || v<=0.0) return("");
   return(DoubleToString(v,AE_Digits(sym)));
}

void AE16_WriteClosed(string sym,datetime eventTime)
{
   if(!AE_HasBars(sym,InpDecisionTF,20) || !AE_HasBars(sym,InpHTPTF,20)) return;

   int d=AE_Digits(sym);
   double spl=AE_StaticPLDot(sym,InpDecisionTF,0);
   double lpl=AE_LivePLDot(sym,InpDecisionTF);
   double rlo=AE_RefreshLow(sym,InpDecisionTF),rhi=AE_RefreshHigh(sym,InpDecisionTF);
   int dotDir=AE_PLDirection(sym,InpDecisionTF);
   double dotDist=AE_DotDistance(sym,InpDecisionTF,0);
   bool dotIn=AE_DotInPreviousRange(sym,InpDecisionTF,0);
   double mcl=AE_MCLineNow(sym,InpDecisionTF);

   AE_TRADE_STATE st=AE_CurrentTradeState(sym,InpDecisionTF);
   AE_TRADE_STATE hst=AE_CurrentTradeState(sym,InpHTPTF);
   double hs=AE_StaticPLDot(sym,InpHTPTF,0),hl=AE_LivePLDot(sym,InpHTPTF);

   double eb=0.0,et=0.0;string envCp="";
   bool env=AE_Envelope(sym,InpDecisionTF,eb,et,envCp);

   AE_EnergyZone ns,nr,fs,fr;
   bool ez=AE_GetEnergyZones(sym,InpDecisionTF,ns,nr,fs,fr);

   double blo=0.0,bhi=0.0;string bcp="";
   bool block=AE_GetBlockArea(sym,InpDecisionTF,blo,bhi,bcp);

   bool align=AE_HTPAligned(sym,InpDecisionTF,InpHTPTF);
   bool pUp=AE_PowerFlowingInFavor(sym,InpDecisionTF,InpHTPTF,AE_DIR_UP);
   bool pDn=AE_PowerFlowingInFavor(sym,InpDecisionTF,InpHTPTF,AE_DIR_DOWN);
   bool eUp=AE_ExhaustionEvidence(sym,InpDecisionTF,InpHTPTF,AE_DIR_UP);
   bool eDn=AE_ExhaustionEvidence(sym,InpDecisionTF,InpHTPTF,AE_DIR_DOWN);
   bool lrUp=AE_LiveRefreshWithTrend(sym,InpDecisionTF,InpHTPTF,AE_DIR_UP);
   bool lrDn=AE_LiveRefreshWithTrend(sym,InpDecisionTF,InpHTPTF,AE_DIR_DOWN);
   AE_RESEARCH_SIGNAL sig=AE_PrimaryResearchSignal(sym,InpDecisionTF,InpHTPTF);

   int h=AE16_Open(InpClosedFile);
   if(h==INVALID_HANDLE){Print("AUTHOR16: cannot open ",InpClosedFile," err=",GetLastError());return;}
   AE16_ClosedHeader(h);

   FileWrite(h,
      (int)TimeCurrent(),sym,(int)eventTime,AE_TFText(InpDecisionTF),AE_TFText(InpHTPTF),
      DoubleToString(spl,d),DoubleToString(lpl,d),DoubleToString(rlo,d),DoubleToString(rhi,d),
      AE_DirText(dotDir),DoubleToString(dotDist,d),dotIn?1:0,DoubleToString(mcl,d),
      AE_StateText(st),AE_StateText(hst),DoubleToString(hs,d),DoubleToString(hl,d),
      AE16_LineValue(sym,InpDecisionTF,AE_L51_UP),AE16_LineValue(sym,InpDecisionTF,AE_L51_DOWN),
      AE16_LineValue(sym,InpDecisionTF,AE_L52_UP),AE16_LineValue(sym,InpDecisionTF,AE_L52_DOWN),
      AE16_LineValue(sym,InpDecisionTF,AE_L53_UP),AE16_LineValue(sym,InpDecisionTF,AE_L53_DOWN),
      AE16_LineValue(sym,InpDecisionTF,AE_L59_UP),AE16_LineValue(sym,InpDecisionTF,AE_L59_DOWN),
      AE16_LineValue(sym,InpDecisionTF,AE_L11_FROM_LOW),AE16_LineValue(sym,InpDecisionTF,AE_L11_FROM_HIGH),
      AE16_LineValue(sym,InpDecisionTF,AE_L61_UP),AE16_LineValue(sym,InpDecisionTF,AE_L65_DOWN),
      AE16_LineValue(sym,InpDecisionTF,AE_L61_DOWN),AE16_LineValue(sym,InpDecisionTF,AE_L65_UP),
      AE16_LineValue(sym,InpDecisionTF,AE_L67_UP),AE16_LineValue(sym,InpDecisionTF,AE_L67_DOWN),
      AE16_LineValue(sym,InpDecisionTF,AE_L66_UP),AE16_LineValue(sym,InpDecisionTF,AE_L66_DOWN),
      env?DoubleToString(eb,d):"",env?DoubleToString(et,d):"",envCp,
      ez?AE16_ZoneValue(ns.valid,ns.low,sym):"",ez?AE16_ZoneValue(ns.valid,ns.high,sym):"",
      ez?AE16_ZoneValue(nr.valid,nr.low,sym):"",ez?AE16_ZoneValue(nr.valid,nr.high,sym):"",
      ez?AE16_ZoneValue(fs.valid,fs.low,sym):"",ez?AE16_ZoneValue(fs.valid,fs.high,sym):"",
      ez?AE16_ZoneValue(fr.valid,fr.low,sym):"",ez?AE16_ZoneValue(fr.valid,fr.high,sym):"",
      block?DoubleToString(blo,d):"",block?DoubleToString(bhi,d):"",bcp,
      align?1:0,pUp?1:0,pDn?1:0,eUp?1:0,eDn?1:0,lrUp?1:0,lrDn?1:0,
      AE_SignalText(sig),AE_TradingEnabled()?1:0,
      AE_SOURCE_GAP_CLOSED_51,AE_SOURCE_GAP_CLOSED_59,AE_SOURCE_GAP_JAWS_59,AE_VERSION);

   FileFlush(h);FileClose(h);
}

void AE16_WriteLive(string sym)
{
   if(!AE_HasBars(sym,InpDecisionTF,6) || !AE_HasBars(sym,InpHTPTF,6)) return;
   int d=AE_Digits(sym);
   double px=AE_CurrentPrice(sym);
   double spl=AE_StaticPLDot(sym,InpDecisionTF,0);
   double lpl=AE_LivePLDot(sym,InpDecisionTF);
   double rlo=AE_RefreshLow(sym,InpDecisionTF),rhi=AE_RefreshHigh(sym,InpDecisionTF);
   double hs=AE_StaticPLDot(sym,InpHTPTF,0),hl=AE_LivePLDot(sym,InpHTPTF);
   bool inR=(rlo>0.0 && px>=rlo && px<=rhi);

   int h=AE16_Open(InpLiveFile);
   if(h==INVALID_HANDLE) return;
   AE16_LiveHeader(h);
   FileWrite(h,
      (int)TimeCurrent(),sym,(int)iTime(sym,InpDecisionTF,0),AE_TFText(InpDecisionTF),
      DoubleToString(px,d),DoubleToString(spl,d),DoubleToString(lpl,d),
      DoubleToString(rlo,d),DoubleToString(rhi,d),
      DoubleToString(lpl-spl,d),DoubleToString(px-lpl,d),inR?1:0,
      DoubleToString(hs,d),DoubleToString(hl,d),AE_VERSION);
   FileFlush(h);FileClose(h);
}

void AE16_ProcessClosed()
{
   for(int i=0;i<ArraySize(g_ae_symbols);i++)
   {
      string sym=g_ae_symbols[i];
      datetime closed=iTime(sym,InpDecisionTF,1);
      if(closed<=0 || closed==g_ae_lastClosed[i]) continue;
      g_ae_lastClosed[i]=closed;
      AE16_WriteClosed(sym,closed);
   }
}

void AE16_ProcessLive()
{
   if(!InpCaptureLiveAllSymbols) return;
   int sec=MathMax(60,InpLiveSnapshotSeconds);
   long bucket=(long)(TimeCurrent()/sec);
   if(bucket==g_ae_lastLiveBucket) return;
   g_ae_lastLiveBucket=bucket;
   for(int i=0;i<ArraySize(g_ae_symbols);i++) AE16_WriteLive(g_ae_symbols[i]);
}

int OnInit()
{
   if(IsTesting())
   {
      Print("AUTHOR16 INIT BLOCKED: STRATEGY_TESTER_FORBIDDEN");
      return(INIT_FAILED);
   }
   if(!IsDemo())
   {
      Print("AUTHOR16 INIT BLOCKED: ACCOUNT_NOT_DEMO");
      return(INIT_FAILED);
   }
   if(InpTimerSeconds<1 || InpLiveSnapshotSeconds<60)
   {
      Print("AUTHOR16 INIT BLOCKED: INVALID_TIMER");
      return(INIT_FAILED);
   }
   if(!AE16_LoadUniverse())
   {
      Print("AUTHOR16 INIT BLOCKED: EMPTY_UNIVERSE");
      return(INIT_FAILED);
   }

   EventSetTimer(InpTimerSeconds);
   AE16_Audit("INIT_PASS","Modules=Utils,Dots,Lines,State,Envelope,Energy,Congestion,Filters,Signals,TradeManager; Trading=DISABLED; Closed5x/Jaws59=SOURCE_GAP");

   Print("=====================================================");
   Print("DRUMMOND AUTHOR SHADOW 16");
   Print("Engine        = ",AE_VERSION);
   Print("Mode          = DEMO OBSERVATION ONLY");
   Print("Symbols       = ",ArraySize(g_ae_symbols));
   Print("Decision TF   = ",AE_TFText(InpDecisionTF));
   Print("HTP TF        = ",AE_TFText(InpHTPTF));
   Print("Live cadence  = ",InpLiveSnapshotSeconds," sec");
   Print("Static PLDot  = ENABLED");
   Print("Live PLDot    = ENABLED");
   Print("5/x,6/x,1-1   = ENABLED");
   Print("HTP/LTP       = ENABLED");
   Print("Energy/state  = ENABLED");
   Print("Trading       = DISABLED BY DESIGN");
   Print("Closed5x/Jaws = SOURCE_GAP (audit only)");
   Print("History replay= DISABLED ON VPS");
   Print("=====================================================");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   AE16_Audit("DEINIT","reason="+IntegerToString(reason));
   Print("AUTHOR16 DEINIT reason=",reason);
}

void OnTimer()
{
   if(!InpEnable) return;
   AE16_ProcessClosed();
   AE16_ProcessLive();
}

void OnTick()
{
   // Timer-driven multi-symbol observer.
}
