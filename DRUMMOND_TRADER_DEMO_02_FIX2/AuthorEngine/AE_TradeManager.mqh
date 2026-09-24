#ifndef __AE_TRADE_MANAGER_MQH__
#define __AE_TRADE_MANAGER_MQH__

#include <AuthorEngine\AE_Signals.mqh>

// Author Engine 16 is research/shadow only.
// This module exists so the architecture is complete, but every execution
// entry point is fail-closed until a later validated execution block.

bool AE_TradingEnabled(){ return(false); }

bool AE_RequestOpen(string sym,int direction,double lots,double sl,double tp,string &reason)
{
   reason="AUTHOR_ENGINE_16_SHADOW_ONLY";
   return(false);
}

bool AE_RequestPyramid(string sym,int direction,string &reason)
{
   reason="AUTHOR_ENGINE_16_SHADOW_ONLY";
   return(false);
}

bool AE_RequestExit(string sym,string &reason)
{
   reason="AUTHOR_ENGINE_16_SHADOW_ONLY";
   return(false);
}

#endif
