#ifndef __AE_STATE_MQH__
#define __AE_STATE_MQH__

#include <AuthorEngine\AE_Lines.mqh>

enum AE_TRADE_STATE
{
   AE_STATE_UNKNOWN=0,
   AE_STATE_TREND_RUN_UP,
   AE_STATE_TREND_RUN_DOWN,
   AE_STATE_CONGESTION_ENTRANCE_UP,
   AE_STATE_CONGESTION_ENTRANCE_DOWN,
   AE_STATE_CONGESTION_ACTION,
   AE_STATE_CONGESTION_EXIT_UP,
   AE_STATE_CONGESTION_EXIT_DOWN,
   AE_STATE_TREND_REVERSAL_UP,
   AE_STATE_TREND_REVERSAL_DOWN
};

string AE_StateText(AE_TRADE_STATE s)
{
   if(s==AE_STATE_TREND_RUN_UP) return("TREND_RUN_UP");
   if(s==AE_STATE_TREND_RUN_DOWN) return("TREND_RUN_DOWN");
   if(s==AE_STATE_CONGESTION_ENTRANCE_UP) return("CONGESTION_ENTRANCE_UP");
   if(s==AE_STATE_CONGESTION_ENTRANCE_DOWN) return("CONGESTION_ENTRANCE_DOWN");
   if(s==AE_STATE_CONGESTION_ACTION) return("CONGESTION_ACTION");
   if(s==AE_STATE_CONGESTION_EXIT_UP) return("CONGESTION_EXIT_UP");
   if(s==AE_STATE_CONGESTION_EXIT_DOWN) return("CONGESTION_EXIT_DOWN");
   if(s==AE_STATE_TREND_REVERSAL_UP) return("TREND_REVERSAL_UP");
   if(s==AE_STATE_TREND_REVERSAL_DOWN) return("TREND_REVERSAL_DOWN");
   return("UNKNOWN");
}

int AE_ThreeCloseTrend(string sym,ENUM_TIMEFRAMES tf,int firstShift=1)
{
   int d=0;
   for(int s=firstShift;s<firstShift+3;s++)
   {
      double dot=AE_StaticPLDot(sym,tf,s);
      double c=AE_Close(sym,tf,s);
      if(dot<=0.0 || c<=0.0) return(AE_DIR_NONE);
      int x=AE_Sign(c-dot,AE_Point(sym)*0.1);
      if(x==AE_DIR_NONE) return(AE_DIR_NONE);
      if(d==0) d=x; else if(d!=x) return(AE_DIR_NONE);
   }
   return(d);
}

// Recovered Lesson 12 core: three same-side closes = trend;
// first opposite close immediately after trend = congestion entrance.
AE_TRADE_STATE AE_CurrentTradeState(string sym,ENUM_TIMEFRAMES tf)
{
   if(!AE_HasBars(sym,tf,12)) return(AE_STATE_UNKNOWN);

   int nowTrend=AE_ThreeCloseTrend(sym,tf,1);
   if(nowTrend==AE_DIR_UP) return(AE_STATE_TREND_RUN_UP);
   if(nowTrend==AE_DIR_DOWN) return(AE_STATE_TREND_RUN_DOWN);

   int prevTrend=AE_ThreeCloseTrend(sym,tf,2);
   double dot1=AE_StaticPLDot(sym,tf,1),c1=AE_Close(sym,tf,1);
   if(prevTrend==AE_DIR_UP && c1<dot1) return(AE_STATE_CONGESTION_ENTRANCE_DOWN);
   if(prevTrend==AE_DIR_DOWN && c1>dot1) return(AE_STATE_CONGESTION_ENTRANCE_UP);

   // If no clean trend is present, classify the working range as congestion action.
   return(AE_STATE_CONGESTION_ACTION);
}

bool AE_PLDotPush(string sym,ENUM_TIMEFRAMES tf,int direction)
{
   double p0=AE_StaticPLDot(sym,tf,0),p1=AE_StaticPLDot(sym,tf,1),p2=AE_StaticPLDot(sym,tf,2);
   if(p0<=0.0 || p1<=0.0 || p2<=0.0) return(false);
   if(direction==AE_DIR_UP) return(p0>p1 && p1>p2);
   if(direction==AE_DIR_DOWN) return(p0<p1 && p1<p2);
   return(false);
}

bool AE_PLDotLosingPush(string sym,ENUM_TIMEFRAMES tf)
{
   return(AE_DotDistanceContracting(sym,tf) || AE_DotInPreviousRange(sym,tf,0));
}

// Historical block zone = zone of 2-3 prior PL dots.
bool AE_BlockZone(string sym,ENUM_TIMEFRAMES tf,double &low,double &high)
{
   AE_DotsBack23Zone(sym,tf,low,high);
   return(low>0.0 && high>0.0);
}

#endif
