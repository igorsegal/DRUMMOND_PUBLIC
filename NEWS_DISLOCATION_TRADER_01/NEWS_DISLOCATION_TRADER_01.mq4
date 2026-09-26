#property strict
#property version   "1.00"
#property description "NEWS03/NEWS05 live demo adapter: high-impact news x cross-market dislocation"

#include "ND01_CurrencyStrengthCore.mqh"

enum ND01_TRADE_MODE
{
   ND_MODE_DISABLED    = 0,
   ND_MODE_SIGNAL_ONLY = 1,
   ND_MODE_DEMO        = 2
};

input ND01_TRADE_MODE InpMode                  = ND_MODE_SIGNAL_ONLY;
input string          InpNewsFile              = "NEWS_LIVE.csv";
input double          InpDislocationSigma      = 2.0;     // frozen NEWS03/05 threshold
input int             InpDecisionDelayMinutes  = 30;      // frozen
input int             InpDecisionWindowMinutes = 10;      // don't enter stale signals
input int             InpHoldMinutes           = 90;      // use 30 or 90; default NEWS03 longer horizon
input double          InpLots                  = 0.01;
input int             InpSlippagePoints        = 30;
input int             InpMagic                 = 26092601;
input bool            InpAllowRealAccount      = false;
input bool            InpManualSmoke           = false;   // evaluates "news 30m ago" once
input string          InpManualCurrency        = "USD";
input string          InpLogFile               = "NEWS_DISLOCATION_TRADER_01.csv";

bool g_manualDone=false;
datetime g_lastMissingFileNotice=0;

//------------------------------------------------------------------
// Utility
//------------------------------------------------------------------
string ND01_ModeText()
{
   if(InpMode==ND_MODE_DISABLED)    return "DISABLED";
   if(InpMode==ND_MODE_SIGNAL_ONLY) return "SIGNAL_ONLY";
   if(InpMode==ND_MODE_DEMO)        return "DEMO";
   return "UNKNOWN";
}

string ND01_Upper(string s)
{
   StringToUpper(s);
   return s;
}

datetime ND01_ParseUtc(string s)
{
   // Accepted:
   // 2026-09-26T12:30:00Z
   // 2026-09-26 12:30:00
   // 2026.09.26 12:30
   string x=s;
   StringReplace(x,"T"," ");
   StringReplace(x,"-",".");

   int z=StringFind(x,"Z",0);
   if(z>=0)
      x=StringSubstr(x,0,z);

   int p=StringFind(x,"+",10);
   if(p>=0)
      x=StringSubstr(x,0,p);

   return StringToTime(x);
}

string ND01_EventKey(const datetime eventUtc,const string currency)
{
   return "NDT01_"+currency+"_"+IntegerToString((int)eventUtc);
}

void ND01_Log(const datetime eventUtc,
              const string currency,
              const string eventName,
              const string canonical,
              const string brokerSymbol,
              const double targetZ,
              const double externalGap,
              const double dislocation,
              const string side,
              const string action,
              const int ticket,
              const int errorCode)
{
   int h=FileOpen(InpLogFile,
                  FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|
                  FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON,
                  ';');
   if(h==INVALID_HANDLE)
   {
      Print("ND01 log open failed: ",GetLastError());
      return;
   }

   if(FileSize(h)==0)
   {
      FileWrite(h,
         "SERVER_TIME","UTC_NOW","EVENT_UTC","NEWS_CURRENCY","EVENT",
         "CANONICAL","BROKER_SYMBOL","MODE",
         "TARGET_Z30","EXTERNAL_GAP_Z30","DISLOCATION_Z","SIDE",
         "SPREAD_POINTS","ACTION","TICKET","ERROR");
   }

   FileSeek(h,0,SEEK_END);

   double sp=0.0;
   if(brokerSymbol!="")
      sp=MarketInfo(brokerSymbol,MODE_SPREAD);

   FileWrite(h,
      TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),
      TimeToString(TimeGMT(),TIME_DATE|TIME_SECONDS),
      TimeToString(eventUtc,TIME_DATE|TIME_SECONDS),
      currency,eventName,canonical,brokerSymbol,ND01_ModeText(),
      DoubleToString(targetZ,6),
      DoubleToString(externalGap,6),
      DoubleToString(dislocation,6),
      side,
      DoubleToString(sp,1),
      action,
      ticket,
      errorCode);

   FileClose(h);
}

bool ND01_HasOpenPosition(const string sym)
{
   for(int i=OrdersTotal()-1;i>=0;i--)
   {
      if(!OrderSelect(i,SELECT_BY_POS,MODE_TRADES))
         continue;
      if(OrderMagicNumber()!=InpMagic)
         continue;
      if(OrderSymbol()!=sym)
         continue;
      int t=OrderType();
      if(t==OP_BUY || t==OP_SELL)
         return true;
   }
   return false;
}

double ND01_NormalizeLots(const string sym,double lots)
{
   double minLot=MarketInfo(sym,MODE_MINLOT);
   double maxLot=MarketInfo(sym,MODE_MAXLOT);
   double step=MarketInfo(sym,MODE_LOTSTEP);

   if(step<=0.0) step=0.01;
   lots=MathMax(minLot,MathMin(maxLot,lots));
   lots=MathFloor(lots/step+1e-9)*step;

   int digits=2;
   if(step>=1.0)       digits=0;
   else if(step>=0.1)  digits=1;
   else if(step>=0.01) digits=2;
   else if(step>=0.001)digits=3;
   else                digits=4;

   return NormalizeDouble(lots,digits);
}

int ND01_SendOrder(const string sym,const int side,const string commentText)
{
   if(InpMode!=ND_MODE_DEMO)
      return -1;

   if(!IsDemo() && !InpAllowRealAccount)
   {
      Print("ND01: REAL ACCOUNT BLOCKED. Set InpAllowRealAccount=true explicitly.");
      return -1;
   }

   if(!IsTradeAllowed())
   {
      Print("ND01: trade not allowed now.");
      return -1;
   }

   if(ND01_HasOpenPosition(sym))
      return -2;

   double lots=ND01_NormalizeLots(sym,InpLots);
   int type=(side>0 ? OP_BUY : OP_SELL);
   double price=(side>0 ? MarketInfo(sym,MODE_ASK) : MarketInfo(sym,MODE_BID));
   int digits=(int)MarketInfo(sym,MODE_DIGITS);
   price=NormalizeDouble(price,digits);

   ResetLastError();
   int ticket=OrderSend(sym,type,lots,price,InpSlippagePoints,0,0,
                        commentText,InpMagic,0,clrNONE);
   if(ticket<0)
      Print("ND01 OrderSend failed ",sym," err=",GetLastError());

   return ticket;
}

//------------------------------------------------------------------
// Trading / signal path
//------------------------------------------------------------------
bool ND01_ProcessEvent(const datetime eventUtc,
                       const string currency,
                       const string eventName)
{
   double z[];
   ArrayResize(z,ND01_PAIR_COUNT);

   if(!ND01_BuildZVector(eventUtc,z))
   {
      ND01_Log(eventUtc,currency,eventName,"","",0,0,0,"","BASKET_NOT_READY",-1,0);
      Print("ND01: basket not ready for ",currency," ",TimeToString(eventUtc,TIME_DATE|TIME_MINUTES));
      return false; // retry inside decision window
   }

   int candidates=0;
   int signals=0;

   for(int i=0;i<ND01_PAIR_COUNT;i++)
   {
      string canonical=ND01_CanonicalPairs[i];
      string base=StringSubstr(canonical,0,3);
      string quote=StringSubstr(canonical,3,3);

      if(currency!=base && currency!=quote)
         continue;

      candidates++;

      double targetZ=0.0,externalGap=0.0,d=0.0;
      if(!ND01_TargetDislocation(i,z,targetZ,externalGap,d))
      {
         ND01_Log(eventUtc,currency,eventName,canonical,ND01_BrokerPairs[i],
                  targetZ,externalGap,d,"","CALC_FAIL",-1,0);
         continue;
      }

      int side=(d>0.0 ? 1 : -1);
      string sideText=(side>0 ? "LONG" : "SHORT");

      if(MathAbs(d)<InpDislocationSigma)
      {
         ND01_Log(eventUtc,currency,eventName,canonical,ND01_BrokerPairs[i],
                  targetZ,externalGap,d,sideText,"NO_SIGNAL",-1,0);
         continue;
      }

      signals++;

      if(InpMode==ND_MODE_SIGNAL_ONLY)
      {
         ND01_Log(eventUtc,currency,eventName,canonical,ND01_BrokerPairs[i],
                  targetZ,externalGap,d,sideText,"SIGNAL_ONLY",-1,0);
         Print("ND01 SIGNAL ",canonical," ",sideText,
               " D=",DoubleToString(d,3),
               " news=",currency," ",eventName);
         continue;
      }

      if(InpMode==ND_MODE_DEMO)
      {
         string commentText="ND01 "+currency+" "+TimeToString(eventUtc,TIME_DATE|TIME_MINUTES);
         ResetLastError();
         int ticket=ND01_SendOrder(ND01_BrokerPairs[i],side,commentText);
         int err=(ticket<0 ? GetLastError() : 0);

         string action="ORDER_OPENED";
         if(ticket==-2) action="POSITION_BLOCKED";
         else if(ticket<0) action="ORDER_FAILED";

         ND01_Log(eventUtc,currency,eventName,canonical,ND01_BrokerPairs[i],
                  targetZ,externalGap,d,sideText,action,ticket,err);
      }
   }

   Print("ND01 EVENT processed ",currency," ",eventName,
         " candidates=",candidates," signals=",signals);
   return true;
}

void ND01_ManageExits()
{
   if(InpHoldMinutes<=0)
      return;

   for(int i=OrdersTotal()-1;i>=0;i--)
   {
      if(!OrderSelect(i,SELECT_BY_POS,MODE_TRADES))
         continue;
      if(OrderMagicNumber()!=InpMagic)
         continue;

      int type=OrderType();
      if(type!=OP_BUY && type!=OP_SELL)
         continue;

      if(TimeCurrent() < OrderOpenTime()+InpHoldMinutes*60)
         continue;

      string sym=OrderSymbol();
      double px=(type==OP_BUY ? MarketInfo(sym,MODE_BID) : MarketInfo(sym,MODE_ASK));
      int digits=(int)MarketInfo(sym,MODE_DIGITS);
      px=NormalizeDouble(px,digits);

      ResetLastError();
      bool ok=OrderClose(OrderTicket(),OrderLots(),px,InpSlippagePoints,clrNONE);
      if(ok)
         Print("ND01 EXIT ",sym," ticket=",OrderTicket()," hold=",InpHoldMinutes,"m");
      else
         Print("ND01 EXIT FAILED ",sym," ticket=",OrderTicket()," err=",GetLastError());
   }
}

void ND01_ScanNews()
{
   if(InpMode==ND_MODE_DISABLED)
      return;

   datetime nowUtc=TimeGMT();

   int h=FileOpen(InpNewsFile,
                  FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_COMMON,
                  ';');

   if(h==INVALID_HANDLE)
   {
      if(nowUtc-g_lastMissingFileNotice>=60)
      {
         Print("ND01: cannot open Common\\Files\\",InpNewsFile," err=",GetLastError());
         g_lastMissingFileNotice=nowUtc;
      }
      return;
   }

   while(!FileIsEnding(h))
   {
      string ts=FileReadString(h);
      if(FileIsEnding(h) && ts=="")
         break;

      string cur=FileReadString(h);
      string impact=FileReadString(h);
      string eventName=FileReadString(h);

      if(ts=="UTC_TIME")
         continue;

      cur=ND01_Upper(cur);
      impact=ND01_Upper(impact);

      if(!ND01_IsCurrency(cur))
         continue;
      if(impact!="HIGH")
         continue;

      datetime eventUtc=ND01_ParseUtc(ts);
      if(eventUtc<=0)
         continue;

      datetime ready=eventUtc+InpDecisionDelayMinutes*60;
      if(nowUtc<ready)
         continue;
      if(nowUtc>ready+InpDecisionWindowMinutes*60)
         continue;

      string key=ND01_EventKey(eventUtc,cur);
      if(GlobalVariableCheck(key))
         continue;

      // One (time,currency) cluster is processed once even if the CSV contains
      // multiple simultaneous high-impact releases (e.g. CPI + Core CPI).
      if(ND01_ProcessEvent(eventUtc,cur,eventName))
         GlobalVariableSet(key,(double)TimeCurrent());
   }

   FileClose(h);
}

void ND01_RunManualSmoke()
{
   if(!InpManualSmoke || g_manualDone || InpMode==ND_MODE_DISABLED)
      return;

   string cur=ND01_Upper(InpManualCurrency);
   if(!ND01_IsCurrency(cur))
   {
      Print("ND01 manual smoke: invalid currency ",cur);
      g_manualDone=true;
      return;
   }

   datetime eventUtc=TimeGMT()-InpDecisionDelayMinutes*60;
   eventUtc=(datetime)(((long)eventUtc/300)*300);

   Print("ND01 MANUAL SMOKE: synthetic scheduled event ",cur,
         " UTC=",TimeToString(eventUtc,TIME_DATE|TIME_MINUTES));

   ND01_ProcessEvent(eventUtc,cur,"MANUAL_SMOKE");
   g_manualDone=true;
}

//------------------------------------------------------------------
// MT4 lifecycle
//------------------------------------------------------------------
int OnInit()
{
   if(InpDislocationSigma!=2.0)
      Print("ND01 WARNING: research-frozen threshold is 2.0 sigma; current=",
            DoubleToString(InpDislocationSigma,3));

   if(InpDecisionDelayMinutes!=30)
      Print("ND01 WARNING: research-frozen decision delay is 30 minutes.");

   if(InpHoldMinutes!=30 && InpHoldMinutes!=90)
      Print("ND01 WARNING: research horizons are 30 or 90 minutes after decision.");

   if(InpMode==ND_MODE_DEMO && !IsDemo() && !InpAllowRealAccount)
   {
      Print("ND01 INIT FAILED: DEMO mode selected on non-demo account. Real account is blocked.");
      return INIT_FAILED;
   }

   int found=ND01_InitBrokerSymbols();

   Print("============================================================");
   Print("NEWS DISLOCATION TRADER 01");
   Print("MODE=",ND01_ModeText()," | mapped FX pairs=",found,"/28");
   Print("Frozen signal: +30m, target excluded, |D|>=2 sigma");
   Print("Hold minutes=",InpHoldMinutes," | magic=",InpMagic);
   Print("============================================================");

   for(int i=0;i<ND01_PAIR_COUNT;i++)
      Print("ND01 MAP ",ND01_CanonicalPairs[i]," -> ",
            (ND01_BrokerPairs[i]=="" ? "MISSING" : ND01_BrokerPairs[i]));

   if(found<ND01_PAIR_COUNT)
   {
      Print("ND01 INIT FAILED: exact research contract requires all 28 FX crosses.");
      return INIT_FAILED;
   }

   EventSetTimer(10);

   Comment(
      "NEWS DISLOCATION TRADER 01\n",
      "Mode: ",ND01_ModeText(),"\n",
      "FX basket: ",found,"/28\n",
      "Signal: High Impact -> +30m -> |D| >= ",
      DoubleToString(InpDislocationSigma,1)," sigma\n",
      "Hold: ",InpHoldMinutes," min\n",
      "News: Common\\Files\\",InpNewsFile
   );

   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
}

void OnTick()
{
   // Trading logic is timer-driven so the EA can manage all 28 symbols
   // from one chart; no dependency on ticks of the attached chart.
}

void OnTimer()
{
   ND01_ManageExits();
   ND01_RunManualSmoke();
   ND01_ScanNews();
}
