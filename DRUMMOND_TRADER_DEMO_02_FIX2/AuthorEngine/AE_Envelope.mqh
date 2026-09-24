#ifndef __AE_ENVELOPE_MQH__
#define __AE_ENVELOPE_MQH__

#include <AuthorEngine\AE_State.mqh>

// Recovered envelope representation built from recent 1-1 belt geometry.
// Until a primary-source numeric ET/EB formula is independently recovered,
// this module is observation-only and MUST NOT be used as a trading gate.

bool AE_Envelope(string sym,ENUM_TIMEFRAMES tf,double &eb,double &et,string &compliance)
{
   eb=0.0;et=0.0;compliance="RECOVERED_PROXY";
   double sumLow=0.0,sumHigh=0.0;int n=0;

   for(int k=0;k<3;k++)
   {
      // Build shifted 1-1 projections explicitly from bar k+1 and its 1-1 dot.
      double dot=AE_OneOneDot(sym,tf,k);
      double loBar=AE_Low(sym,tf,k+1),hiBar=AE_High(sym,tf,k+1);
      if(dot<=0.0 || loBar<=0.0 || hiBar<=0.0) continue;
      double a=AE_ProjectBarToHalfDot(loBar,dot);
      double b=AE_ProjectBarToHalfDot(hiBar,dot);
      sumLow+=MathMin(a,b);
      sumHigh+=MathMax(a,b);
      n++;
   }
   if(n<3) return(false);
   eb=AE_Normalize(sym,sumLow/n);
   et=AE_Normalize(sym,sumHigh/n);
   return(eb>0.0 && et>0.0 && et>=eb);
}

int AE_EnvelopePosition(string sym,ENUM_TIMEFRAMES tf,double price=0.0)
{
   if(price<=0.0) price=AE_CurrentPrice(sym);
   double eb,et;string cp;
   if(!AE_Envelope(sym,tf,eb,et,cp)) return(0);
   double pl=AE_StaticPLDot(sym,tf,0);
   if(price>et) return(3);             // ABOVE_ET
   if(price>=pl && price<=et) return(2); // PL_TO_ET
   if(price>=eb && price<pl) return(1);  // EB_TO_PL
   return(-1);                         // BELOW_EB
}

string AE_EnvelopePositionText(int p)
{
   if(p==3) return("ABOVE_ET");
   if(p==2) return("PL_TO_ET");
   if(p==1) return("EB_TO_PL");
   if(p==-1) return("BELOW_EB");
   return("UNKNOWN");
}

#endif
