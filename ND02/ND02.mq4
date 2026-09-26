#property strict
#property version "1.00"
#property description "ND02: MT4 Strategy Tester news-dislocation trader"

#include "ND02.mqh"

input string InpNewsFile="NEWS26.csv";
input bool   InpTrade=true;
input double InpLots=0.01;
input double InpDislocationSigma=2.0;
input int    InpDecisionDelayMinutes=30;
input int    InpDecisionWindowMinutes=15;
input int    InpHoldMinutes=90;
input int    InpSlippagePoints=30;
input int    InpMagic=26092602;
input int    InpUtcWinterOffsetHours=2;
input int    InpUtcSummerOffsetHours=3;
input bool   InpUseEuropeDST=true;
input bool   InpAllowOutsideTester=false;
input string InpLogFile="ND02.csv";

datetime gUtc[];
datetime gServer[];
string   gCur[];
string   gName[];
int      gNewsN=0;
int      gNext=0;
int      gTarget=-1;
int      gTargetMode=0; // 1=full FX pair, 2=one-sided external currency target
string   gTargetCanonical="";
string   gBaseCode="";
string   gQuoteCode="";
string   gNewsCurrency="";
bool     gKnownCurrencyIsBase=false;
datetime gLastExitCheck=0;
datetime gLastBasketFailPrint=0;
int      gLastBasketFailNews=-1;

string ND02_Upper(string s)
{
   StringToUpper(s);
   return s;
}

datetime ND02_ParseUtc(string s)
{
   string x=s;
   StringReplace(x,"T"," ");
   StringReplace(x,"-",".");
   int z=StringFind(x,"Z",0);
   if(z>=0) x=StringSubstr(x,0,z);
   return StringToTime(x);
}

datetime ND02_LastSunday0100Utc(int year,int month)
{
   string mm=(month<10 ? "0"+IntegerToString(month) : IntegerToString(month));
   datetime d31=StringToTime(IntegerToString(year)+"."+mm+".31 01:00");
   int dow=TimeDayOfWeek(d31);
   return d31-dow*86400;
}

int ND02_UtcOffsetHours(datetime utc)
{
   if(!InpUseEuropeDST)
      return InpUtcWinterOffsetHours;

   int y=TimeYear(utc);
   datetime start=ND02_LastSunday0100Utc(y,3);
   datetime finish=ND02_LastSunday0100Utc(y,10);

   if(utc>=start && utc<finish)
      return InpUtcSummerOffsetHours;
   return InpUtcWinterOffsetHours;
}

datetime ND02_UtcToServer(datetime utc)
{
   return utc+ND02_UtcOffsetHours(utc)*3600;
}

bool ND02_ParseTarget()
{
   string s=Symbol();

   for(int i=0;i<ND02_PAIR_COUNT;i++)
   {
      if(s==ND02_CanonicalPairs[i] || StringFind(s,ND02_CanonicalPairs[i],0)>=0)
      {
         gTarget=i;
         gTargetMode=1;
         gTargetCanonical=ND02_CanonicalPairs[i];
         gBaseCode=StringSubstr(gTargetCanonical,0,3);
         gQuoteCode=StringSubstr(gTargetCanonical,3,3);
         return true;
      }
   }

   if(StringLen(s)<6)
      return false;

   gBaseCode=StringSubstr(s,0,3);
   gQuoteCode=StringSubstr(s,3,3);

   bool baseKnown=ND02_IsCurrency(gBaseCode);
   bool quoteKnown=ND02_IsCurrency(gQuoteCode);

   if(baseKnown==quoteKnown)
      return false;

   gTarget=-1;
   gTargetMode=2;
   gTargetCanonical=gBaseCode+gQuoteCode;
   gKnownCurrencyIsBase=baseKnown;
   gNewsCurrency=(baseKnown ? gBaseCode : gQuoteCode);
   return true;
}

bool ND02_TargetContainsCurrency(string cur)
{
   if(gTargetMode==1)
      return (gBaseCode==cur || gQuoteCode==cur);

   if(gTargetMode==2)
      return (gNewsCurrency==cur);

   return false;
}

bool ND02_LoadNews()
{
   int h=FileOpen(InpNewsFile,FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_COMMON,';');
   if(h==INVALID_HANDLE)
   {
      Print("ND02: cannot open Common\\Files\\",InpNewsFile," err=",GetLastError());
      return false;
   }

   ArrayResize(gUtc,0);
   ArrayResize(gServer,0);
   ArrayResize(gCur,0);
   ArrayResize(gName,0);
   gNewsN=0;

   while(!FileIsEnding(h))
   {
      string ts=FileReadString(h);
      if(FileIsEnding(h) && ts=="") break;
      string cur=FileReadString(h);
      string impact=FileReadString(h);
      string name=FileReadString(h);

      if(ts=="UTC_TIME") continue;

      cur=ND02_Upper(cur);
      impact=ND02_Upper(impact);
      if(impact!="HIGH") continue;
      if(!ND02_IsCurrency(cur)) continue;

      datetime utc=ND02_ParseUtc(ts);
      if(utc<=0) continue;

      // Merge simultaneous releases of the same currency into one news cluster.
      if(gNewsN>0 && gUtc[gNewsN-1]==utc && gCur[gNewsN-1]==cur)
      {
         if(StringFind(gName[gNewsN-1],name,0)<0)
            gName[gNewsN-1]=gName[gNewsN-1]+" | "+name;
         continue;
      }

      int n=gNewsN+1;
      ArrayResize(gUtc,n);
      ArrayResize(gServer,n);
      ArrayResize(gCur,n);
      ArrayResize(gName,n);

      gUtc[gNewsN]=utc;
      gServer[gNewsN]=ND02_UtcToServer(utc);
      gCur[gNewsN]=cur;
      gName[gNewsN]=name;
      gNewsN=n;
   }

   FileClose(h);
   Print("ND02: NEWS loaded clusters=",gNewsN);
   return (gNewsN>0);
}

void ND02_Log(int idx,double targetZ,double externalGap,double d,string action,int ticket,int err)
{
   int h=FileOpen(InpLogFile,
                  FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|
                  FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON,';');
   if(h==INVALID_HANDLE) return;

   if(FileSize(h)==0)
      FileWrite(h,"TEST_TIME","EVENT_UTC","EVENT_SERVER","CURRENCY","EVENT",
                  "TARGET","TARGET_Z30","EXTERNAL_GAP_Z30","DISLOCATION_Z",
                  "ACTION","TICKET","ERROR","BID","ASK","SPREAD_POINTS");

   FileSeek(h,0,SEEK_END);

   FileWrite(h,
      TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),
      TimeToString(gUtc[idx],TIME_DATE|TIME_SECONDS),
      TimeToString(gServer[idx],TIME_DATE|TIME_SECONDS),
      gCur[idx],gName[idx],gTargetCanonical,
      DoubleToString(targetZ,6),
      DoubleToString(externalGap,6),
      DoubleToString(d,6),
      action,ticket,err,
      DoubleToString(Bid,Digits),
      DoubleToString(Ask,Digits),
      DoubleToString(MarketInfo(Symbol(),MODE_SPREAD),1));

   FileClose(h);
}

bool ND02_HasPosition()
{
   for(int i=OrdersTotal()-1;i>=0;i--)
   {
      if(!OrderSelect(i,SELECT_BY_POS,MODE_TRADES)) continue;
      if(OrderMagicNumber()!=InpMagic) continue;
      if(OrderSymbol()!=Symbol()) continue;
      int t=OrderType();
      if(t==OP_BUY || t==OP_SELL) return true;
   }
   return false;
}

double ND02_Lots()
{
   double mn=MarketInfo(Symbol(),MODE_MINLOT);
   double mx=MarketInfo(Symbol(),MODE_MAXLOT);
   double st=MarketInfo(Symbol(),MODE_LOTSTEP);
   if(st<=0) st=0.01;

   double x=MathMax(mn,MathMin(mx,InpLots));
   x=MathFloor(x/st+1e-9)*st;

   int dg=2;
   if(st>=1.0) dg=0;
   else if(st>=0.1) dg=1;
   else if(st>=0.01) dg=2;
   else if(st>=0.001) dg=3;
   else dg=4;
   return NormalizeDouble(x,dg);
}

int ND02_Open(int side,string commentText)
{
   if(!InpTrade) return -10;
   if(ND02_HasPosition()) return -20;

   RefreshRates();
   int type=(side>0 ? OP_BUY : OP_SELL);
   double px=(side>0 ? Ask : Bid);
   px=NormalizeDouble(px,Digits);

   ResetLastError();
   int ticket=OrderSend(Symbol(),type,ND02_Lots(),px,InpSlippagePoints,0,0,
                        commentText,InpMagic,0,clrNONE);
   if(ticket<0)
      Print("ND02 OrderSend FAIL err=",GetLastError());
   else
      Print("ND02 ORDER OPENED ",gTargetCanonical," ticket=",ticket,
            " side=",(side>0?"LONG":"SHORT"));
   return ticket;
}

void ND02_ManageExit()
{
   if(InpHoldMinutes<=0) return;
   if(gLastExitCheck==TimeCurrent()) return;
   gLastExitCheck=TimeCurrent();

   for(int i=OrdersTotal()-1;i>=0;i--)
   {
      if(!OrderSelect(i,SELECT_BY_POS,MODE_TRADES)) continue;
      if(OrderMagicNumber()!=InpMagic || OrderSymbol()!=Symbol()) continue;

      int type=OrderType();
      if(type!=OP_BUY && type!=OP_SELL) continue;
      if(TimeCurrent()<OrderOpenTime()+InpHoldMinutes*60) continue;

      RefreshRates();
      double px=(type==OP_BUY ? Bid : Ask);
      px=NormalizeDouble(px,Digits);

      ResetLastError();
      bool ok=OrderClose(OrderTicket(),OrderLots(),px,InpSlippagePoints,clrNONE);
      if(ok)
         Print("ND02 EXIT ticket=",OrderTicket()," hold=",InpHoldMinutes,"m");
      else
         Print("ND02 EXIT FAIL ticket=",OrderTicket()," err=",GetLastError());
   }
}

void ND02_ProcessNews()
{
   datetime now=TimeCurrent();

   while(gNext<gNewsN)
   {
      datetime ready=gServer[gNext]+InpDecisionDelayMinutes*60;

      if(now<ready)
         break;

      if(now>=ready+InpDecisionWindowMinutes*60)
      {
         gNext++;
         continue;
      }

      if(!ND02_TargetContainsCurrency(gCur[gNext]))
      {
         gNext++;
         continue;
      }

      double targetZ=0.0,externalGap=0.0,d=0.0;
      bool calcOK=false;

      if(gTargetMode==1)
      {
         double z[];
         ArrayResize(z,ND02_PAIR_COUNT);

         if(!ND02_BuildZVectorServer(gServer[gNext],z))
         {
            if(gLastBasketFailNews!=gNext)
            {
               Print("ND02 BASKET WAIT event=",
                     TimeToString(gServer[gNext],TIME_DATE|TIME_MINUTES),
                     " target=",gTargetCanonical,
                     " fail_symbol=",ND02_LastBasketFailSymbol,
                     " reason=",ND02_LastBasketFailReason);
               gLastBasketFailNews=gNext;
            }
            return;
         }

         calcOK=ND02_TargetDislocation(gTarget,z,targetZ,externalGap,d);
      }
      else if(gTargetMode==2)
      {
         double currencyStrength=0.0;
         bool a=ND02_SymbolZ30(Symbol(),gServer[gNext],targetZ);
         bool b=ND02_ExternalCurrencyStrengthServer(gNewsCurrency,gServer[gNext],currencyStrength);

         if(a && b)
         {
            // Example XAUUSD: positive USD strength implies negative external
            // pressure for XAUUSD, because USD is the quote currency.
            externalGap=(gKnownCurrencyIsBase ? currencyStrength : -currencyStrength);
            d=externalGap-targetZ;
            calcOK=true;
         }
         else
         {
            if(gLastBasketFailNews!=gNext)
            {
               Print("ND02 ONE_SIDED WAIT event=",
                     TimeToString(gServer[gNext],TIME_DATE|TIME_MINUTES),
                     " target=",gTargetCanonical,
                     " currency=",gNewsCurrency,
                     " fail_symbol=",ND02_LastBasketFailSymbol,
                     " reason=",ND02_LastBasketFailReason);
               gLastBasketFailNews=gNext;
            }
            return;
         }
      }

      if(!calcOK)
      {
         ND02_Log(gNext,targetZ,externalGap,d,"CALC_FAIL",-1,0);
         gNext++;
         continue;
      }

      if(MathAbs(d)<InpDislocationSigma)
      {
         ND02_Log(gNext,targetZ,externalGap,d,"NO_SIGNAL",-1,0);
         Print("ND02 NO SIGNAL ",gTargetCanonical," D=",DoubleToString(d,3));
         gNext++;
         continue;
      }

      int side=(d>0.0 ? 1 : -1);
      string action=(side>0 ? "SIGNAL_LONG" : "SIGNAL_SHORT");
      int ticket=-1,err=0;

      if(InpTrade)
      {
         ResetLastError();
         ticket=ND02_Open(side,"ND02 "+gCur[gNext]);
         err=(ticket<0 ? GetLastError() : 0);

         if(ticket>=0) action=(side>0 ? "ORDER_LONG" : "ORDER_SHORT");
         else if(ticket==-20) action="POSITION_BLOCKED";
         else action="ORDER_FAILED";
      }

      ND02_Log(gNext,targetZ,externalGap,d,action,ticket,err);
      Print("ND02 EVENT ",gCur[gNext]," ",gName[gNext],
            " target=",gTargetCanonical,
            " D=",DoubleToString(d,3),
            " action=",action);

      gNext++;
   }
}

int OnInit()
{
   if(!IsTesting() && !InpAllowOutsideTester)
   {
      Print("ND02 INIT FAILED: this version is for Strategy Tester.");
      return INIT_FAILED;
   }

   if(!ND02_ParseTarget())
   {
      Print("ND02 INIT FAILED: unsupported target symbol: ",Symbol(),
            ". Use a canonical FX pair or a 6-char symbol with exactly one of AUD/CAD/CHF/EUR/GBP/JPY/NZD/USD.");
      return INIT_FAILED;
   }

   int found=ND02_InitBrokerSymbols();
   Print("ND02 map=",found,"/28 target=",gTargetCanonical,
         " broker=",Symbol()," mode=",(gTargetMode==1 ? "FX_FULL" : "ONE_SIDED"));

   if(gTargetMode==2)
      Print("ND02 EXPERIMENTAL ONE-SIDED TARGET: currency=",gNewsCurrency,
            " known_is_base=",gKnownCurrencyIsBase,
            " (e.g. XAUUSD uses external USD strength).");

   if(found<ND02_PAIR_COUNT)
   {
      Print("ND02 INIT FAILED: all 28 FX crosses are required for exact external strength.");
      return INIT_FAILED;
   }

   if(!ND02_LoadNews())
      return INIT_FAILED;

   if(InpDislocationSigma!=2.0)
      Print("ND02 WARNING: frozen research threshold is 2.0 sigma.");
   if(InpDecisionDelayMinutes!=30)
      Print("ND02 WARNING: frozen research delay is 30 minutes.");
   if(InpHoldMinutes!=30 && InpHoldMinutes!=90)
      Print("ND02 WARNING: research hold horizons are 30 or 90 minutes.");

   Print("==================================================");
   Print("ND02 STRATEGY TESTER TRADER");
   Print("TARGET=",gTargetCanonical,
         " MODE=",(gTargetMode==1 ? "FX_FULL" : "ONE_SIDED"),
         " NEWS=",gNewsN,
         " TRADE=",InpTrade,
         " HOLD=",InpHoldMinutes,
         " LOTS=",DoubleToString(InpLots,2));
   Print("UTC offsets winter/summer=",
         InpUtcWinterOffsetHours,"/",InpUtcSummerOffsetHours,
         " EU_DST=",InpUseEuropeDST);
   Print("==================================================");

   return INIT_SUCCEEDED;
}

void OnTick()
{
   ND02_ManageExit();
   ND02_ProcessNews();
}

void OnDeinit(const int reason)
{
   Print("ND02 STOP reason=",reason," nextNews=",gNext,"/",gNewsN);
}
