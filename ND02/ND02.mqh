#ifndef __ND02_CORE_MQH__
#define __ND02_CORE_MQH__

// NEWS DISLOCATION TRADER 01
// Frozen live implementation of NEWS03/NEWS05 cross-market geometry.
// M5, 30-minute move, prior 24h (288 M5 returns) volatility,
// target pair excluded by construction via six third currencies.

#define ND02_PAIR_COUNT 28
#define ND02_CUR_COUNT   8
#define ND02_VOL_BARS    288

string ND02_Currencies[ND02_CUR_COUNT] =
{
   "AUD","CAD","CHF","EUR","GBP","JPY","NZD","USD"
};

string ND02_CanonicalPairs[ND02_PAIR_COUNT] =
{
   "AUDCAD","AUDCHF","AUDJPY","AUDNZD","AUDUSD",
   "CADCHF","CADJPY","CHFJPY",
   "EURAUD","EURCAD","EURCHF","EURGBP","EURJPY","EURNZD","EURUSD",
   "GBPAUD","GBPCAD","GBPCHF","GBPJPY","GBPNZD","GBPUSD",
   "NZDCAD","NZDCHF","NZDJPY","NZDUSD",
   "USDCAD","USDCHF","USDJPY"
};

string ND02_BrokerPairs[ND02_PAIR_COUNT];

string ND02_LastBasketFailSymbol="";
string ND02_LastBasketFailReason="";
datetime ND02_LastBasketFailRequested=0;
datetime ND02_LastBasketFailActual=0;

int ND02_FindCanonicalPairIndex(const string canonical)
{
   for(int i=0;i<ND02_PAIR_COUNT;i++)
      if(ND02_CanonicalPairs[i]==canonical)
         return i;
   return -1;
}

bool ND02_IsCurrency(const string c)
{
   for(int i=0;i<ND02_CUR_COUNT;i++)
      if(ND02_Currencies[i]==c)
         return true;
   return false;
}

string ND02_FindBrokerSymbol(const string canonical)
{
   // Prefer exact symbol first.
   int n=SymbolsTotal(false);
   for(int i=0;i<n;i++)
   {
      string s=SymbolName(i,false);
      if(s==canonical)
         return s;
   }

   // Then common broker suffixes: EURUSD.s, EURUSDm, EURUSD.pro ...
   for(int j=0;j<n;j++)
   {
      string s2=SymbolName(j,false);
      if(StringFind(s2,canonical,0)==0)
         return s2;
   }

   // Last fallback: prefix + canonical (rare broker naming).
   for(int k=0;k<n;k++)
   {
      string s3=SymbolName(k,false);
      if(StringFind(s3,canonical,0)>=0)
         return s3;
   }
   return "";
}

int ND02_InitBrokerSymbols()
{
   int found=0;
   for(int i=0;i<ND02_PAIR_COUNT;i++)
   {
      ND02_BrokerPairs[i]=ND02_FindBrokerSymbol(ND02_CanonicalPairs[i]);
      if(ND02_BrokerPairs[i]!="")
      {
         SymbolSelect(ND02_BrokerPairs[i],true);
         found++;
      }
   }
   return found;
}

datetime ND02_AlignUpM5(datetime t)
{
   long x=(long)t;
   long r=x%300;
   if(r==0) return t;
   return (datetime)(x+(300-r));
}

bool ND02_PairZ30(const int pairIndex,
                  const datetime alignedEventServerTime,
                  double &z30)
{
   z30=0.0;
   ND02_LastBasketFailSymbol="";
   ND02_LastBasketFailReason="";
   ND02_LastBasketFailRequested=0;
   ND02_LastBasketFailActual=0;

   if(pairIndex<0 || pairIndex>=ND02_PAIR_COUNT)
   {
      ND02_LastBasketFailReason="BAD_PAIR_INDEX";
      return false;
   }

   string sym=ND02_BrokerPairs[pairIndex];
   if(sym=="")
   {
      ND02_LastBasketFailReason="NO_BROKER_SYMBOL";
      return false;
   }

   int bars=iBars(sym,PERIOD_M5);
   if(bars<ND02_VOL_BARS+20)
   {
      ND02_LastBasketFailSymbol=sym;
      ND02_LastBasketFailReason="SHORT_M5_HISTORY";
      return false;
   }

   // MT4 histories can omit an individual M5 timestamp when there was no tick.
   // Use nearest bar but allow at most one M5 interval of displacement.
   int s0=iBarShift(sym,PERIOD_M5,alignedEventServerTime,false);
   int s30=iBarShift(sym,PERIOD_M5,alignedEventServerTime+1800,false);
   if(s0<0 || s30<0)
   {
      ND02_LastBasketFailSymbol=sym;
      ND02_LastBasketFailReason="IBARSHIFT_FAIL";
      return false;
   }

   datetime t0=iTime(sym,PERIOD_M5,s0);
   datetime t30=iTime(sym,PERIOD_M5,s30);
   if(MathAbs((double)(t0-alignedEventServerTime))>300.0)
   {
      ND02_LastBasketFailSymbol=sym;
      ND02_LastBasketFailReason="EVENT_BAR_GAP_GT_M5";
      ND02_LastBasketFailRequested=alignedEventServerTime;
      ND02_LastBasketFailActual=t0;
      return false;
   }
   if(MathAbs((double)(t30-(alignedEventServerTime+1800)))>300.0)
   {
      ND02_LastBasketFailSymbol=sym;
      ND02_LastBasketFailReason="DECISION_BAR_GAP_GT_M5";
      ND02_LastBasketFailRequested=alignedEventServerTime+1800;
      ND02_LastBasketFailActual=t30;
      return false;
   }

   if(s0+ND02_VOL_BARS+1>=bars)
   {
      ND02_LastBasketFailSymbol=sym;
      ND02_LastBasketFailReason="PRIOR_24H_NOT_AVAILABLE";
      return false;
   }

   double o0=iOpen(sym,PERIOD_M5,s0);
   double o30=iOpen(sym,PERIOD_M5,s30);
   if(o0<=0.0 || o30<=0.0)
   {
      ND02_LastBasketFailSymbol=sym;
      ND02_LastBasketFailReason="BAD_EVENT_OPEN";
      return false;
   }

   double sum=0.0, sum2=0.0;
   int n=0;

   for(int k=1;k<=ND02_VOL_BARS;k++)
   {
      double onewer=iOpen(sym,PERIOD_M5,s0+k);
      double oolder=iOpen(sym,PERIOD_M5,s0+k+1);
      if(onewer<=0.0 || oolder<=0.0)
      {
         ND02_LastBasketFailSymbol=sym;
         ND02_LastBasketFailReason="BAD_PRIOR_OPEN";
         return false;
      }

      double r=MathLog(onewer/oolder);
      sum+=r;
      sum2+=r*r;
      n++;
   }

   if(n<2)
   {
      ND02_LastBasketFailSymbol=sym;
      ND02_LastBasketFailReason="VOL_N_LT_2";
      return false;
   }

   double variance=(sum2-sum*sum/n)/(n-1);
   if(variance<=0.0)
   {
      ND02_LastBasketFailSymbol=sym;
      ND02_LastBasketFailReason="VOL_ZERO";
      return false;
   }

   double sd=MathSqrt(variance);
   double r30=MathLog(o30/o0);
   z30=r30/(sd*MathSqrt(6.0));

   if(!MathIsValidNumber(z30))
   {
      ND02_LastBasketFailSymbol=sym;
      ND02_LastBasketFailReason="Z_INVALID";
      return false;
   }

   return true;
}

bool ND02_BuildZVectorServer(const datetime eventServer,
                             double &z[])
{
   if(ArraySize(z)<ND02_PAIR_COUNT)
      ArrayResize(z,ND02_PAIR_COUNT);

   datetime aligned=ND02_AlignUpM5(eventServer);

   for(int i=0;i<ND02_PAIR_COUNT;i++)
   {
      if(ND02_BrokerPairs[i]=="")
         return false;

      if(!ND02_PairZ30(i,aligned,z[i]))
         return false;
   }
   return true;
}

bool ND02_GetOrientedZ(const string a,
                       const string b,
                       double &z[],
                       double &out)
{
   string direct=a+b;
   int i=ND02_FindCanonicalPairIndex(direct);
   if(i>=0)
   {
      out=z[i];
      return true;
   }

   string inverse=b+a;
   i=ND02_FindCanonicalPairIndex(inverse);
   if(i>=0)
   {
      out=-z[i];
      return true;
   }

   out=0.0;
   return false;
}

bool ND02_TargetDislocation(const int targetIndex,
                            double &z[],
                            double &targetZ,
                            double &externalGap,
                            double &dislocation)
{
   targetZ=0.0;
   externalGap=0.0;
   dislocation=0.0;

   if(targetIndex<0 || targetIndex>=ND02_PAIR_COUNT)
      return false;

   string target=ND02_CanonicalPairs[targetIndex];
   string base=StringSubstr(target,0,3);
   string quote=StringSubstr(target,3,3);

   double sumBase=0.0, sumQuote=0.0;
   int n=0;

   for(int c=0;c<ND02_CUR_COUNT;c++)
   {
      string third=ND02_Currencies[c];
      if(third==base || third==quote)
         continue;

      double bz=0.0, qz=0.0;
      if(!ND02_GetOrientedZ(base,third,z,bz))
         return false;
      if(!ND02_GetOrientedZ(quote,third,z,qz))
         return false;

      sumBase+=bz;
      sumQuote+=qz;
      n++;
   }

   if(n!=6)
      return false;

   targetZ=z[targetIndex];
   externalGap=(sumBase/n)-(sumQuote/n);
   dislocation=externalGap-targetZ;

   return (MathIsValidNumber(targetZ) &&
           MathIsValidNumber(externalGap) &&
           MathIsValidNumber(dislocation));
}


bool ND02_SymbolZ30(const string sym,
                    const datetime eventServer,
                    double &z30)
{
   z30=0.0;
   datetime aligned=ND02_AlignUpM5(eventServer);

   if(iBars(sym,PERIOD_M5)<ND02_VOL_BARS+20)
      return false;

   int s0=iBarShift(sym,PERIOD_M5,aligned,true);
   int s30=iBarShift(sym,PERIOD_M5,aligned+1800,true);
   if(s0<0 || s30<0)
      return false;
   if(s0+ND02_VOL_BARS+1>=iBars(sym,PERIOD_M5))
      return false;

   double o0=iOpen(sym,PERIOD_M5,s0);
   double o30=iOpen(sym,PERIOD_M5,s30);
   if(o0<=0.0 || o30<=0.0)
      return false;

   double sum=0.0, sum2=0.0;
   int n=0;
   for(int k=1;k<=ND02_VOL_BARS;k++)
   {
      double onewer=iOpen(sym,PERIOD_M5,s0+k);
      double oolder=iOpen(sym,PERIOD_M5,s0+k+1);
      if(onewer<=0.0 || oolder<=0.0)
         return false;

      double r=MathLog(onewer/oolder);
      sum+=r;
      sum2+=r*r;
      n++;
   }

   if(n<2)
      return false;

   double variance=(sum2-sum*sum/n)/(n-1);
   if(variance<=0.0)
      return false;

   double sd=MathSqrt(variance);
   double r30=MathLog(o30/o0);
   z30=r30/(sd*MathSqrt(6.0));

   return MathIsValidNumber(z30);
}

bool ND02_ExternalCurrencyStrength(const string currency,
                                   double &z[],
                                   double &strength)
{
   strength=0.0;
   if(!ND02_IsCurrency(currency))
      return false;

   double sum=0.0;
   int n=0;

   for(int i=0;i<ND02_CUR_COUNT;i++)
   {
      string other=ND02_Currencies[i];
      if(other==currency)
         continue;

      double v=0.0;
      if(!ND02_GetOrientedZ(currency,other,z,v))
         return false;

      sum+=v;
      n++;
   }

   if(n!=7)
      return false;

   strength=sum/n;
   return MathIsValidNumber(strength);
}

#endif
