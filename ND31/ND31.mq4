#property strict
#property version   "1.00"
#property description "ND31 DEMO multi-symbol news/dislocation trader"

#define CUR_N 8
#define FX_N 28
#define INST_N 44
#define VOL_BARS 288

input string InpNewsFile="NEWS.csv";
input double InpLots=0.10;
input double InpSigma=2.0;
input int    InpDelayMin=30;
input int    InpHoldMin=30;
input int    InpDecisionWindowMin=10;
input double InpMinMarginLevelPct=5000.0;
input int    InpSlippage=30;
input int    InpMagic=26092831;
input int    InpTimerSec=5;
input string InpTelemetryFile="ND31_EXECUTION.csv";

string CURS[CUR_N]={"AUD","CAD","CHF","EUR","GBP","JPY","NZD","USD"};

string FX[FX_N]={
"AUDCAD","AUDCHF","AUDJPY","AUDNZD","AUDUSD",
"CADCHF","CADJPY","CHFJPY",
"EURAUD","EURCAD","EURCHF","EURGBP","EURJPY","EURNZD","EURUSD",
"GBPAUD","GBPCAD","GBPCHF","GBPJPY","GBPNZD","GBPUSD",
"NZDCAD","NZDCHF","NZDJPY","NZDUSD","USDCAD","USDCHF","USDJPY"
};

string INST[INST_N]={
"USDCHF","GBPUSD","EURUSD","USDJPY","USDCAD","AUDUSD","EURGBP","EURAUD","EURCHF","EURJPY",
"GBPCHF","CADJPY","GBPJPY","AUDNZD","AUDCAD","AUDCHF","AUDJPY","CHFJPY","EURNZD","EURCAD",
"CADCHF","NZDJPY","NZDUSD","GBPAUD","GBPCAD","GBPNZD","NZDCAD","NZDCHF",
"XAUUSD","XAGUSD","XAUEUR","BTCUSD","ETHUSD","SOLUSD","DOGEUSD","ADAUSD","XRPUSD",
".DE40Cash",".JP225Cash",".US500Cash",".USTECHCash",".US30Cash","BRENT","WTI"
};

// 0=FX pair; 1=one-sided external currency driver.
int    InstType[INST_N];
string InstBase[INST_N];
string InstQuote[INST_N];
string InstDriver[INST_N];
bool   InstKnownIsBase[INST_N];

datetime NUtc[];
string   NCur[];
string   NName[];
bool     NDone[];
int      NN=0;

datetime LastManage=0;

// -----------------------------------------------------------------------------
// Symbol map is frozen in code: no MAP.csv.
// -----------------------------------------------------------------------------
void InitInstrumentMap()
{
   for(int i=0;i<INST_N;i++)
   {
      InstType[i]=1;
      InstBase[i]="";
      InstQuote[i]="";
      InstDriver[i]="";
      InstKnownIsBase[i]=false;

      int fi=FindFx(INST[i]);
      if(fi>=0)
      {
         InstType[i]=0;
         InstBase[i]=StringSubstr(FX[fi],0,3);
         InstQuote[i]=StringSubstr(FX[fi],3,3);
         continue;
      }

      string s=INST[i];

      if(s=="XAUUSD" || s=="XAGUSD" ||
         s=="BTCUSD" || s=="ETHUSD" || s=="SOLUSD" ||
         s=="DOGEUSD" || s=="ADAUSD" || s=="XRPUSD" ||
         s==".US500Cash" || s==".USTECHCash" || s==".US30Cash" ||
         s=="BRENT" || s=="WTI")
      {
         InstDriver[i]="USD";
         InstKnownIsBase[i]=false;
      }
      else if(s=="XAUEUR" || s==".DE40Cash")
      {
         InstDriver[i]="EUR";
         InstKnownIsBase[i]=false;
      }
      else if(s==".JP225Cash")
      {
         InstDriver[i]="JPY";
         InstKnownIsBase[i]=false;
      }
   }
}

int FindFx(string s)
{
   for(int i=0;i<FX_N;i++) if(FX[i]==s) return i;
   return -1;
}

bool IsCur(string c)
{
   for(int i=0;i<CUR_N;i++) if(CURS[i]==c) return true;
   return false;
}

datetime ParseUtc(string s)
{
   string x=s;
   StringReplace(x,"T"," ");
   StringReplace(x,"-",".");
   int z=StringFind(x,"Z");
   if(z>=0) x=StringSubstr(x,0,z);
   return StringToTime(x);
}

datetime AlignM5(datetime t)
{
   long x=(long)t;
   long r=x%300;
   if(r==0) return t;
   return (datetime)(x+(300-r));
}

int ServerUtcOffset()
{
   return (int)(TimeCurrent()-TimeGMT());
}

datetime UtcToServer(datetime utc)
{
   return utc+ServerUtcOffset();
}

bool LoadNews()
{
   int h=FileOpen(InpNewsFile,
                  FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_COMMON,';');
   if(h==INVALID_HANDLE)
   {
      Print("ND31 INIT FAIL: cannot open Common\\Files\\",InpNewsFile,
            " err=",GetLastError());
      return false;
   }

   NN=0;
   ArrayResize(NUtc,0);
   ArrayResize(NCur,0);
   ArrayResize(NName,0);
   ArrayResize(NDone,0);

   while(!FileIsEnding(h))
   {
      string ts=FileReadString(h);
      if(FileIsEnding(h) && ts=="") break;
      string cur=FileReadString(h);
      string impact=FileReadString(h);
      string name=FileReadString(h);

      if(ts=="UTC_TIME") continue;

      StringToUpper(cur);
      StringToUpper(impact);
      if(impact!="HIGH" || !IsCur(cur)) continue;

      datetime utc=ParseUtc(ts);
      if(utc<=0) continue;

      // Collapse simultaneous same-currency event cluster.
      if(NN>0 && NUtc[NN-1]==utc && NCur[NN-1]==cur)
      {
         if(StringFind(NName[NN-1],name)<0)
            NName[NN-1]=NName[NN-1]+" | "+name;
         continue;
      }

      int n=NN+1;
      ArrayResize(NUtc,n);
      ArrayResize(NCur,n);
      ArrayResize(NName,n);
      ArrayResize(NDone,n);

      NUtc[NN]=utc;
      NCur[NN]=cur;
      NName[NN]=name;
      NDone[NN]=false;
      NN=n;
   }

   FileClose(h);
   Print("ND31 NEWS clusters=",NN);
   return NN>0;
}

// -----------------------------------------------------------------------------
// Z30 core
// -----------------------------------------------------------------------------
bool SymbolZ30(string sym,datetime eventServer,double &z)
{
   z=0.0;
   datetime e=AlignM5(eventServer);

   int bars=iBars(sym,PERIOD_M5);
   if(bars<VOL_BARS+20) return false;

   int s0=iBarShift(sym,PERIOD_M5,e,false);
   int s30=iBarShift(sym,PERIOD_M5,e+1800,false);
   if(s0<0 || s30<0) return false;

   datetime t0=iTime(sym,PERIOD_M5,s0);
   datetime t30=iTime(sym,PERIOD_M5,s30);
   if(MathAbs((double)(t0-e))>300.0) return false;
   if(MathAbs((double)(t30-(e+1800)))>300.0) return false;
   if(s0+VOL_BARS+1>=bars) return false;

   double o0=iOpen(sym,PERIOD_M5,s0);
   double o30=iOpen(sym,PERIOD_M5,s30);
   if(o0<=0 || o30<=0) return false;

   double sum=0.0,sum2=0.0;
   int n=0;

   for(int k=1;k<=VOL_BARS;k++)
   {
      double newer=iOpen(sym,PERIOD_M5,s0+k);
      double older=iOpen(sym,PERIOD_M5,s0+k+1);
      if(newer<=0 || older<=0) return false;

      double r=MathLog(newer/older);
      sum+=r;
      sum2+=r*r;
      n++;
   }

   if(n<2) return false;
   double var=(sum2-sum*sum/n)/(n-1);
   if(var<=0) return false;

   z=MathLog(o30/o0)/(MathSqrt(var)*MathSqrt(6.0));
   return MathIsValidNumber(z);
}

bool BuildFxZ(datetime eventServer,double &z[])
{
   ArrayResize(z,FX_N);
   for(int i=0;i<FX_N;i++)
   {
      if(!SymbolZ30(FX[i],eventServer,z[i]))
      {
         Print("ND31 DATA WAIT fx=",FX[i],
               " event=",TimeToString(eventServer,TIME_DATE|TIME_MINUTES));
         return false;
      }
   }
   return true;
}

bool OrientedZ(string a,string b,double &z[],double &out)
{
   int i=FindFx(a+b);
   if(i>=0) { out=z[i]; return true; }

   i=FindFx(b+a);
   if(i>=0) { out=-z[i]; return true; }

   return false;
}

bool CurrencyStrength(string cur,double &z[],double &out)
{
   double sum=0.0;
   int n=0;

   for(int i=0;i<CUR_N;i++)
   {
      string other=CURS[i];
      if(other==cur) continue;

      double x=0.0;
      if(!OrientedZ(cur,other,z,x)) return false;

      sum+=x;
      n++;
   }

   if(n!=7) return false;
   out=sum/n;
   return MathIsValidNumber(out);
}

bool FxDislocation(string pair,double &z[],double &targetZ,double &external,double &d)
{
   int ti=FindFx(pair);
   if(ti<0) return false;

   string base=StringSubstr(pair,0,3);
   string quote=StringSubstr(pair,3,3);

   double sb=0.0,sq=0.0;
   int n=0;

   for(int i=0;i<CUR_N;i++)
   {
      string third=CURS[i];
      if(third==base || third==quote) continue;

      double bz=0.0,qz=0.0;
      if(!OrientedZ(base,third,z,bz)) return false;
      if(!OrientedZ(quote,third,z,qz)) return false;

      sb+=bz;
      sq+=qz;
      n++;
   }

   if(n!=6) return false;

   targetZ=z[ti];
   external=sb/n-sq/n;
   d=external-targetZ;
   return MathIsValidNumber(d);
}

// -----------------------------------------------------------------------------
// Execution telemetry
// -----------------------------------------------------------------------------
string IsoUtc(datetime t)
{
   if(t<=0) return "";
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ",
                       TimeYear(t),TimeMonth(t),TimeDay(t),
                       TimeHour(t),TimeMinute(t),TimeSeconds(t));
}

void Telemetry(int ni,string sym,string action,int side,
               double targetZ,double external,double d,
               double lots,double marginLevel,double freeBefore,double freeAfter,
               int ticket,int err,double openPx,double closePx,
               double pnl,double swap,double commission,
               datetime openTime,datetime closeTime)
{
   int h=FileOpen(InpTelemetryFile,
                  FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|
                  FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON,';');
   if(h==INVALID_HANDLE)
   {
      Print("ND31 TELEMETRY OPEN FAIL err=",GetLastError());
      return;
   }

   if(FileSize(h)==0)
      FileWrite(h,
         "UTC_NOW","SERVER_NOW","EVENT_UTC","CURRENCY","EVENT",
         "SYMBOL","ACTION","SIDE",
         "TARGET_Z30","EXTERNAL_Z30","D","SIGMA",
         "BID","ASK","SPREAD_POINTS","LOTS",
         "MARGIN_LEVEL_BEFORE","FREE_MARGIN_BEFORE","FREE_MARGIN_AFTER_CHECK",
         "TICKET","ERROR",
         "OPEN_PRICE","CLOSE_PRICE","PROFIT","SWAP","COMMISSION",
         "ORDER_OPEN_SERVER","ORDER_CLOSE_SERVER","ACTUAL_HOLD_SEC");

   string eventUtc="",cur="",eventName="";
   if(ni>=0 && ni<NN)
   {
      eventUtc=IsoUtc(NUtc[ni]);
      cur=NCur[ni];
      eventName=NName[ni];
   }

   double bid=0.0,ask=0.0,spread=0.0;
   int digits=5;
   if(sym!="")
   {
      bid=MarketInfo(sym,MODE_BID);
      ask=MarketInfo(sym,MODE_ASK);
      spread=MarketInfo(sym,MODE_SPREAD);
      digits=(int)MarketInfo(sym,MODE_DIGITS);
      if(digits<0) digits=5;
   }

   int holdSec=0;
   if(openTime>0 && closeTime>=openTime)
      holdSec=(int)(closeTime-openTime);

   FileSeek(h,0,SEEK_END);
   FileWrite(h,
      IsoUtc(TimeGMT()),
      TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),
      eventUtc,cur,eventName,
      sym,action,(side>0?"LONG":(side<0?"SHORT":"NONE")),
      DoubleToString(targetZ,6),
      DoubleToString(external,6),
      DoubleToString(d,6),
      DoubleToString(InpSigma,2),
      (sym==""?"":DoubleToString(bid,digits)),
      (sym==""?"":DoubleToString(ask,digits)),
      DoubleToString(spread,1),
      DoubleToString(lots,4),
      DoubleToString(marginLevel,2),
      DoubleToString(freeBefore,2),
      DoubleToString(freeAfter,2),
      ticket,err,
      DoubleToString(openPx,digits),
      DoubleToString(closePx,digits),
      DoubleToString(pnl,2),
      DoubleToString(swap,2),
      DoubleToString(commission,2),
      (openTime>0?TimeToString(openTime,TIME_DATE|TIME_SECONDS):""),
      (closeTime>0?TimeToString(closeTime,TIME_DATE|TIME_SECONDS):""),
      holdSec);
   FileFlush(h);
   FileClose(h);
}

// -----------------------------------------------------------------------------
// Trading
// -----------------------------------------------------------------------------
bool HasPosition(string sym)
{
   for(int i=OrdersTotal()-1;i>=0;i--)
   {
      if(!OrderSelect(i,SELECT_BY_POS,MODE_TRADES)) continue;
      if(OrderMagicNumber()!=InpMagic) continue;
      if(OrderSymbol()!=sym) continue;
      int t=OrderType();
      if(t==OP_BUY || t==OP_SELL) return true;
   }
   return false;
}

double MarginLevelPct()
{
   double m=AccountMargin();
   if(m<=0.0) return 1.0e12;
   return AccountEquity()/m*100.0;
}

int LotDigits(double step)
{
   if(step>=1.0) return 0;
   if(step>=0.1) return 1;
   if(step>=0.01) return 2;
   if(step>=0.001) return 3;
   return 4;
}

double LotsFor(string sym)
{
   double mn=MarketInfo(sym,MODE_MINLOT);
   double mx=MarketInfo(sym,MODE_MAXLOT);
   double st=MarketInfo(sym,MODE_LOTSTEP);
   if(st<=0) st=0.01;

   double x=MathMax(mn,MathMin(mx,InpLots));
   x=MathFloor(x/st+1e-9)*st;
   return NormalizeDouble(x,LotDigits(st));
}

int OpenOrder(int ni,string sym,int side,string comment,
              double targetZ,double external,double d)
{
   double ml=MarginLevelPct();
   double freeBefore=AccountFreeMargin();
   double lots=LotsFor(sym);

   if(HasPosition(sym))
   {
      Telemetry(ni,sym,"POSITION_BLOCKED",side,targetZ,external,d,
                lots,ml,freeBefore,freeBefore,-20,0,0,0,0,0,0,0,0);
      return -20;
   }

   if(ml<InpMinMarginLevelPct)
   {
      Print("ND31 MARGIN BLOCK symbol=",sym,
            " margin_level=",DoubleToString(ml,1));
      Telemetry(ni,sym,"MARGIN_BLOCKED",side,targetZ,external,d,
                lots,ml,freeBefore,freeBefore,-30,0,0,0,0,0,0,0,0);
      return -30;
   }

   int type=(side>0 ? OP_BUY : OP_SELL);

   RefreshRates();
   double bid=MarketInfo(sym,MODE_BID);
   double ask=MarketInfo(sym,MODE_ASK);
   double px=(side>0 ? ask : bid);
   int digits=(int)MarketInfo(sym,MODE_DIGITS);

   if(px<=0 || lots<=0)
   {
      Print("ND31 QUOTE/LOT FAIL symbol=",sym,
            " bid=",DoubleToString(bid,digits),
            " ask=",DoubleToString(ask,digits),
            " lots=",DoubleToString(lots,2));
      Telemetry(ni,sym,"QUOTE_OR_LOT_FAIL",side,targetZ,external,d,
                lots,ml,freeBefore,freeBefore,-40,0,0,0,0,0,0,0,0);
      return -40;
   }

   ResetLastError();
   double freeAfter=AccountFreeMarginCheck(sym,type,lots);
   int fmErr=GetLastError();
   if(freeAfter<=0 || fmErr==134)
   {
      Print("ND31 FREE MARGIN BLOCK symbol=",sym,
            " lots=",DoubleToString(lots,2),
            " err=",fmErr);
      Telemetry(ni,sym,"FREE_MARGIN_BLOCKED",side,targetZ,external,d,
                lots,ml,freeBefore,freeAfter,-31,fmErr,0,0,0,0,0,0,0);
      return -31;
   }

   ResetLastError();
   int ticket=OrderSend(sym,type,lots,NormalizeDouble(px,digits),
                        InpSlippage,0,0,comment,InpMagic,0,clrNONE);
   int err=(ticket<0 ? GetLastError() : 0);

   if(ticket<0)
   {
      Print("ND31 ORDER FAIL symbol=",sym," err=",err);
      Telemetry(ni,sym,"ORDER_FAILED",side,targetZ,external,d,
                lots,ml,freeBefore,freeAfter,ticket,err,0,0,0,0,0,0,0);
   }
   else
   {
      double openPx=px;
      datetime openTime=TimeCurrent();
      if(OrderSelect(ticket,SELECT_BY_TICKET,MODE_TRADES))
      {
         openPx=OrderOpenPrice();
         openTime=OrderOpenTime();
      }

      Print("ND31 ORDER OPENED symbol=",sym,
            " ticket=",ticket,
            " side=",(side>0?"LONG":"SHORT"),
            " lots=",DoubleToString(lots,2));
      Telemetry(ni,sym,"ORDER_OPENED",side,targetZ,external,d,
                lots,ml,freeBefore,freeAfter,ticket,0,openPx,0,0,0,0,openTime,0);
   }

   return ticket;
}

void ManageExits()
{
   datetime now=TimeCurrent();
   if(now==LastManage) return;
   LastManage=now;

   for(int i=OrdersTotal()-1;i>=0;i--)
   {
      if(!OrderSelect(i,SELECT_BY_POS,MODE_TRADES)) continue;
      if(OrderMagicNumber()!=InpMagic) continue;

      int type=OrderType();
      if(type!=OP_BUY && type!=OP_SELL) continue;
      datetime openTime=OrderOpenTime();
      if(now<openTime+InpHoldMin*60) continue;

      int ticket=OrderTicket();
      string sym=OrderSymbol();
      double lots=OrderLots();
      double openPx=OrderOpenPrice();
      int side=(type==OP_BUY ? 1 : -1);
      int digits=(int)MarketInfo(sym,MODE_DIGITS);
      double px=(type==OP_BUY ? MarketInfo(sym,MODE_BID) : MarketInfo(sym,MODE_ASK));
      double ml=MarginLevelPct();
      double freeBefore=AccountFreeMargin();

      if(px<=0)
      {
         Telemetry(-1,sym,"EXIT_QUOTE_FAIL",side,0,0,0,
                   lots,ml,freeBefore,freeBefore,ticket,0,openPx,0,0,0,0,openTime,0);
         continue;
      }

      ResetLastError();
      bool ok=OrderClose(ticket,lots,NormalizeDouble(px,digits),
                         InpSlippage,clrNONE);
      int err=(ok ? 0 : GetLastError());

      if(ok)
      {
         double closePx=px,pnl=0,swap=0,commission=0;
         datetime closeTime=TimeCurrent();
         if(OrderSelect(ticket,SELECT_BY_TICKET,MODE_HISTORY))
         {
            closePx=OrderClosePrice();
            closeTime=OrderCloseTime();
            pnl=OrderProfit();
            swap=OrderSwap();
            commission=OrderCommission();
         }

         Print("ND31 EXIT symbol=",sym,
               " ticket=",ticket,
               " hold=",InpHoldMin,"m");
         Telemetry(-1,sym,"ORDER_CLOSED",side,0,0,0,
                   lots,ml,freeBefore,AccountFreeMargin(),ticket,0,
                   openPx,closePx,pnl,swap,commission,openTime,closeTime);
      }
      else
      {
         Print("ND31 EXIT FAIL symbol=",sym,
               " ticket=",ticket,
               " err=",err);
         Telemetry(-1,sym,"EXIT_FAILED",side,0,0,0,
                   lots,ml,freeBefore,freeBefore,ticket,err,
                   openPx,0,0,0,0,openTime,0);
      }
   }
}

void ProcessEvent(int ni)
{
   string newsCur=NCur[ni];
   datetime eventServer=UtcToServer(NUtc[ni]);

   double z[];
   if(!BuildFxZ(eventServer,z))
   {
      Telemetry(ni,"","FX_DATA_WAIT",0,0,0,0,0,
                MarginLevelPct(),AccountFreeMargin(),AccountFreeMargin(),
                -1,0,0,0,0,0,0,0,0);
      return;
   }

   for(int i=0;i<INST_N;i++)
   {
      string sym=INST[i];

      bool relevant=false;
      if(InstType[i]==0)
         relevant=(InstBase[i]==newsCur || InstQuote[i]==newsCur);
      else
         relevant=(InstDriver[i]==newsCur);

      if(!relevant) continue;

      SymbolSelect(sym,true);

      double targetZ=0.0,external=0.0,d=0.0;
      bool ok=false;

      if(InstType[i]==0)
      {
         ok=FxDislocation(sym,z,targetZ,external,d);
      }
      else
      {
         double strength=0.0;
         if(CurrencyStrength(InstDriver[i],z,strength) &&
            SymbolZ30(sym,eventServer,targetZ))
         {
            external=(InstKnownIsBase[i] ? strength : -strength);
            d=external-targetZ;
            ok=true;
         }
      }

      if(!ok)
      {
         Print("ND31 CALC FAIL symbol=",sym,
               " news=",newsCur,
               " event=",TimeToString(NUtc[ni],TIME_DATE|TIME_MINUTES));
         Telemetry(ni,sym,"CALC_FAIL",0,targetZ,external,d,0,
                   MarginLevelPct(),AccountFreeMargin(),AccountFreeMargin(),
                   -1,0,0,0,0,0,0,0,0);
         continue;
      }

      int side=(d>0 ? 1 : -1);

      if(MathAbs(d)<InpSigma)
      {
         Print("ND31 NO SIGNAL symbol=",sym,
               " news=",newsCur,
               " D=",DoubleToString(d,3));
         Telemetry(ni,sym,"NO_SIGNAL",side,targetZ,external,d,LotsFor(sym),
                   MarginLevelPct(),AccountFreeMargin(),AccountFreeMargin(),
                   -1,0,0,0,0,0,0,0,0);
         continue;
      }

      string comment="ND31 "+newsCur;
      int ticket=OpenOrder(ni,sym,side,comment,targetZ,external,d);

      Print("ND31 SIGNAL symbol=",sym,
            " news=",newsCur,
            " event=",NName[ni],
            " targetZ=",DoubleToString(targetZ,3),
            " ext=",DoubleToString(external,3),
            " D=",DoubleToString(d,3),
            " ticket=",ticket);
   }

   NDone[ni]=true;
}

void ScanNews()
{
   datetime nowUtc=TimeGMT();

   for(int i=0;i<NN;i++)
   {
      if(NDone[i]) continue;

      datetime ready=NUtc[i]+InpDelayMin*60;
      if(nowUtc<ready) continue;

      if(nowUtc>=ready+InpDecisionWindowMin*60)
      {
         NDone[i]=true;
         continue;
      }

      ProcessEvent(i);
   }
}

int OnInit()
{
   if(!IsDemo())
   {
      Print("ND31 INIT FAIL: DEMO ACCOUNT ONLY.");
      return INIT_FAILED;
   }

   InitInstrumentMap();

   int missing=0;
   for(int i=0;i<INST_N;i++)
   {
      if(!SymbolSelect(INST[i],true))
      {
         Print("ND31 SYMBOL MISSING ",INST[i]);
         Telemetry(-1,INST[i],"SYMBOL_MISSING",0,0,0,0,0,
                   MarginLevelPct(),AccountFreeMargin(),AccountFreeMargin(),
                   -1,0,0,0,0,0,0,0,0);
         missing++;
      }
      else
      {
         Telemetry(-1,INST[i],"SYMBOL_READY",0,0,0,0,LotsFor(INST[i]),
                   MarginLevelPct(),AccountFreeMargin(),AccountFreeMargin(),
                   -1,0,0,0,0,0,0,0,0);
      }
   }

   for(int f=0;f<FX_N;f++)
      SymbolSelect(FX[f],true);

   if(!LoadNews()) return INIT_FAILED;

   EventSetTimer(MathMax(1,InpTimerSec));

   Print("==================================================");
   Print("ND31 DEMO START");
   Print("mode=TRADE_ONLY instruments=",INST_N,
         " missing=",missing,
         " sigma=",DoubleToString(InpSigma,1),
         " delay=",InpDelayMin,
         " hold=",InpHoldMin,
         " min_margin_level=",DoubleToString(InpMinMarginLevelPct,0),"%");
   Print("NEWS clusters=",NN,
         " account=",AccountNumber(),
         " demo=",IsDemo(),
         " telemetry=",InpTelemetryFile);
   Print("==================================================");

   return INIT_SUCCEEDED;
}

void OnTimer()
{
   ManageExits();
   ScanNews();
}

void OnTick()
{
   // Timer is the primary clock. Tick is only a fallback.
   ManageExits();
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("ND31 STOP reason=",reason);
}
