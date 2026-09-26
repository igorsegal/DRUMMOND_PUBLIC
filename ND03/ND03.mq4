#property strict
#property version   "1.00"
#property description "ND03: XAUUSD Strategy Tester trader with precomputed external USD strength"

input string InpSignalFile="USD26.csv";
input bool   InpTrade=true;
input double InpLots=0.10;
input double InpDislocationSigma=2.0;
input int    InpDecisionDelayMinutes=30;
input int    InpDecisionWindowMinutes=15;
input int    InpHoldMinutes=90;
input int    InpSlippagePoints=30;
input int    InpMagic=26092603;
input int    InpUtcWinterOffsetHours=2;
input int    InpUtcSummerOffsetHours=3;
input bool   InpUseEuropeDST=true;
input bool   InpAllowOutsideTester=false;
input string InpLogFile="ND03.csv";

#define ND03_VOL_BARS 288

datetime gUtc[];
datetime gServer[];
string   gEvent[];
double   gExt[];
int      gN=0;
int      gNext=0;
int      gProcessed=0;
int      gNoSignal=0;
int      gSignals=0;
int      gOpened=0;
int      gBlocked=0;
int      gFailed=0;

datetime ND03_ParseUtc(string s)
{
   string x=s;
   StringReplace(x,"T"," ");
   StringReplace(x,"-",".");
   int z=StringFind(x,"Z",0);
   if(z>=0) x=StringSubstr(x,0,z);
   return StringToTime(x);
}

datetime ND03_LastSunday0100Utc(int year,int month)
{
   string mm=(month<10 ? "0"+IntegerToString(month) : IntegerToString(month));
   datetime d31=StringToTime(IntegerToString(year)+"."+mm+".31 01:00");
   return d31-TimeDayOfWeek(d31)*86400;
}

int ND03_UtcOffsetHours(datetime utc)
{
   if(!InpUseEuropeDST) return InpUtcWinterOffsetHours;
   int y=TimeYear(utc);
   datetime a=ND03_LastSunday0100Utc(y,3);
   datetime b=ND03_LastSunday0100Utc(y,10);
   if(utc>=a && utc<b) return InpUtcSummerOffsetHours;
   return InpUtcWinterOffsetHours;
}

datetime ND03_UtcToServer(datetime utc)
{
   return utc+ND03_UtcOffsetHours(utc)*3600;
}

datetime ND03_AlignUpM5(datetime t)
{
   long x=(long)t;
   long r=x%300;
   if(r==0) return t;
   return (datetime)(x+(300-r));
}

bool ND03_TargetZ30(datetime eventServer,double &z30)
{
   z30=0.0;
   datetime aligned=ND03_AlignUpM5(eventServer);

   int bars=iBars(Symbol(),PERIOD_M5);
   if(bars<ND03_VOL_BARS+20) return false;

   int s0=iBarShift(Symbol(),PERIOD_M5,aligned,false);
   int s30=iBarShift(Symbol(),PERIOD_M5,aligned+1800,false);
   if(s0<0 || s30<0) return false;

   datetime t0=iTime(Symbol(),PERIOD_M5,s0);
   datetime t30=iTime(Symbol(),PERIOD_M5,s30);
   if(MathAbs((double)(t0-aligned))>300.0) return false;
   if(MathAbs((double)(t30-(aligned+1800)))>300.0) return false;
   if(s0+ND03_VOL_BARS+1>=bars) return false;

   double o0=iOpen(Symbol(),PERIOD_M5,s0);
   double o30=iOpen(Symbol(),PERIOD_M5,s30);
   if(o0<=0.0 || o30<=0.0) return false;

   double sum=0.0,sum2=0.0;
   int n=0;
   for(int k=1;k<=ND03_VOL_BARS;k++)
   {
      double newer=iOpen(Symbol(),PERIOD_M5,s0+k);
      double older=iOpen(Symbol(),PERIOD_M5,s0+k+1);
      if(newer<=0.0 || older<=0.0) return false;
      double r=MathLog(newer/older);
      sum+=r; sum2+=r*r; n++;
   }

   if(n<2) return false;
   double variance=(sum2-sum*sum/n)/(n-1);
   if(variance<=0.0) return false;

   double sd=MathSqrt(variance);
   z30=MathLog(o30/o0)/(sd*MathSqrt(6.0));
   return MathIsValidNumber(z30);
}

bool ND03_LoadSignals()
{
   int h=FileOpen(InpSignalFile,
                  FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_COMMON,';');
   if(h==INVALID_HANDLE)
   {
      Print("ND03 INIT FAILED: cannot open Common\\Files\\",InpSignalFile,
            " err=",GetLastError());
      return false;
   }

   ArrayResize(gUtc,0);
   ArrayResize(gServer,0);
   ArrayResize(gEvent,0);
   ArrayResize(gExt,0);
   gN=0;

   while(!FileIsEnding(h))
   {
      string ts=FileReadString(h);
      if(FileIsEnding(h) && ts=="") break;
      string aligned=FileReadString(h);
      string eventName=FileReadString(h);
      string usdStrength=FileReadString(h);
      string externalGap=FileReadString(h);
      string legCount=FileReadString(h);

      if(ts=="UTC_TIME") continue;

      datetime utc=ND03_ParseUtc(ts);
      if(utc<=0) continue;
      double ext=StringToDouble(externalGap);
      if(!MathIsValidNumber(ext)) continue;
      if(StringToInteger(legCount)!=7) continue;

      int n=gN+1;
      ArrayResize(gUtc,n);
      ArrayResize(gServer,n);
      ArrayResize(gEvent,n);
      ArrayResize(gExt,n);

      gUtc[gN]=utc;
      gServer[gN]=ND03_UtcToServer(utc);
      gEvent[gN]=eventName;
      gExt[gN]=ext;
      gN=n;
   }

   FileClose(h);
   Print("ND03: external USD rows loaded=",gN);
   return gN>0;
}

bool ND03_HasPosition()
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

double ND03_Lots()
{
   double mn=MarketInfo(Symbol(),MODE_MINLOT);
   double mx=MarketInfo(Symbol(),MODE_MAXLOT);
   double st=MarketInfo(Symbol(),MODE_LOTSTEP);
   if(st<=0.0) st=0.01;
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

void ND03_Log(int idx,double targetZ,double d,string action,int ticket,int err)
{
   int h=FileOpen(InpLogFile,
                  FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|
                  FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON,';');
   if(h==INVALID_HANDLE) return;

   if(FileSize(h)==0)
      FileWrite(h,"TEST_TIME","EVENT_UTC","EVENT_SERVER","EVENT",
                  "TARGET_Z30","EXTERNAL_GAP_Z30","DISLOCATION_Z",
                  "ACTION","TICKET","ERROR","BID","ASK","SPREAD_POINTS");

   FileSeek(h,0,SEEK_END);
   FileWrite(h,
      TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),
      TimeToString(gUtc[idx],TIME_DATE|TIME_SECONDS),
      TimeToString(gServer[idx],TIME_DATE|TIME_SECONDS),
      gEvent[idx],
      DoubleToString(targetZ,6),
      DoubleToString(gExt[idx],6),
      DoubleToString(d,6),
      action,ticket,err,
      DoubleToString(Bid,Digits),
      DoubleToString(Ask,Digits),
      DoubleToString(MarketInfo(Symbol(),MODE_SPREAD),1));
   FileClose(h);
}

int ND03_Open(int side)
{
   if(!InpTrade) return -10;
   if(ND03_HasPosition()) return -20;

   RefreshRates();
   int type=(side>0 ? OP_BUY : OP_SELL);
   double px=(side>0 ? Ask : Bid);
   px=NormalizeDouble(px,Digits);

   ResetLastError();
   int ticket=OrderSend(Symbol(),type,ND03_Lots(),px,InpSlippagePoints,0,0,
                        "ND03 USD NEWS",InpMagic,0,clrNONE);
   if(ticket<0)
      Print("ND03 OrderSend FAIL err=",GetLastError());
   else
      Print("ND03 ORDER OPENED ",Symbol()," ticket=",ticket,
            " side=",(side>0 ? "LONG" : "SHORT"));
   return ticket;
}

void ND03_ManageExit()
{
   if(InpHoldMinutes<=0) return;

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
         Print("ND03 EXIT ticket=",OrderTicket()," hold=",InpHoldMinutes,"m");
      else
         Print("ND03 EXIT FAIL ticket=",OrderTicket()," err=",GetLastError());
   }
}

void ND03_Process()
{
   datetime now=TimeCurrent();

   while(gNext<gN)
   {
      datetime ready=gServer[gNext]+InpDecisionDelayMinutes*60;

      if(now<ready) break;

      if(now>=ready+InpDecisionWindowMinutes*60)
      {
         gNext++;
         continue;
      }

      double targetZ=0.0;
      if(!ND03_TargetZ30(gServer[gNext],targetZ))
      {
         Print("ND03 TARGET WAIT event=",
               TimeToString(gServer[gNext],TIME_DATE|TIME_MINUTES));
         return;
      }

      double d=gExt[gNext]-targetZ;
      gProcessed++;

      if(MathAbs(d)<InpDislocationSigma)
      {
         gNoSignal++;
         ND03_Log(gNext,targetZ,d,"NO_SIGNAL",-1,0);
         Print("ND03 NO SIGNAL event=",
               TimeToString(gUtc[gNext],TIME_DATE|TIME_MINUTES),
               " targetZ=",DoubleToString(targetZ,3),
               " ext=",DoubleToString(gExt[gNext],3),
               " D=",DoubleToString(d,3));
         gNext++;
         continue;
      }

      gSignals++;
      int side=(d>0.0 ? 1 : -1);
      ResetLastError();
      int ticket=ND03_Open(side);
      int err=(ticket<0 ? GetLastError() : 0);
      string action;

      if(ticket>=0)
      {
         gOpened++;
         action=(side>0 ? "ORDER_LONG" : "ORDER_SHORT");
      }
      else if(ticket==-20)
      {
         gBlocked++;
         action="POSITION_BLOCKED";
      }
      else if(ticket==-10)
      {
         action=(side>0 ? "SIGNAL_LONG" : "SIGNAL_SHORT");
      }
      else
      {
         gFailed++;
         action="ORDER_FAILED";
      }

      ND03_Log(gNext,targetZ,d,action,ticket,err);
      Print("ND03 EVENT ",gEvent[gNext],
            " D=",DoubleToString(d,3),
            " action=",action);
      gNext++;
   }
}

int OnInit()
{
   if(!IsTesting() && !InpAllowOutsideTester)
   {
      Print("ND03 INIT FAILED: Strategy Tester only.");
      return INIT_FAILED;
   }

   if(StringFind(Symbol(),"XAUUSD",0)<0)
   {
      Print("ND03 INIT FAILED: this build is for XAUUSD tester only. Symbol=",Symbol());
      return INIT_FAILED;
   }

   if(!ND03_LoadSignals())
      return INIT_FAILED;

   Print("==================================================");
   Print("ND03 XAUUSD TESTER");
   Print("external USD source=USD26.csv; MT4 multi-symbol dependency=NONE");
   Print("rows=",gN," threshold=",DoubleToString(InpDislocationSigma,1),
         " hold=",InpHoldMinutes," lots=",DoubleToString(InpLots,2));
   Print("==================================================");
   return INIT_SUCCEEDED;
}

void OnTick()
{
   ND03_ManageExit();
   ND03_Process();
}

void OnDeinit(const int reason)
{
   Print("ND03 STOP reason=",reason,
         " next=",gNext,"/",gN,
         " processed=",gProcessed,
         " no_signal=",gNoSignal,
         " signals=",gSignals,
         " opened=",gOpened,
         " blocked=",gBlocked,
         " failed=",gFailed);
}
