#ifndef __AE_ENERGY_MQH__
#define __AE_ENERGY_MQH__

#include <AuthorEngine\AE_Envelope.mqh>

struct AE_EnergyZone
{
   double low;
   double high;
   bool valid;
   bool furtherOut;
   string source;
   string compliance;
};

void AE_ResetZone(AE_EnergyZone &z)
{
   z.low=0.0;z.high=0.0;z.valid=false;z.furtherOut=false;z.source="";z.compliance="RECOVERED";
}

void AE_AddLevelToZone(double v,double &lo,double &hi,int &n)
{
   if(v<=0.0) return;
   if(n==0){lo=v;hi=v;} else {lo=MathMin(lo,v);hi=MathMax(hi,v);}
   n++;
}

void AE_LineFamilyZone(string sym,ENUM_TIMEFRAMES tf,int direction,
                       bool include11,bool include51,bool include52,bool include59,
                       double &lo,double &hi,int &n)
{
   lo=0.0;hi=0.0;n=0;
   AE_LINE_ID ids[8];
   ids[0]=AE_L11_FROM_LOW; ids[1]=AE_L11_FROM_HIGH;
   ids[2]=AE_L51_UP;ids[3]=AE_L51_DOWN;
   ids[4]=AE_L52_UP;ids[5]=AE_L52_DOWN;
   ids[6]=AE_L59_UP;ids[7]=AE_L59_DOWN;

   for(int i=0;i<8;i++)
   {
      bool family=(i<2?include11:(i<4?include51:(i<6?include52:include59)));
      if(!family) continue;
      double v;int d;string nm,cp;
      if(AE_GetLine(sym,tf,ids[i],v,d,nm,cp) && d==direction)
         AE_AddLevelToZone(v,lo,hi,n);
   }
}

bool AE_GetEnergyZones(string sym,ENUM_TIMEFRAMES tf,
                       AE_EnergyZone &nearSupport,AE_EnergyZone &nearResistance,
                       AE_EnergyZone &farSupport,AE_EnergyZone &farResistance)
{
   AE_ResetZone(nearSupport);AE_ResetZone(nearResistance);
   AE_ResetZone(farSupport);AE_ResetZone(farResistance);

   double eb,et;string cp;
   if(!AE_Envelope(sym,tf,eb,et,cp)) return(false);
   double pl=AE_StaticPLDot(sym,tf,0);
   double c1=AE_Close(sym,tf,1);
   if(pl<=0.0 || c1<=0.0) return(false);

   int pos=AE_EnvelopePosition(sym,tf,c1);
   double lo,hi;int n;

   // Lesson-16 recovered placement map.
   if(pos==3) // close above ET
   {
      nearSupport.low=MathMin(et,pl); nearSupport.high=MathMax(et,pl);
      nearSupport.valid=true;nearSupport.source="ET_TO_PLDOT";

      AE_LineFamilyZone(sym,tf,AE_DIR_DOWN,true,false,true,true,lo,hi,n);
      if(n>0){nearResistance.low=lo;nearResistance.high=hi;nearResistance.valid=true;nearResistance.source="1-1_5/2_5/9";}
   }
   else if(pos==2) // ET to PL
   {
      nearSupport.low=MathMin(pl,eb);nearSupport.high=MathMax(pl,eb);
      nearSupport.valid=true;nearSupport.source="PLDOT_TO_EB";
      nearResistance.low=et;nearResistance.high=et;nearResistance.valid=true;nearResistance.source="ET";
   }
   else if(pos==1) // PL to EB
   {
      nearSupport.low=eb;nearSupport.high=eb;nearSupport.valid=true;nearSupport.source="EB";
      nearResistance.low=MathMin(pl,et);nearResistance.high=MathMax(pl,et);
      nearResistance.valid=true;nearResistance.source="PLDOT_TO_ET";
   }
   else if(pos==-1) // below EB
   {
      AE_LineFamilyZone(sym,tf,AE_DIR_UP,false,false,true,true,lo,hi,n);
      if(n>0){farSupport.low=lo;farSupport.high=hi;farSupport.valid=true;farSupport.furtherOut=true;farSupport.source="5/9_5/2";}
      nearResistance.low=MathMin(eb,pl);nearResistance.high=MathMax(eb,pl);
      nearResistance.valid=true;nearResistance.source="EB_TO_PLDOT";
   }

   nearSupport.compliance="RECOVERED_LESSON16";
   nearResistance.compliance="RECOVERED_LESSON16";
   farSupport.compliance="RECOVERED_LESSON16";
   farResistance.compliance="RECOVERED_LESSON16";
   return(true);
}


bool AE_GetFurtherOutLineZone(string sym,ENUM_TIMEFRAMES tf,int direction,double reference,
                              double &low,double &high,int &count)
{
   low=0.0;high=0.0;count=0;
   AE_LINE_ID ids[4];
   ids[0]=AE_L52_UP; ids[1]=AE_L59_UP;
   ids[2]=AE_L52_DOWN; ids[3]=AE_L59_DOWN;
   for(int i=0;i<4;i++)
   {
      double v;int d;string nm,cp;
      if(!AE_GetLine(sym,tf,ids[i],v,d,nm,cp) || d!=direction) continue;
      if(direction==AE_DIR_UP && v>=reference) continue;
      if(direction==AE_DIR_DOWN && v<=reference) continue;
      AE_AddLevelToZone(v,low,high,count);
   }
   return(count>0);
}

bool AE_GetNearbyLineZone(string sym,ENUM_TIMEFRAMES tf,int direction,double reference,
                          double &low,double &high,int &count)
{
   low=0.0;high=0.0;count=0;
   AE_LINE_ID ids[6];
   ids[0]=AE_L11_FROM_LOW; ids[1]=AE_L52_UP; ids[2]=AE_L59_UP;
   ids[3]=AE_L11_FROM_HIGH;ids[4]=AE_L52_DOWN;ids[5]=AE_L59_DOWN;
   for(int i=0;i<6;i++)
   {
      double v;int d;string nm,cp;
      if(!AE_GetLine(sym,tf,ids[i],v,d,nm,cp) || d!=direction) continue;
      if(direction==AE_DIR_UP && v>=reference) continue;
      if(direction==AE_DIR_DOWN && v<=reference) continue;
      AE_AddLevelToZone(v,low,high,count);
   }
   return(count>0);
}

// Lesson-16 / Lesson-20 contract:
// Further Out is NOT "the farthest valid Drummond line".
// Its recovered line components are 5/2 and 5/9. 1-1 and 6/x retain
// their own author roles and cannot silently become Further Out.
double AE_FurtherOutStop(string sym,ENUM_TIMEFRAMES tf,int positionDirection,double entry)
{
   double lo,hi;int n;
   double p=AE_Point(sym);
   if(positionDirection==AE_DIR_UP)
   {
      if(!AE_GetFurtherOutLineZone(sym,tf,AE_DIR_UP,entry,lo,hi,n)) return(0.0);
      return(AE_Normalize(sym,lo-p));
   }
   if(positionDirection==AE_DIR_DOWN)
   {
      if(!AE_GetFurtherOutLineZone(sym,tf,AE_DIR_DOWN,entry,lo,hi,n)) return(0.0);
      return(AE_Normalize(sym,hi+p));
   }
   return(0.0);
}


bool AE_ZoneContains(AE_EnergyZone &z,double price)
{
   return(z.valid && price>=z.low && price<=z.high);
}

#endif
