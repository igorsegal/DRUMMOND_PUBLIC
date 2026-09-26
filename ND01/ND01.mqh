#ifndef __ND01_CURRENCY_STRENGTH_CORE_MQH__
#define __ND01_CURRENCY_STRENGTH_CORE_MQH__

// NEWS DISLOCATION TRADER 01
// Frozen live implementation of NEWS03/NEWS05 cross-market geometry.
// M5, 30-minute move, prior 24h (288 M5 returns) volatility,
// target pair excluded by construction via six third currencies.

#define ND01_PAIR_COUNT 28
#define ND01_CUR_COUNT   8
#define ND01_VOL_BARS    288

string ND01_Currencies[ND01_CUR_COUNT] =
{
   "AUD","CAD","CHF","EUR","GBP","JPY","NZD","USD"
};

string ND01_CanonicalPairs[ND01_PAIR_COUNT] =
{
   "AUDCAD","AUDCHF","AUDJPY","AUDNZD","AUDUSD",
   "CADCHF","CADJPY","CHFJPY",
   "EURAUD","EURCAD","EURCHF","EURGBP","EURJPY","EURNZD","EURUSD",
   "GBPAUD","GBPCAD","GBPCHF","GBPJPY","GBPNZD","GBPUSD",
   "NZDCAD","NZDCHF","NZDJPY","NZDUSD",
   "USDCAD","USDCHF","USDJPY"
};

string ND01_BrokerPairs[ND01_PAIR_COUNT];

int ND01_FindCanonicalPairIndex(const string canonical)
{
   for(int i=0;i<ND01_PAIR_COUNT;i++)
      if(ND01_CanonicalPairs[i]==canonical)
         return i;
   return -1;
}

bool ND01_IsCurrency(const string c)
{
   for(int i=0;i<ND01_CUR_COUNT;i++)
      if(ND01_Currencies[i]==c)
         return true;
   return false;
}

string ND01_FindBrokerSymbol(const string canonical)
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

int ND01_InitBrokerSymbols()
{
   int found=0;
   for(int i=0;i<ND01_PAIR_COUNT;i++)
   {
      ND01_BrokerPairs[i]=ND01_FindBrokerSymbol(ND01_CanonicalPairs[i]);
      if(ND01_BrokerPairs[i]!="")
      {
         SymbolSelect(ND01_BrokerPairs[i],true);
         found++;
      }
   }
   return found;
}

datetime ND01_AlignUpM5(datetime t)
{
   long x=(long)t;
   long r=x%300;
   if(r==0) return t;
   return (datetime)(x+(300-r));
}

int ND01_CurrentServerUtcOffset()
{
   // For live processing we only translate a current/recent UTC event.
   return (int)(TimeCurrent()-TimeGMT());
}

bool ND01_PairZ30(const int pairIndex,
                  const datetime alignedEventServerTime,
                  double &z30)
{
   z30=0.0;
   if(pairIndex<0 || pairIndex>=ND01_PAIR_COUNT)
      return false;

   string sym=ND01_BrokerPairs[pairIndex];
   if(sym=="")
      return false;

   if(iBars(sym,PERIOD_M5)<ND01_VOL_BARS+20)
      return false;

   int s0=iBarShift(sym,PERIOD_M5,alignedEventServerTime,true);
   int s30=iBarShift(sym,PERIOD_M5,alignedEventServerTime+1800,true);
   if(s0<0 || s30<0)
      return false;
   if(s0+ND01_VOL_BARS+1>=iBars(sym,PERIOD_M5))
      return false;

   double o0=iOpen(sym,PERIOD_M5,s0);
   double o30=iOpen(sym,PERIOD_M5,s30);
   if(o0<=0.0 || o30<=0.0)
      return false;

   double sum=0.0, sum2=0.0;
   int n=0;

   // Strictly prior volatility: do NOT include event-bar return.
   // Newer/older open ratio for 288 completed M5 returns.
   for(int k=1;k<=ND01_VOL_BARS;k++)
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

bool ND01_BuildZVector(const datetime eventUtc,
                       double &z[])
{
   if(ArraySize(z)<ND01_PAIR_COUNT)
      ArrayResize(z,ND01_PAIR_COUNT);

   int offset=ND01_CurrentServerUtcOffset();
   datetime eventServer=eventUtc+offset;
   datetime aligned=ND01_AlignUpM5(eventServer);

   for(int i=0;i<ND01_PAIR_COUNT;i++)
   {
      if(ND01_BrokerPairs[i]=="")
         return false;

      if(!ND01_PairZ30(i,aligned,z[i]))
         return false;
   }
   return true;
}

bool ND01_GetOrientedZ(const string a,
                       const string b,
                       double &z[],
                       double &out)
{
   string direct=a+b;
   int i=ND01_FindCanonicalPairIndex(direct);
   if(i>=0)
   {
      out=z[i];
      return true;
   }

   string inverse=b+a;
   i=ND01_FindCanonicalPairIndex(inverse);
   if(i>=0)
   {
      out=-z[i];
      return true;
   }

   out=0.0;
   return false;
}

bool ND01_TargetDislocation(const int targetIndex,
                            double &z[],
                            double &targetZ,
                            double &externalGap,
                            double &dislocation)
{
   targetZ=0.0;
   externalGap=0.0;
   dislocation=0.0;

   if(targetIndex<0 || targetIndex>=ND01_PAIR_COUNT)
      return false;

   string target=ND01_CanonicalPairs[targetIndex];
   string base=StringSubstr(target,0,3);
   string quote=StringSubstr(target,3,3);

   double sumBase=0.0, sumQuote=0.0;
   int n=0;

   for(int c=0;c<ND01_CUR_COUNT;c++)
   {
      string third=ND01_Currencies[c];
      if(third==base || third==quote)
         continue;

      double bz=0.0, qz=0.0;
      if(!ND01_GetOrientedZ(base,third,z,bz))
         return false;
      if(!ND01_GetOrientedZ(quote,third,z,qz))
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

#endif
