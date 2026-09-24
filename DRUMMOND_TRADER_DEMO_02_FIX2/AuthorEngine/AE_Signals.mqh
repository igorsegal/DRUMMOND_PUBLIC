#ifndef __AE_SIGNALS_MQH__
#define __AE_SIGNALS_MQH__

#include <AuthorEngine\AE_Filters.mqh>

enum AE_RESEARCH_SIGNAL
{
   AE_SIG_NONE=0,
   AE_SIG_TREND_REFRESH_UP,
   AE_SIG_TREND_REFRESH_DOWN,
   AE_SIG_CONGESTION_ENTRANCE_UP,
   AE_SIG_CONGESTION_ENTRANCE_DOWN,
   AE_SIG_DOTTED_EVIDENCE_UP,
   AE_SIG_DOTTED_EVIDENCE_DOWN,
   AE_SIG_EXHAUSTION_UP,
   AE_SIG_EXHAUSTION_DOWN,
   AE_SIG_BLOCK_STRONG
};

string AE_SignalText(AE_RESEARCH_SIGNAL s)
{
   if(s==AE_SIG_TREND_REFRESH_UP) return("TREND_REFRESH_UP");
   if(s==AE_SIG_TREND_REFRESH_DOWN) return("TREND_REFRESH_DOWN");
   if(s==AE_SIG_CONGESTION_ENTRANCE_UP) return("CONGESTION_ENTRANCE_UP");
   if(s==AE_SIG_CONGESTION_ENTRANCE_DOWN) return("CONGESTION_ENTRANCE_DOWN");
   if(s==AE_SIG_DOTTED_EVIDENCE_UP) return("DOTTED_EVIDENCE_UP");
   if(s==AE_SIG_DOTTED_EVIDENCE_DOWN) return("DOTTED_EVIDENCE_DOWN");
   if(s==AE_SIG_EXHAUSTION_UP) return("EXHAUSTION_UP");
   if(s==AE_SIG_EXHAUSTION_DOWN) return("EXHAUSTION_DOWN");
   if(s==AE_SIG_BLOCK_STRONG) return("BLOCK_STRONG");
   return("NONE");
}

AE_RESEARCH_SIGNAL AE_PrimaryResearchSignal(string sym,ENUM_TIMEFRAMES ltf,ENUM_TIMEFRAMES htf)
{
   int d=AE_ThreeCloseTrend(sym,ltf,1);
   if(d==AE_DIR_UP && AE_LiveRefreshWithTrend(sym,ltf,htf,AE_DIR_UP))
      return(AE_SIG_TREND_REFRESH_UP);
   if(d==AE_DIR_DOWN && AE_LiveRefreshWithTrend(sym,ltf,htf,AE_DIR_DOWN))
      return(AE_SIG_TREND_REFRESH_DOWN);

   AE_TRADE_STATE st=AE_CurrentTradeState(sym,ltf);
   if(st==AE_STATE_CONGESTION_ENTRANCE_UP) return(AE_SIG_CONGESTION_ENTRANCE_UP);
   if(st==AE_STATE_CONGESTION_ENTRANCE_DOWN) return(AE_SIG_CONGESTION_ENTRANCE_DOWN);

   string reason="";
   if(AE_DottedSetupEvidence(sym,ltf,htf,AE_DIR_UP,reason))
      return(AE_SIG_DOTTED_EVIDENCE_UP);
   if(AE_DottedSetupEvidence(sym,ltf,htf,AE_DIR_DOWN,reason))
      return(AE_SIG_DOTTED_EVIDENCE_DOWN);

   if(AE_ExhaustionEvidence(sym,ltf,htf,AE_DIR_UP))
      return(AE_SIG_EXHAUSTION_UP);
   if(AE_ExhaustionEvidence(sym,ltf,htf,AE_DIR_DOWN))
      return(AE_SIG_EXHAUSTION_DOWN);

   if(AE_IsStrongBlockEvidence(sym,ltf,htf))
      return(AE_SIG_BLOCK_STRONG);

   return(AE_SIG_NONE);
}

#endif
