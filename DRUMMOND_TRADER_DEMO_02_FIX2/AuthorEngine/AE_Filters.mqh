#ifndef __AE_FILTERS_MQH__
#define __AE_FILTERS_MQH__

#include <AuthorEngine\AE_Congestion.mqh>

bool AE_HTPAligned(string sym,ENUM_TIMEFRAMES ltf,ENUM_TIMEFRAMES htf)
{
   int a=AE_ThreeCloseTrend(sym,ltf,1);
   int b=AE_ThreeCloseTrend(sym,htf,1);
   return(a!=AE_DIR_NONE && a==b);
}

int AE_HTPDirection(string sym,ENUM_TIMEFRAMES htf)
{
   return(AE_ThreeCloseTrend(sym,htf,1));
}

bool AE_PowerFlowingInFavor(string sym,ENUM_TIMEFRAMES ltf,ENUM_TIMEFRAMES htf,int direction)
{
   bool htp=(AE_HTPDirection(sym,htf)==direction);
   bool push=AE_PLDotPush(sym,ltf,direction) || AE_PLDotPush(sym,htf,direction);
   return(htp && push);
}

bool AE_ExhaustionEvidence(string sym,ENUM_TIMEFRAMES ltf,ENUM_TIMEFRAMES htf,int direction)
{
   double flo,fhi;AE_DotsForward23Zone(sym,ltf,flo,fhi);
   double px=AE_Close(sym,ltf,1);
   bool atForward=(flo>0.0 && px>=flo && px<=fhi);
   bool losing=AE_PLDotLosingPush(sym,ltf);
   bool htpNotStrong=(AE_HTPDirection(sym,htf)!=direction || AE_PLDotLosingPush(sym,htf));
   return((atForward || losing) && htpNotStrong);
}

bool AE_LiveRefreshWithTrend(string sym,ENUM_TIMEFRAMES ltf,ENUM_TIMEFRAMES htf,int direction)
{
   return(AE_IsLiveRefresh(sym,ltf) && AE_HTPDirection(sym,htf)==direction);
}

#endif
