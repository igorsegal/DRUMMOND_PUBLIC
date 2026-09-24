#ifndef __AE_CONGESTION_MQH__
#define __AE_CONGESTION_MQH__

#include <AuthorEngine\AE_Energy.mqh>

bool AE_IsCongestionEntrance(string sym,ENUM_TIMEFRAMES tf)
{
   AE_TRADE_STATE s=AE_CurrentTradeState(sym,tf);
   return(s==AE_STATE_CONGESTION_ENTRANCE_UP || s==AE_STATE_CONGESTION_ENTRANCE_DOWN);
}

bool AE_IsCongestionAction(string sym,ENUM_TIMEFRAMES tf)
{
   return(AE_CurrentTradeState(sym,tf)==AE_STATE_CONGESTION_ACTION);
}

bool AE_GetBlockArea(string sym,ENUM_TIMEFRAMES tf,double &low,double &high,string &compliance)
{
   AE_DotsBack23Zone(sym,tf,low,high);
   compliance="RECOVERED_2_3_DOTS_BACK";
   return(low>0.0 && high>0.0);
}

// Dotted Line setup is represented as a conjunction of recovered observable evidence.
// It is intentionally descriptive: no order entry is attached to this function.
bool AE_DottedSetupEvidence(string sym,ENUM_TIMEFRAMES ltf,ENUM_TIMEFRAMES htf,
                            int direction,string &reason)
{
   reason="";
   int htp=AE_ThreeCloseTrend(sym,htf,1);
   if(htp==AE_DIR_NONE){reason="NO_HTP_CONTEXT";return(false);}

   bool counterLines=(AE_CountValidLines(sym,ltf,-direction)>=2);
   if(!counterLines){reason="NO_COUNTER_LINE_CLUSTER";return(false);}

   if(!AE_PLDotLosingPush(sym,ltf)){reason="PLDOT_NOT_LOSING_PUSH";return(false);}

   AE_TRADE_STATE s=AE_CurrentTradeState(sym,ltf);
   bool entrance=(s==AE_STATE_CONGESTION_ENTRANCE_UP || s==AE_STATE_CONGESTION_ENTRANCE_DOWN);
   if(!entrance){reason="NO_CONGESTION_ENTRANCE";return(false);}

   reason="RECOVERED_DOTTED_EVIDENCE";
   return(true);
}

bool AE_IsStrongBlockEvidence(string sym,ENUM_TIMEFRAMES ltf,ENUM_TIMEFRAMES htf)
{
   double blo,bhi;string cp;
   if(!AE_GetBlockArea(sym,ltf,blo,bhi,cp)) return(false);
   double hp=AE_StaticPLDot(sym,htf,0);
   if(hp<=0.0) return(false);
   double tol=AE_Point(sym)*10.0;
   bool htpNear=(hp>=blo-tol && hp<=bhi+tol);
   bool lineSupport=(AE_CountValidLines(sym,ltf,AE_DIR_UP)>0 || AE_CountValidLines(sym,ltf,AE_DIR_DOWN)>0);
   return(htpNear && lineSupport);
}

#endif
