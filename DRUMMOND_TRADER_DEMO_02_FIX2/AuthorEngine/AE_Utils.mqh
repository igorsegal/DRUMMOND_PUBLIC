#ifndef __AE_UTILS_MQH__
#define __AE_UTILS_MQH__

#define AE_DIR_NONE 0
#define AE_DIR_UP   1
#define AE_DIR_DOWN -1

double AE_Point(string sym){ return(MarketInfo(sym,MODE_POINT)); }
int AE_Digits(string sym){ return((int)MarketInfo(sym,MODE_DIGITS)); }
double AE_Normalize(string sym,double p){ return(NormalizeDouble(p,AE_Digits(sym))); }

bool AE_HasBars(string sym,ENUM_TIMEFRAMES tf,int n){ return(iBars(sym,tf)>=n); }

double AE_Open(string sym,ENUM_TIMEFRAMES tf,int s){ return(iOpen(sym,tf,s)); }
double AE_High(string sym,ENUM_TIMEFRAMES tf,int s){ return(iHigh(sym,tf,s)); }
double AE_Low(string sym,ENUM_TIMEFRAMES tf,int s){ return(iLow(sym,tf,s)); }
double AE_Close(string sym,ENUM_TIMEFRAMES tf,int s){ return(iClose(sym,tf,s)); }

double AE_Typical(string sym,ENUM_TIMEFRAMES tf,int s)
{
   double h=AE_High(sym,tf,s),l=AE_Low(sym,tf,s),c=AE_Close(sym,tf,s);
   if(h<=0.0 || l<=0.0 || c<=0.0) return(0.0);
   return((h+l+c)/3.0);
}

double AE_Mid(string sym,ENUM_TIMEFRAMES tf,int s)
{
   double h=AE_High(sym,tf,s),l=AE_Low(sym,tf,s);
   if(h<=0.0 || l<=0.0) return(0.0);
   return((h+l)/2.0);
}

double AE_CurrentPrice(string sym)
{
   double bid=MarketInfo(sym,MODE_BID);
   if(bid>0.0) return(bid);
   return(AE_Close(sym,PERIOD_CURRENT,0));
}

// Two equally spaced closed-bar points: p1@bar1, p2@bar2 -> X@bar0.
// This is the corrected author projection orientation.
double AE_Project12To0(double p1,double p2){ return(2.0*p1-p2); }

// Half-step recovered geometry: bar point at t=-1 and dot at t=-0.5,
// projected to current bar t=0. This is required for classical between-bar
// Drummond dot geometry. Value = 2*dot - barPoint.
double AE_ProjectBarToHalfDot(double barPoint,double dot){ return(2.0*dot-barPoint); }

bool AE_Inside(double x,double a,double b)
{
   double lo=MathMin(a,b),hi=MathMax(a,b);
   return(x>=lo && x<=hi);
}

int AE_Sign(double x,double eps=0.0)
{
   if(x>eps) return(AE_DIR_UP);
   if(x<-eps) return(AE_DIR_DOWN);
   return(AE_DIR_NONE);
}

string AE_DirText(int d)
{
   if(d==AE_DIR_UP) return("UP");
   if(d==AE_DIR_DOWN) return("DOWN");
   return("NONE");
}

string AE_TFText(ENUM_TIMEFRAMES tf)
{
   if(tf==PERIOD_M1) return("M1");
   if(tf==PERIOD_M5) return("M5");
   if(tf==PERIOD_M15) return("M15");
   if(tf==PERIOD_M30) return("M30");
   if(tf==PERIOD_H1) return("H1");
   if(tf==PERIOD_H4) return("H4");
   if(tf==PERIOD_D1) return("D1");
   if(tf==PERIOD_W1) return("W1");
   if(tf==PERIOD_MN1) return("MN1");
   return(IntegerToString((int)tf));
}

#endif
