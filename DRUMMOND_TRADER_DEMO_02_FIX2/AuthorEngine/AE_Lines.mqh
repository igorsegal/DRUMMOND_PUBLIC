#ifndef __AE_LINES_MQH__
#define __AE_LINES_MQH__

#include <AuthorEngine\AE_Dots.mqh>

enum AE_LINE_ID
{
   AE_L51_UP=0, AE_L51_DOWN,
   AE_L52_UP, AE_L52_DOWN,
   AE_L53_UP, AE_L53_DOWN,
   AE_L59_UP, AE_L59_DOWN,
   AE_L11_FROM_LOW, AE_L11_FROM_HIGH,
   AE_L61_UP, AE_L65_DOWN,
   AE_L61_DOWN, AE_L65_UP,
   AE_L67_UP, AE_L67_DOWN,
   AE_L66_UP, AE_L66_DOWN
};

bool AE_GetLine(string sym,ENUM_TIMEFRAMES tf,AE_LINE_ID id,
                double &value,int &direction,string &name,string &compliance)
{
   value=0.0; direction=AE_DIR_NONE; name=""; compliance="RECOVERED";
   if(!AE_HasBars(sym,tf,8)) return(false);

   double h1=AE_High(sym,tf,1),h2=AE_High(sym,tf,2);
   double l1=AE_Low(sym,tf,1), l2=AE_Low(sym,tf,2);
   double c1=AE_Close(sym,tf,1);
   double pl0=AE_StaticPLDot(sym,tf,0),pl1=AE_StaticPLDot(sym,tf,1);
   double dot=AE_OneOneDot(sym,tf,0),x=0.0;

   switch(id)
   {
      case AE_L51_UP:
         if(!(h1<h2)) return(false);
         x=AE_Project12To0(h1,h2);
         if(!(x<c1)) return(false);
         direction=AE_DIR_UP; name="5/1_UP"; compliance="EXACT_RECOVERED"; break;

      case AE_L51_DOWN:
         if(!(l1>l2)) return(false);
         x=AE_Project12To0(l1,l2);
         if(!(x>c1)) return(false);
         direction=AE_DIR_DOWN; name="5/1_DOWN"; compliance="EXACT_RECOVERED"; break;

      case AE_L52_UP:
         if(!(l1<l2)) return(false);
         x=AE_Project12To0(l1,l2);
         direction=AE_DIR_UP; name="5/2_UP"; compliance="EXACT_RECOVERED"; break;

      case AE_L52_DOWN:
         if(!(h1>h2)) return(false);
         x=AE_Project12To0(h1,h2);
         direction=AE_DIR_DOWN; name="5/2_DOWN"; compliance="EXACT_RECOVERED"; break;

      case AE_L53_UP:
         if(!(l1>l2)) return(false);
         x=AE_Project12To0(l1,l2);
         if(!(x<c1)) return(false);
         direction=AE_DIR_UP; name="5/3_UP"; compliance="EXACT_RECOVERED"; break;

      case AE_L53_DOWN:
         if(!(h1<h2)) return(false);
         x=AE_Project12To0(h1,h2);
         if(!(x>c1)) return(false);
         direction=AE_DIR_DOWN; name="5/3_DOWN"; compliance="EXACT_RECOVERED"; break;

      case AE_L59_UP:
         x=AE_Project12To0(l1,h2);
         direction=AE_DIR_UP; name="5/9_UP"; compliance="EXACT_RECOVERED"; break;

      case AE_L59_DOWN:
         x=AE_Project12To0(h1,l2);
         direction=AE_DIR_DOWN; name="5/9_DOWN"; compliance="EXACT_RECOVERED"; break;

      // Raw 1-1 projections. We intentionally avoid the historically ambiguous
      // High/Low naming and preserve endpoint semantics explicitly.
      case AE_L11_FROM_LOW:
         if(dot<=0.0) return(false);
         x=AE_ProjectBarToHalfDot(l1,dot);
         direction=AE_DIR_UP; name="1-1_FROM_LOW"; compliance="RECOVERED_HALF_BAR"; break;

      case AE_L11_FROM_HIGH:
         if(dot<=0.0) return(false);
         x=AE_ProjectBarToHalfDot(h1,dot);
         direction=AE_DIR_DOWN; name="1-1_FROM_HIGH"; compliance="RECOVERED_HALF_BAR"; break;

      // 6/1 and 6/5 share one geometry; identity is determined by X vs C[1].
      case AE_L61_UP:
      case AE_L65_DOWN:
         if(pl0<=0.0) return(false);
         x=AE_ProjectBarToHalfDot(h1,pl0);
         if(x<c1)
         {
            if(id!=AE_L61_UP) return(false);
            direction=AE_DIR_UP; name="6/1_UP";
         }
         else
         {
            if(id!=AE_L65_DOWN) return(false);
            direction=AE_DIR_DOWN; name="6/5_DOWN";
         }
         compliance="RECOVERED_HALF_BAR"; break;

      case AE_L61_DOWN:
      case AE_L65_UP:
         if(pl0<=0.0) return(false);
         x=AE_ProjectBarToHalfDot(l1,pl0);
         if(x>c1)
         {
            if(id!=AE_L61_DOWN) return(false);
            direction=AE_DIR_DOWN; name="6/1_DOWN";
         }
         else
         {
            if(id!=AE_L65_UP) return(false);
            direction=AE_DIR_UP; name="6/5_UP";
         }
         compliance="RECOVERED_HALF_BAR"; break;

      case AE_L67_UP:
         if(!(pl0>0.0 && pl0<l1)) return(false);
         x=AE_ProjectBarToHalfDot(l1,pl0);
         direction=AE_DIR_UP; name="6/7_UP"; compliance="RECOVERED_HALF_BAR"; break;

      case AE_L67_DOWN:
         if(!(pl0>h1)) return(false);
         x=AE_ProjectBarToHalfDot(h1,pl0);
         direction=AE_DIR_DOWN; name="6/7_DOWN"; compliance="RECOVERED_HALF_BAR"; break;

      // PLdot[1] is between historical bars; extrapolation through bar-1 H/L.
      case AE_L66_UP:
         if(!(pl1>0.0 && AE_Inside(pl1,l1,h1))) return(false);
         x=3.0*l1-2.0*pl1;
         direction=AE_DIR_UP; name="6/6_UP"; compliance="RECOVERED_HALF_BAR"; break;

      case AE_L66_DOWN:
         if(!(pl1>0.0 && AE_Inside(pl1,l1,h1))) return(false);
         x=3.0*h1-2.0*pl1;
         direction=AE_DIR_DOWN; name="6/6_DOWN"; compliance="RECOVERED_HALF_BAR"; break;

      default:
         return(false);
   }

   if(x<=0.0 || !MathIsValidNumber(x)) return(false);
   value=AE_Normalize(sym,x);
   return(true);
}

int AE_CountValidLines(string sym,ENUM_TIMEFRAMES tf,int direction)
{
   int n=0;
   for(int i=0;i<=AE_L66_DOWN;i++)
   {
      double v;int d;string nm,cp;
      if(AE_GetLine(sym,tf,(AE_LINE_ID)i,v,d,nm,cp) && d==direction) n++;
   }
   return(n);
}

bool AE_LineZone(string sym,ENUM_TIMEFRAMES tf,int direction,
                 double &low,double &high,int &count)
{
   low=0.0;high=0.0;count=0;
   for(int i=0;i<=AE_L66_DOWN;i++)
   {
      double v;int d;string nm,cp;
      if(!AE_GetLine(sym,tf,(AE_LINE_ID)i,v,d,nm,cp) || d!=direction) continue;
      if(count==0){low=v;high=v;}
      else{low=MathMin(low,v);high=MathMax(high,v);}
      count++;
   }
   return(count>0);
}

bool AE_OneOneBelt(string sym,ENUM_TIMEFRAMES tf,double &low,double &high)
{
   double a,b;int da,db;string na,nb,ca,cb;
   bool va=AE_GetLine(sym,tf,AE_L11_FROM_LOW,a,da,na,ca);
   bool vb=AE_GetLine(sym,tf,AE_L11_FROM_HIGH,b,db,nb,cb);
   if(!va || !vb){low=0.0;high=0.0;return(false);}
   low=MathMin(a,b); high=MathMax(a,b);
   return(true);
}

#endif
