#ifndef __AE_DOTS_MQH__
#define __AE_DOTS_MQH__

#include <AuthorEngine\AE_Utils.mqh>

double AE_StaticPLDot(string sym,ENUM_TIMEFRAMES tf,int shift=0)
{
   if(!AE_HasBars(sym,tf,shift+5)) return(0.0);
   double a=AE_Typical(sym,tf,shift+1);
   double b=AE_Typical(sym,tf,shift+2);
   double c=AE_Typical(sym,tf,shift+3);
   if(a<=0.0 || b<=0.0 || c<=0.0) return(0.0);
   return(AE_Normalize(sym,(a+b+c)/3.0));
}

// Author live point: current forming-bar typical + two previous typicals.
// Current close proxy is current Bid, while H[0]/L[0] are live bar extremes.
double AE_LivePLDot(string sym,ENUM_TIMEFRAMES tf)
{
   if(!AE_HasBars(sym,tf,4)) return(0.0);
   double h0=AE_High(sym,tf,0),l0=AE_Low(sym,tf,0),px=MarketInfo(sym,MODE_BID);
   if(px<=0.0) px=AE_Close(sym,tf,0);
   double a1=AE_Typical(sym,tf,1),a2=AE_Typical(sym,tf,2);
   if(h0<=0.0 || l0<=0.0 || px<=0.0 || a1<=0.0 || a2<=0.0) return(0.0);
   double liveTypical=(h0+l0+px)/3.0;
   return(AE_Normalize(sym,(liveTypical+a1+a2)/3.0));
}

double AE_OneOneDot(string sym,ENUM_TIMEFRAMES tf,int shift=0)
{
   return(AE_Typical(sym,tf,shift+1));
}

int AE_PLDirection(string sym,ENUM_TIMEFRAMES tf)
{
   double p0=AE_StaticPLDot(sym,tf,0),p1=AE_StaticPLDot(sym,tf,1);
   if(p0<=0.0 || p1<=0.0) return(AE_DIR_NONE);
   return(AE_Sign(p0-p1,AE_Point(sym)*0.1));
}

double AE_DotDistance(string sym,ENUM_TIMEFRAMES tf,int shift=0)
{
   double a=AE_StaticPLDot(sym,tf,shift),b=AE_StaticPLDot(sym,tf,shift+1);
   if(a<=0.0 || b<=0.0) return(0.0);
   return(MathAbs(a-b));
}

bool AE_DotDistanceExpanding(string sym,ENUM_TIMEFRAMES tf)
{
   double d0=AE_DotDistance(sym,tf,0),d1=AE_DotDistance(sym,tf,1);
   return(d0>d1 && d1>0.0);
}

bool AE_DotDistanceContracting(string sym,ENUM_TIMEFRAMES tf)
{
   double d0=AE_DotDistance(sym,tf,0),d1=AE_DotDistance(sym,tf,1);
   return(d0<d1 && d0>=0.0 && d1>0.0);
}

bool AE_DotInPreviousRange(string sym,ENUM_TIMEFRAMES tf,int shift=0)
{
   double p=AE_StaticPLDot(sym,tf,shift);
   if(p<=0.0) return(false);
   return(AE_Inside(p,AE_Low(sym,tf,shift+1),AE_High(sym,tf,shift+1)));
}

int AE_CloseToDot(string sym,ENUM_TIMEFRAMES tf,int shift=1)
{
   double p=AE_StaticPLDot(sym,tf,shift);
   double c=AE_Close(sym,tf,shift);
   if(p<=0.0 || c<=0.0) return(AE_DIR_NONE);
   return(AE_Sign(c-p,AE_Point(sym)*0.1));
}

// Main Channel Line: line through two consecutive static PL Dots.
double AE_MCLineNow(string sym,ENUM_TIMEFRAMES tf)
{
   double p0=AE_StaticPLDot(sym,tf,0),p1=AE_StaticPLDot(sym,tf,1);
   if(p0<=0.0 || p1<=0.0) return(0.0);
   return(AE_Normalize(sym,2.0*p0-p1));
}

double AE_RefreshHigh(string sym,ENUM_TIMEFRAMES tf)
{
   double s=AE_StaticPLDot(sym,tf,0),l=AE_LivePLDot(sym,tf);
   if(s<=0.0 || l<=0.0) return(0.0);
   return(MathMax(s,l));
}

double AE_RefreshLow(string sym,ENUM_TIMEFRAMES tf)
{
   double s=AE_StaticPLDot(sym,tf,0),l=AE_LivePLDot(sym,tf);
   if(s<=0.0 || l<=0.0) return(0.0);
   return(MathMin(s,l));
}

bool AE_IsLiveRefresh(string sym,ENUM_TIMEFRAMES tf)
{
   double lo=AE_RefreshLow(sym,tf),hi=AE_RefreshHigh(sym,tf);
   double p=AE_CurrentPrice(sym);
   return(lo>0.0 && hi>0.0 && p>=lo && p<=hi);
}

// Historical 2-3 dots back zone. This is a zone, not a single guessed line.
void AE_DotsBack23Zone(string sym,ENUM_TIMEFRAMES tf,double &lo,double &hi)
{
   double p2=AE_StaticPLDot(sym,tf,2),p3=AE_StaticPLDot(sym,tf,3);
   lo=MathMin(p2,p3); hi=MathMax(p2,p3);
}

// Forward projection from current dot momentum. Kept as research geometry;
// never used as a trading gate unless separately validated.
void AE_DotsForward23Zone(string sym,ENUM_TIMEFRAMES tf,double &lo,double &hi)
{
   double p0=AE_StaticPLDot(sym,tf,0),p1=AE_StaticPLDot(sym,tf,1);
   if(p0<=0.0 || p1<=0.0){ lo=0.0;hi=0.0;return; }
   double d=p0-p1;
   double p2=p0+2.0*d,p3=p0+3.0*d;
   lo=MathMin(p2,p3); hi=MathMax(p2,p3);
}

#endif
