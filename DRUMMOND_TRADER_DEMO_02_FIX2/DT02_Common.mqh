#ifndef __DT02_COMMON_MQH__
#define __DT02_COMMON_MQH__

// Общий код DRUMMOND TRADER DEMO 02.
// Watcher использует его для анализа нескольких символов.
// Executor использует те же геометрические правила только для повторной проверки исполнения.

enum D2_SIDE
{
   D2_SIDE_NONE  = 0,
   D2_SIDE_LONG  = 1,
   D2_SIDE_SHORT = -1
};

enum D2_DIRECTION_MODE
{
   D2_DIR_BOTH       = 0,
   D2_DIR_SHORT_ONLY = 1,
   D2_DIR_LONG_ONLY  = 2
};

enum D2_LINE_ID
{
   D2_LINE_51_UP = 0,
   D2_LINE_51_DOWN,
   D2_LINE_52_UP,
   D2_LINE_52_DOWN,
   D2_LINE_59_UP,
   D2_LINE_59_DOWN
};

struct D2TradePlan
{
   string   symbol;
   datetime decision_time;
   int      side;
   int      trend_direction;
   int      htp_direction;
   double   decision_pldot;
   double   entry_reference;
   double   stop_price;
   double   target_price;
   double   rr;
   string   signal_name;
};

void D2_ResetPlan(D2TradePlan &p)
{
   p.symbol="";
   p.decision_time=0;
   p.side=D2_SIDE_NONE;
   p.trend_direction=0;
   p.htp_direction=0;
   p.decision_pldot=0.0;
   p.entry_reference=0.0;
   p.stop_price=0.0;
   p.target_price=0.0;
   p.rr=0.0;
   p.signal_name="";
}

string D2_SideText(int side)
{
   if(side==D2_SIDE_LONG) return("LONG");
   if(side==D2_SIDE_SHORT) return("SHORT");
   return("NONE");
}

string D2_DirectionModeText(D2_DIRECTION_MODE mode)
{
   if(mode==D2_DIR_SHORT_ONLY) return("SHORT_ONLY");
   if(mode==D2_DIR_LONG_ONLY) return("LONG_ONLY");
   return("BOTH");
}

double D2_Point(string sym)
{
   return(MarketInfo(sym,MODE_POINT));
}

int D2_Digits(string sym)
{
   return((int)MarketInfo(sym,MODE_DIGITS));
}

double D2_NormalizePrice(string sym,double price)
{
   return(NormalizeDouble(price,D2_Digits(sym)));
}

int D2_LotDigits(double step)
{
   int d=0;
   while(d<8 && MathAbs(step-NormalizeDouble(step,d))>1e-10) d++;
   return(d);
}

double D2_NormalizeLots(string sym,double requested)
{
   double minLot=MarketInfo(sym,MODE_MINLOT);
   double maxLot=MarketInfo(sym,MODE_MAXLOT);
   double step=MarketInfo(sym,MODE_LOTSTEP);
   if(minLot<=0.0) minLot=0.01;
   if(step<=0.0) step=minLot;
   double lots=requested;
   if(lots<minLot) lots=minLot;
   if(maxLot>0.0 && lots>maxLot) lots=maxLot;
   lots=MathFloor((lots+1e-12)/step)*step;
   if(lots<minLot) lots=minLot;
   return(NormalizeDouble(lots,D2_LotDigits(step)));
}

double D2_MinimumBrokerLot(string sym)
{
   double minLot=MarketInfo(sym,MODE_MINLOT);
   if(minLot<=0.0) minLot=0.01;
   return(D2_NormalizeLots(sym,minLot));
}

bool D2_HasBars(string sym,ENUM_TIMEFRAMES tf,int required)
{
   return(iBars(sym,tf)>=required);
}

double D2_Typical(string sym,ENUM_TIMEFRAMES tf,int shift)
{
   double h=iHigh(sym,tf,shift);
   double l=iLow(sym,tf,shift);
   double c=iClose(sym,tf,shift);
   if(h<=0.0 || l<=0.0 || c<=0.0) return(0.0);
   return((h+l+c)/3.0);
}

double D2_PLdot(string sym,ENUM_TIMEFRAMES tf,int shift)
{
   if(!D2_HasBars(sym,tf,shift+5)) return(0.0);
   double a1=D2_Typical(sym,tf,shift+1);
   double a2=D2_Typical(sym,tf,shift+2);
   double a3=D2_Typical(sym,tf,shift+3);
   if(a1<=0.0 || a2<=0.0 || a3<=0.0) return(0.0);
   return((a1+a2+a3)/3.0);
}

int D2_CloseSideOfDot(string sym,ENUM_TIMEFRAMES tf,int shift)
{
   double dot=D2_PLdot(sym,tf,shift);
   double close=iClose(sym,tf,shift);
   if(dot<=0.0 || close<=0.0) return(0);
   double eps=D2_Point(sym)*0.1;
   if(close>dot+eps) return(1);
   if(close<dot-eps) return(-1);
   return(0);
}

int D2_TrendDirection(string sym,ENUM_TIMEFRAMES tf,int firstShift)
{
   int side=0;
   for(int s=firstShift;s<firstShift+3;s++)
   {
      int current=D2_CloseSideOfDot(sym,tf,s);
      if(current==0) return(0);
      if(side==0) side=current;
      else if(side!=current) return(0);
   }
   return(side);
}

bool D2_IsClosedBarRefresh(string sym,ENUM_TIMEFRAMES tf,int direction,int shift)
{
   double dot=D2_PLdot(sym,tf,shift);
   if(dot<=0.0) return(false);
   double high=iHigh(sym,tf,shift);
   double low=iLow(sym,tf,shift);
   double close=iClose(sym,tf,shift);
   if(direction>0) return(low<=dot && close>dot);
   if(direction<0) return(high>=dot && close<dot);
   return(false);
}

double D2_Extend12(double p1,double p2)
{
   return(2.0*p1-p2);
}

bool D2_GetLine(string sym,D2_LINE_ID id,ENUM_TIMEFRAMES tf,double &value,int &direction)
{
   value=0.0;
   direction=0;
   if(!D2_HasBars(sym,tf,6)) return(false);
   double h1=iHigh(sym,tf,1), h2=iHigh(sym,tf,2);
   double l1=iLow(sym,tf,1),  l2=iLow(sym,tf,2);
   double c1=iClose(sym,tf,1), x=0.0;

   switch(id)
   {
      case D2_LINE_51_UP:
         if(!(h1<h2)) return(false); x=D2_Extend12(h1,h2); if(!(x<c1)) return(false); direction=1; break;
      case D2_LINE_51_DOWN:
         if(!(l1>l2)) return(false); x=D2_Extend12(l1,l2); if(!(x>c1)) return(false); direction=-1; break;
      case D2_LINE_52_UP:
         if(!(l1<l2)) return(false); x=D2_Extend12(l1,l2); direction=1; break;
      case D2_LINE_52_DOWN:
         if(!(h1>h2)) return(false); x=D2_Extend12(h1,h2); direction=-1; break;
      case D2_LINE_59_UP:
         x=D2_Extend12(l1,h2); direction=1; break;
      case D2_LINE_59_DOWN:
         x=D2_Extend12(h1,l2); direction=-1; break;
      default:
         return(false);
   }

   if(x<=0.0) return(false);
   value=D2_NormalizePrice(sym,x);
   return(true);
}

bool D2_ResolveNearestHTPTarget(string sym,int side,ENUM_TIMEFRAMES htp,double entry,double &target)
{
   target=0.0;
   D2_LINE_ID ids[3];
   if(side==D2_SIDE_LONG)
   {
      ids[0]=D2_LINE_51_DOWN; ids[1]=D2_LINE_52_DOWN; ids[2]=D2_LINE_59_DOWN;
   }
   else if(side==D2_SIDE_SHORT)
   {
      ids[0]=D2_LINE_51_UP; ids[1]=D2_LINE_52_UP; ids[2]=D2_LINE_59_UP;
   }
   else return(false);

   bool found=false;
   for(int i=0;i<3;i++)
   {
      double level; int direction;
      if(!D2_GetLine(sym,ids[i],htp,level,direction)) continue;
      if(side==D2_SIDE_LONG)
      {
         if(level<=entry) continue;
         if(!found || level<target){ target=level; found=true; }
      }
      else
      {
         if(level>=entry) continue;
         if(!found || level>target){ target=level; found=true; }
      }
   }
   if(!found) return(false);
   target=D2_NormalizePrice(sym,target);
   return(true);
}

bool D2_ResolveStructuralStop(string sym,int side,ENUM_TIMEFRAMES tf,double entry,int bufferPoints,double &stop)
{
   stop=0.0;
   D2_LINE_ID ids[3];
   if(side==D2_SIDE_LONG)
   {
      ids[0]=D2_LINE_51_UP; ids[1]=D2_LINE_52_UP; ids[2]=D2_LINE_59_UP;
   }
   else if(side==D2_SIDE_SHORT)
   {
      ids[0]=D2_LINE_51_DOWN; ids[1]=D2_LINE_52_DOWN; ids[2]=D2_LINE_59_DOWN;
   }
   else return(false);

   bool found=false;
   for(int i=0;i<3;i++)
   {
      double level; int direction;
      if(!D2_GetLine(sym,ids[i],tf,level,direction)) continue;
      if(side==D2_SIDE_LONG)
      {
         if(level>=entry) continue;
         if(!found || level<stop){ stop=level; found=true; }
      }
      else
      {
         if(level<=entry) continue;
         if(!found || level>stop){ stop=level; found=true; }
      }
   }
   if(!found) return(false);

   double buffer=MathMax(1,bufferPoints)*D2_Point(sym);
   if(side==D2_SIDE_LONG) stop-=buffer;
   else stop+=buffer;
   stop=D2_NormalizePrice(sym,stop);
   return(true);
}

bool D2_DirectionAllowed(int side,D2_DIRECTION_MODE mode)
{
   if(side!=D2_SIDE_LONG && side!=D2_SIDE_SHORT) return(false);
   if(mode==D2_DIR_BOTH) return(true);
   if(mode==D2_DIR_SHORT_ONLY) return(side==D2_SIDE_SHORT);
   if(mode==D2_DIR_LONG_ONLY) return(side==D2_SIDE_LONG);
   return(false);
}

double D2_InitialRR(double entry,double stop,double target)
{
   double risk=MathAbs(entry-stop);
   double reward=MathAbs(target-entry);
   if(risk<=0.0 || reward<0.0) return(-1.0);
   return(reward/risk);
}

// 12 последовательных шлюзов. Процент — только глубина прохождения фильтров,
// а не вероятность успеха и не confidence score.
bool D2_EvaluateSymbol(string sym,
                       ENUM_TIMEFRAMES decisionTF,
                       ENUM_TIMEFRAMES htpTF,
                       int protectionBufferPoints,
                       D2_DIRECTION_MODE directionMode,
                       double rrMin,
                       double rrMax,
                       D2TradePlan &plan,
                       string &reason,
                       int &gatesPassed,
                       int &gatesTotal)
{
   D2_ResetPlan(plan);
   plan.symbol=sym;
   gatesPassed=0;
   gatesTotal=12;
   reason="";

   if(!D2_HasBars(sym,decisionTF,20)){ reason="NO_DECISION_HISTORY"; return(false); }
   gatesPassed++;

   if(!D2_HasBars(sym,htpTF,20)){ reason="NO_HTP_HISTORY"; return(false); }
   gatesPassed++;

   int trend=D2_TrendDirection(sym,decisionTF,1);
   if(trend==0){ reason="NO_DECISION_TREND"; return(false); }
   gatesPassed++;

   int htpTrend=D2_TrendDirection(sym,htpTF,1);
   if(htpTrend==0){ reason="NO_HTP_TREND"; return(false); }
   gatesPassed++;

   if(htpTrend!=trend){ reason="HTP_DIRECTION_CONFLICT"; return(false); }
   gatesPassed++;

   if(!D2_IsClosedBarRefresh(sym,decisionTF,trend,1)){ reason="NO_PLDOT_REFRESH"; return(false); }
   gatesPassed++;

   double ask=MarketInfo(sym,MODE_ASK);
   double bid=MarketInfo(sym,MODE_BID);
   double entry=(trend>0?ask:bid);
   if(entry<=0.0){ reason="NO_EXECUTION_QUOTE"; return(false); }
   gatesPassed++;

   int side=(trend>0?D2_SIDE_LONG:D2_SIDE_SHORT);
   double target=0.0;
   if(!D2_ResolveNearestHTPTarget(sym,side,htpTF,entry,target))
   { reason="NO_HTP_TARGET"; return(false); }
   gatesPassed++;

   double stop=0.0;
   if(!D2_ResolveStructuralStop(sym,side,decisionTF,entry,protectionBufferPoints,stop))
   { reason="NO_STRUCTURAL_PROTECTION"; return(false); }
   gatesPassed++;

   if(side==D2_SIDE_LONG)
   {
      if(!(stop<entry && target>entry)){ reason="INVALID_LONG_GEOMETRY"; return(false); }
   }
   else
   {
      if(!(stop>entry && target<entry)){ reason="INVALID_SHORT_GEOMETRY"; return(false); }
   }
   gatesPassed++;

   if(!D2_DirectionAllowed(side,directionMode))
   {
      reason=(side==D2_SIDE_LONG?"DIRECTION_GATE_LONG_BLOCKED":"DIRECTION_GATE_SHORT_BLOCKED");
      return(false);
   }
   gatesPassed++;

   double rr=D2_InitialRR(entry,stop,target);
   if(rr<0.0 || !MathIsValidNumber(rr)){ reason="RR_GATE_INVALID"; return(false); }
   if(rr<rrMin){ reason="RR_GATE_BELOW_MIN"; return(false); }
   if(rrMax>0.0 && rr>=rrMax){ reason="RR_GATE_AT_OR_ABOVE_MAX"; return(false); }
   gatesPassed++;

   plan.decision_time=iTime(sym,decisionTF,1);
   plan.side=side;
   plan.trend_direction=trend;
   plan.htp_direction=htpTrend;
   plan.decision_pldot=D2_PLdot(sym,decisionTF,1);
   plan.entry_reference=D2_NormalizePrice(sym,entry);
   plan.stop_price=stop;
   plan.target_price=target;
   plan.rr=rr;
   plan.signal_name="CONSERVATIVE_TREND_PLDOT_REFRESH_HTP_ALIGNED";
   reason="FULL_PASS";
   return(true);
}

string D2_SignalId(string sym,datetime decisionTime,int side)
{
   return(sym+"_"+IntegerToString((int)decisionTime)+"_"+(side==D2_SIDE_LONG?"L":"S"));
}

bool D2_OneOurPositionOnSymbol(string sym,int magic)
{
   for(int i=OrdersTotal()-1;i>=0;i--)
   {
      if(!OrderSelect(i,SELECT_BY_POS,MODE_TRADES)) continue;
      if(OrderSymbol()!=sym) continue;
      if(OrderMagicNumber()!=magic) continue;
      if(OrderType()==OP_BUY || OrderType()==OP_SELL) return(true);
   }
   return(false);
}

bool D2_CheckBrokerDistances(string sym,int side,double price,double sl,double tp,string &reason)
{
   double point=D2_Point(sym);
   int stopLevelPoints=(int)MarketInfo(sym,MODE_STOPLEVEL);
   double minDistance=MathMax(0,stopLevelPoints)*point;
   if(side==D2_SIDE_LONG)
   {
      if(!(sl<price && tp>price)){ reason="BROKER_LONG_DIRECTION_INVALID"; return(false); }
      if(price-sl<minDistance){ reason="SL_TOO_CLOSE"; return(false); }
      if(tp-price<minDistance){ reason="TP_TOO_CLOSE"; return(false); }
   }
   else if(side==D2_SIDE_SHORT)
   {
      if(!(sl>price && tp<price)){ reason="BROKER_SHORT_DIRECTION_INVALID"; return(false); }
      if(sl-price<minDistance){ reason="SL_TOO_CLOSE"; return(false); }
      if(price-tp<minDistance){ reason="TP_TOO_CLOSE"; return(false); }
   }
   else
   {
      reason="SIDE_NONE";
      return(false);
   }
   reason="BROKER_DISTANCES_OK";
   return(true);
}

bool D2_ProjectedMarginLevelOK(string sym,int side,double lots,double minLevelPct,double &projectedLevel,string &reason)
{
   projectedLevel=0.0;
   int command=(side==D2_SIDE_LONG?OP_BUY:OP_SELL);
   ResetLastError();
   double freeAfter=AccountFreeMarginCheck(sym,command,lots);
   int err=GetLastError();
   if(freeAfter<=0.0 || err==134)
   {
      reason="NOT_ENOUGH_MARGIN";
      return(false);
   }

   double equity=AccountEquity();
   double projectedUsed=equity-freeAfter;
   if(projectedUsed<=0.0)
   {
      projectedLevel=999999999.0;
      reason="PROJECTED_MARGIN_LEVEL_OK";
      return(true);
   }

   projectedLevel=(equity/projectedUsed)*100.0;
   if(minLevelPct>0.0 && projectedLevel<minLevelPct)
   {
      reason="PROJECTED_MARGIN_LEVEL_BELOW_MIN";
      return(false);
   }
   reason="PROJECTED_MARGIN_LEVEL_OK";
   return(true);
}

#endif
