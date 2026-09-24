#property strict

#include "DT02_Common.mqh"

enum D2_EXECUTOR_RUN_MODE
{
   D2_EXECUTOR_TESTER = 0,
   D2_EXECUTOR_DEMO   = 1
};

input D2_EXECUTOR_RUN_MODE InpRunMode=D2_EXECUTOR_TESTER;
input bool            InpEnableTesterTrading=true;
input bool            InpEnableDemoTrading=false;
input int             InpMagic=29092002;
input int             InpTimerSeconds=2;
input double          InpMinProjectedMarginLevelPct=5000.0;
input bool            InpOnePositionPerSymbol=false;
input int             InpSignalMaxAgeMinutes=15;
input double          InpMaxSpreadRiskPercent=10.0;
input double          InpMaxEntryDriftRiskPercent=10.0;
input double          InpRRMin=0.75;
input double          InpRRMax=1.75;
input int             InpSlippagePoints=20;
input bool            InpTrailFurtherOut=true;
input ENUM_TIMEFRAMES InpDecisionTF=PERIOD_H1;
input int             InpProtectionBufferPoints=1;
input string          InpQueueFile="DRUMMOND_DEMO02_SIGNALS.csv";
input string          InpExecutionFile="DRUMMOND_DEMO02_EXECUTION.csv";
input bool            InpClearTesterExecutionOnInit=true;
input string          InpLifecycleFile="DRUMMOND_DEMO02_LIFECYCLE.csv";
input bool            InpClearTesterLifecycleOnInit=true;

string g_processed[];
int    g_lifeTickets[];
string g_lifeSignalIds[];
int    g_lifeClosedLogged[];

int D2_OpenAppendExecution()
{
   int flags=FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE;
   if(InpRunMode==D2_EXECUTOR_DEMO) flags|=FILE_COMMON;
   int h=FileOpen(InpExecutionFile,flags,';');
   if(h==INVALID_HANDLE) return(INVALID_HANDLE);
   FileSeek(h,0,SEEK_END);
   return(h);
}

void D2_WriteExecutionHeaderIfNeeded(int h)
{
   if(h==INVALID_HANDLE) return;
   if(FileSize(h)>0) return;
   FileWrite(h,
      "SIGNAL_ID","SERVER_TIME","ACTION","REASON","SYMBOL","DECISION_TIME","SIDE",
      "LOTS","PRICE","SL","TP","RR_CURRENT","PROJECTED_MARGIN_LEVEL_PCT","TICKET","ERROR");
}

void D2_ExecutionLog(string signalId,string action,string reason,string sym,datetime decisionTime,
                     int side,double lots,double price,double sl,double tp,double rr,
                     double projectedMarginLevel,int ticket,int errorCode)
{
   int h=D2_OpenAppendExecution();
   if(h==INVALID_HANDLE)
   {
      Print("EXECUTOR: cannot open execution log, err=",GetLastError());
      return;
   }
   D2_WriteExecutionHeaderIfNeeded(h);
   int digits=(sym!=""?D2_Digits(sym):5);
   FileSeek(h,0,SEEK_END);
   FileWrite(h,
      signalId,(int)TimeCurrent(),action,reason,sym,(int)decisionTime,D2_SideText(side),
      DoubleToString(lots,4),DoubleToString(price,digits),DoubleToString(sl,digits),DoubleToString(tp,digits),
      DoubleToString(rr,6),DoubleToString(projectedMarginLevel,2),ticket,errorCode);
   FileFlush(h);
   FileClose(h);
}

int D2_OpenAppendLifecycle()
{
   int flags=FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE;
   int h=FileOpen(InpLifecycleFile,flags,';');
   if(h==INVALID_HANDLE) return(INVALID_HANDLE);
   FileSeek(h,0,SEEK_END);
   return(h);
}

void D2_WriteLifecycleHeaderIfNeeded(int h)
{
   if(h==INVALID_HANDLE || FileSize(h)>0) return;
   FileWrite(h,
      "EVENT","SERVER_TIME","SIGNAL_ID","TICKET","SYMBOL","SIDE",
      "OPEN_TIME","OPEN_PRICE","CLOSE_TIME","CLOSE_PRICE","FINAL_SL","TP",
      "LOTS","PROFIT","SWAP","COMMISSION","CLOSE_REASON");
}

void D2_LifeMapAdd(int ticket,string signalId)
{
   int n=ArraySize(g_lifeTickets);
   ArrayResize(g_lifeTickets,n+1);
   ArrayResize(g_lifeSignalIds,n+1);
   g_lifeTickets[n]=ticket;
   g_lifeSignalIds[n]=signalId;
}

string D2_LifeSignalByTicket(int ticket)
{
   for(int i=ArraySize(g_lifeTickets)-1;i>=0;i--)
      if(g_lifeTickets[i]==ticket) return(g_lifeSignalIds[i]);
   return("");
}

bool D2_LifeClosedWasLogged(int ticket)
{
   for(int i=0;i<ArraySize(g_lifeClosedLogged);i++)
      if(g_lifeClosedLogged[i]==ticket) return(true);
   return(false);
}

void D2_LifeMarkClosedLogged(int ticket)
{
   if(D2_LifeClosedWasLogged(ticket)) return;
   int n=ArraySize(g_lifeClosedLogged);
   ArrayResize(g_lifeClosedLogged,n+1);
   g_lifeClosedLogged[n]=ticket;
}

string D2_LifeCloseReason(int side,double closePrice,double sl,double tp,double point)
{
   double eps=MathMax(point*0.5,0.0000001);
   if(side==D2_SIDE_LONG)
   {
      if(tp>0.0 && closePrice>=tp-eps) return("TP");
      if(sl>0.0 && closePrice<=sl+eps) return("SL");
   }
   else if(side==D2_SIDE_SHORT)
   {
      if(tp>0.0 && closePrice<=tp+eps) return("TP");
      if(sl>0.0 && closePrice>=sl-eps) return("SL");
   }
   return("OTHER");
}

void D2_LifecycleWrite(string eventName,string signalId,int ticket,string sym,int side,
                       datetime openTime,double openPrice,datetime closeTime,double closePrice,
                       double sl,double tp,double lots,double profit,double swap,double commission,
                       string closeReason)
{
   int h=D2_OpenAppendLifecycle();
   if(h==INVALID_HANDLE)
   {
      Print("EXECUTOR EQ02: cannot open lifecycle log, err=",GetLastError());
      return;
   }
   D2_WriteLifecycleHeaderIfNeeded(h);
   int digits=(sym!=""?D2_Digits(sym):5);
   FileSeek(h,0,SEEK_END);
   FileWrite(h,eventName,(int)TimeCurrent(),signalId,ticket,sym,D2_SideText(side),
      (int)openTime,DoubleToString(openPrice,digits),(int)closeTime,DoubleToString(closePrice,digits),
      DoubleToString(sl,digits),DoubleToString(tp,digits),DoubleToString(lots,4),
      DoubleToString(profit,2),DoubleToString(swap,2),DoubleToString(commission,2),closeReason);
   FileFlush(h);
   FileClose(h);
}

void D2_LifecycleLogOpen(string signalId,int ticket)
{
   if(!OrderSelect(ticket,SELECT_BY_TICKET,MODE_TRADES)) return;
   int side=(OrderType()==OP_BUY?D2_SIDE_LONG:OrderType()==OP_SELL?D2_SIDE_SHORT:D2_SIDE_NONE);
   if(side==D2_SIDE_NONE) return;
   D2_LifecycleWrite("OPEN",signalId,ticket,OrderSymbol(),side,
      OrderOpenTime(),OrderOpenPrice(),0,0.0,OrderStopLoss(),OrderTakeProfit(),
      OrderLots(),0.0,0.0,0.0,"");
}

void D2_ScanClosedLifecycle()
{
   int total=OrdersHistoryTotal();
   for(int i=0;i<total;i++)
   {
      if(!OrderSelect(i,SELECT_BY_POS,MODE_HISTORY)) continue;
      if(OrderMagicNumber()!=InpMagic) continue;
      if(OrderType()!=OP_BUY && OrderType()!=OP_SELL) continue;
      int ticket=OrderTicket();
      if(D2_LifeClosedWasLogged(ticket)) continue;
      string signalId=D2_LifeSignalByTicket(ticket);
      if(signalId=="") continue;
      int side=(OrderType()==OP_BUY?D2_SIDE_LONG:D2_SIDE_SHORT);
      double point=D2_Point(OrderSymbol());
      string reason=D2_LifeCloseReason(side,OrderClosePrice(),OrderStopLoss(),OrderTakeProfit(),point);
      D2_LifecycleWrite("CLOSE",signalId,ticket,OrderSymbol(),side,
         OrderOpenTime(),OrderOpenPrice(),OrderCloseTime(),OrderClosePrice(),
         OrderStopLoss(),OrderTakeProfit(),OrderLots(),OrderProfit(),OrderSwap(),OrderCommission(),reason);
      D2_LifeMarkClosedLogged(ticket);
   }
}

bool D2_IsProcessed(string signalId)
{
   if(signalId=="") return(false);
   int n=ArraySize(g_processed);
   for(int i=0;i<n;i++) if(g_processed[i]==signalId) return(true);
   return(false);
}

void D2_AddProcessed(string signalId)
{
   if(signalId=="" || D2_IsProcessed(signalId)) return;
   int n=ArraySize(g_processed);
   ArrayResize(g_processed,n+1);
   g_processed[n]=signalId;
}

void D2_LoadProcessed()
{
   ArrayResize(g_processed,0);
   int flags=FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE;
   if(InpRunMode==D2_EXECUTOR_DEMO) flags|=FILE_COMMON;
   int h=FileOpen(InpExecutionFile,flags,';');
   if(h==INVALID_HANDLE) return;

   while(!FileIsEnding(h))
   {
      string id=FileReadString(h);
      if(FileIsEnding(h) && id=="") break;
      // Остальные 14 полей строки.
      for(int k=0;k<14;k++) FileReadString(h);
      if(id=="" || id=="SIGNAL_ID") continue;
      D2_AddProcessed(id);
   }
   FileClose(h);
}

int D2_ParseSide(string s)
{
   if(s=="LONG") return(D2_SIDE_LONG);
   if(s=="SHORT") return(D2_SIDE_SHORT);
   return(D2_SIDE_NONE);
}

bool D2_EnvironmentOK(string &reason)
{
   reason="";

   if(InpRunMode==D2_EXECUTOR_TESTER)
   {
      if(!IsTesting()){ reason="TESTER_MODE_OUTSIDE_STRATEGY_TESTER"; return(false); }
      if(!InpEnableTesterTrading){ reason="TESTER_TRADING_DISABLED"; return(false); }
      if(IsTradeContextBusy()){ reason="TRADE_CONTEXT_BUSY"; return(false); }
      reason="ENVIRONMENT_OK";
      return(true);
   }

   if(IsTesting()){ reason="DEMO_MODE_INSIDE_STRATEGY_TESTER"; return(false); }
   if(!IsDemo()){ reason="ACCOUNT_NOT_DEMO"; return(false); }
   if(!InpEnableDemoTrading){ reason="DEMO_TRADING_DISABLED"; return(false); }
   if(!IsConnected()){ reason="TERMINAL_NOT_CONNECTED"; return(false); }
   if(!IsTradeAllowed()){ reason="TRADE_NOT_ALLOWED"; return(false); }
   if(IsTradeContextBusy()){ reason="TRADE_CONTEXT_BUSY"; return(false); }
   reason="ENVIRONMENT_OK";
   return(true);
}

bool D2_ValidateFreshSignal(string signalId,int createdAt,string sym,datetime decisionTime,int side,
                            double entryRef,double sl,double tp,
                            double &lots,double &currentPrice,double &currentRR,double &projectedMarginLevel,
                            string &reason)
{
   lots=0.0;
   currentPrice=0.0;
   currentRR=0.0;
   projectedMarginLevel=0.0;
   reason="";

   if(signalId=="" || sym=="" || decisionTime<=0 || createdAt<=0)
   { reason="INVALID_SIGNAL_ROW"; return(false); }

   int ageSec=(int)TimeCurrent()-createdAt;
   if(ageSec<0) ageSec=0;
   if(InpSignalMaxAgeMinutes>0 && ageSec>InpSignalMaxAgeMinutes*60)
   { reason="SIGNAL_EXPIRED"; return(false); }

   string env="";
   if(!D2_EnvironmentOK(env)){ reason=env; return(false); }

   // В MT4 Strategy Tester тестируемый символ уже задаётся самим тестером.
   // SymbolSelect() там может вернуть false даже для текущего символа, поэтому
   // в TESTER не пытаемся менять Market Watch: разрешён только Symbol().
   if(InpRunMode==D2_EXECUTOR_TESTER)
   {
      if(sym!=Symbol()){ reason="TESTER_SYMBOL_MISMATCH"; return(false); }
   }
   else
   {
      if(!SymbolSelect(sym,true)){ reason="SYMBOL_SELECT_FAILED"; return(false); }
      if(MarketInfo(sym,MODE_TRADEALLOWED)<=0){ reason="SYMBOL_TRADE_NOT_ALLOWED"; return(false); }
   }

   if(side!=D2_SIDE_LONG && side!=D2_SIDE_SHORT){ reason="INVALID_SIDE"; return(false); }

   double ask=MarketInfo(sym,MODE_ASK);
   double bid=MarketInfo(sym,MODE_BID);
   double point=D2_Point(sym);
   if(ask<=0.0 || bid<=0.0 || point<=0.0){ reason="INVALID_QUOTE"; return(false); }

   lots=D2_MinimumBrokerLot(sym);
   if(lots<=0.0){ reason="INVALID_MIN_LOT"; return(false); }

   if(InpOnePositionPerSymbol && D2_OneOurPositionOnSymbol(sym,InpMagic))
   { reason="POSITION_ALREADY_OPEN_ON_SYMBOL"; return(false); }

   double originalRisk=MathAbs(entryRef-sl);
   if(originalRisk<=0.0){ reason="INVALID_ORIGINAL_RISK"; return(false); }

   double spread=ask-bid;
   double spreadRiskPct=100.0*spread/originalRisk;
   if(InpMaxSpreadRiskPercent>0.0 && spreadRiskPct>InpMaxSpreadRiskPercent)
   { reason="SPREAD_TOO_LARGE_VS_RISK"; return(false); }

   currentPrice=(side==D2_SIDE_LONG?ask:bid);
   currentPrice=D2_NormalizePrice(sym,currentPrice);

   double driftPct=100.0*MathAbs(currentPrice-entryRef)/originalRisk;
   if(InpMaxEntryDriftRiskPercent>0.0 && driftPct>InpMaxEntryDriftRiskPercent)
   { reason="ENTRY_DRIFT_TOO_LARGE"; return(false); }

   if(side==D2_SIDE_LONG)
   {
      if(!(sl<currentPrice && tp>currentPrice)){ reason="CURRENT_LONG_GEOMETRY_INVALID"; return(false); }
   }
   else
   {
      if(!(sl>currentPrice && tp<currentPrice)){ reason="CURRENT_SHORT_GEOMETRY_INVALID"; return(false); }
   }

   currentRR=D2_InitialRR(currentPrice,sl,tp);
   if(currentRR<0.0 || !MathIsValidNumber(currentRR)){ reason="CURRENT_RR_INVALID"; return(false); }
   if(currentRR<InpRRMin){ reason="CURRENT_RR_BELOW_MIN"; return(false); }
   if(InpRRMax>0.0 && currentRR>=InpRRMax){ reason="CURRENT_RR_AT_OR_ABOVE_MAX"; return(false); }

   string distReason="";
   if(!D2_CheckBrokerDistances(sym,side,currentPrice,sl,tp,distReason))
   { reason=distReason; return(false); }

   string marginReason="";
   if(!D2_ProjectedMarginLevelOK(sym,side,lots,InpMinProjectedMarginLevelPct,projectedMarginLevel,marginReason))
   { reason=marginReason; return(false); }

   reason="EXECUTION_VALIDATED";
   return(true);
}

void D2_ProcessSignal(string signalId,int createdAt,string sym,datetime decisionTime,int side,
                      double entryRef,double sl,double tp,double rrFromWatcher,string signalName)
{
   if(D2_IsProcessed(signalId)) return;

   double lots=0.0,currentPrice=0.0,currentRR=0.0,projectedLevel=0.0;
   string reason="";
   bool valid=D2_ValidateFreshSignal(signalId,createdAt,sym,decisionTime,side,entryRef,sl,tp,
                                     lots,currentPrice,currentRR,projectedLevel,reason);
   if(!valid)
   {
      D2_ExecutionLog(signalId,"BLOCKED",reason,sym,decisionTime,side,lots,currentPrice,sl,tp,currentRR,projectedLevel,-1,0);
      D2_AddProcessed(signalId);
      Print("EXECUTOR BLOCKED | ",signalId," | ",reason);
      return;
   }

   // Двухфазная fail-closed защита от дубля после аварийного перезапуска:
   // сначала сигнал фиксируется как CLAIMED, затем выполняется единственная попытка OrderSend.
   D2_ExecutionLog(signalId,"CLAIMED","CLAIMED_BEFORE_ORDERSEND",sym,decisionTime,side,lots,currentPrice,sl,tp,currentRR,projectedLevel,-1,0);
   D2_AddProcessed(signalId);

   int command=(side==D2_SIDE_LONG?OP_BUY:OP_SELL);
   ResetLastError();
   int ticket=OrderSend(sym,command,lots,currentPrice,InpSlippagePoints,
                        D2_NormalizePrice(sym,sl),D2_NormalizePrice(sym,tp),
                        "DrummondD02",InpMagic,0,clrNONE);
   int err=GetLastError();

   if(ticket<0)
   {
      D2_ExecutionLog(signalId,"ORDER_REJECTED","ORDERSEND_ERROR_"+IntegerToString(err),
                      sym,decisionTime,side,lots,currentPrice,sl,tp,currentRR,projectedLevel,-1,err);
      Print("EXECUTOR REJECTED | ",signalId," | error=",err);
      return;
   }

   D2_ExecutionLog(signalId,"ORDER_OPENED","ORDER_OPENED",sym,decisionTime,side,lots,currentPrice,sl,tp,currentRR,projectedLevel,ticket,0);
   D2_LifeMapAdd(ticket,signalId);
   D2_LifecycleLogOpen(signalId,ticket);
   Print("EXECUTOR OPENED | ",signalId," | ticket=",ticket," | lot=",DoubleToString(lots,4),
         " | projected margin level=",DoubleToString(projectedLevel,2),"%");
}

void D2_ReadQueueAndExecute()
{
   int flags=FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE;
   if(InpRunMode==D2_EXECUTOR_DEMO) flags|=FILE_COMMON;
   int h=FileOpen(InpQueueFile,flags,';');
   if(h==INVALID_HANDLE) return; // До первого сигнала файл может ещё не существовать.

   while(!FileIsEnding(h))
   {
      string signalId=FileReadString(h);
      if(FileIsEnding(h) && signalId=="") break;
      string createdS=FileReadString(h);
      string sym=FileReadString(h);
      string decisionS=FileReadString(h);
      string sideS=FileReadString(h);
      string entryS=FileReadString(h);
      string slS=FileReadString(h);
      string tpS=FileReadString(h);
      string rrS=FileReadString(h);
      string signalName=FileReadString(h);
      string decisionTfS=FileReadString(h);
      string htpTfS=FileReadString(h);

      if(signalId=="" || signalId=="SIGNAL_ID") continue;
      if(D2_IsProcessed(signalId)) continue;

      int createdAt=(int)StringToInteger(createdS);

      // При раздельном тесте Watcher -> Executor очередь уже содержит будущие
      // сигналы всего периода. Не имеем права исполнять их раньше их времени.
      if(InpRunMode==D2_EXECUTOR_TESTER && createdAt>(int)TimeCurrent())
         continue;

      datetime decisionTime=(datetime)StringToInteger(decisionS);
      int side=D2_ParseSide(sideS);
      double entryRef=StringToDouble(entryS);
      double sl=StringToDouble(slS);
      double tp=StringToDouble(tpS);
      double rrFromWatcher=StringToDouble(rrS);

      D2_ProcessSignal(signalId,createdAt,sym,decisionTime,side,entryRef,sl,tp,rrFromWatcher,signalName);
   }
   FileClose(h);
}

void D2_TrailAllOurPositions()
{
   if(!InpTrailFurtherOut) return;
   if(InpRunMode==D2_EXECUTOR_TESTER)
   {
      if(!IsTesting() || !InpEnableTesterTrading || IsTradeContextBusy()) return;
   }
   else
   {
      if(!InpEnableDemoTrading || IsTesting() || !IsDemo() || !IsConnected() || !IsTradeAllowed() || IsTradeContextBusy()) return;
   }

   for(int i=OrdersTotal()-1;i>=0;i--)
   {
      if(!OrderSelect(i,SELECT_BY_POS,MODE_TRADES)) continue;
      if(OrderMagicNumber()!=InpMagic) continue;
      if(OrderType()!=OP_BUY && OrderType()!=OP_SELL) continue;

      string sym=OrderSymbol();
      int side=(OrderType()==OP_BUY?D2_SIDE_LONG:D2_SIDE_SHORT);
      double bid=MarketInfo(sym,MODE_BID);
      double ask=MarketInfo(sym,MODE_ASK);
      if(bid<=0.0 || ask<=0.0) continue;
      double reference=(side==D2_SIDE_LONG?bid:ask);

      double candidate=0.0;
      if(!D2_ResolveStructuralStop(sym,side,InpDecisionTF,reference,InpProtectionBufferPoints,candidate)) continue;

      double oldSL=OrderStopLoss();
      bool tighter=false;
      if(side==D2_SIDE_LONG)
      {
         if(candidate>=bid) continue;
         tighter=(oldSL<=0.0 || candidate>oldSL+D2_Point(sym));
      }
      else
      {
         if(candidate<=ask) continue;
         tighter=(oldSL<=0.0 || candidate<oldSL-D2_Point(sym));
      }
      if(!tighter) continue;

      int stopPts=(int)MarketInfo(sym,MODE_STOPLEVEL);
      int freezePts=(int)MarketInfo(sym,MODE_FREEZELEVEL);
      double minDistance=MathMax(stopPts,freezePts)*D2_Point(sym);
      if(side==D2_SIDE_LONG && bid-candidate<minDistance) continue;
      if(side==D2_SIDE_SHORT && candidate-ask<minDistance) continue;

      ResetLastError();
      bool ok=OrderModify(OrderTicket(),OrderOpenPrice(),D2_NormalizePrice(sym,candidate),OrderTakeProfit(),0,clrNONE);
      int err=GetLastError();
      if(ok)
      {
         D2_ExecutionLog("","TRAIL_UPDATED","TRAIL_UPDATED",sym,0,side,OrderLots(),reference,candidate,OrderTakeProfit(),0.0,0.0,OrderTicket(),0);
         Print("EXECUTOR TRAIL UPDATED | ",sym," | ticket=",OrderTicket()," | SL=",DoubleToString(candidate,D2_Digits(sym)));
      }
      else
      {
         D2_ExecutionLog("","TRAIL_REJECTED","ORDERMODIFY_ERROR_"+IntegerToString(err),sym,0,side,OrderLots(),reference,candidate,OrderTakeProfit(),0.0,0.0,OrderTicket(),err);
      }
   }
}

int OnInit()
{
   if(InpRunMode==D2_EXECUTOR_TESTER)
   {
      if(!IsTesting())
      {
         Print("EXECUTOR INIT BLOCKED: TESTER_MODE_OUTSIDE_STRATEGY_TESTER");
         return(INIT_FAILED);
      }
      if(InpClearTesterExecutionOnInit)
         FileDelete(InpExecutionFile,0);
      if(InpClearTesterLifecycleOnInit)
         FileDelete(InpLifecycleFile,0);
      ArrayResize(g_lifeTickets,0);
      ArrayResize(g_lifeSignalIds,0);
      ArrayResize(g_lifeClosedLogged,0);
   }
   else
   {
      if(IsTesting())
      {
         Print("EXECUTOR INIT BLOCKED: DEMO_MODE_INSIDE_STRATEGY_TESTER");
         return(INIT_FAILED);
      }
      if(!IsDemo())
      {
         Print("EXECUTOR INIT BLOCKED: ACCOUNT_NOT_DEMO");
         return(INIT_FAILED);
      }
      if(InpTimerSeconds<1)
      {
         Print("EXECUTOR INIT BLOCKED: TIMER_TOO_SMALL");
         return(INIT_FAILED);
      }
   }

   D2_LoadProcessed();
   if(InpRunMode==D2_EXECUTOR_DEMO)
      EventSetTimer(InpTimerSeconds);

   Print("=====================================================");
   Print("DRUMMOND EXECUTOR DEMO 02 FIX2");
   Print("Run mode      = ",InpRunMode==D2_EXECUTOR_TESTER?"TESTER":"DEMO");
   Print("Tester trading= ",InpEnableTesterTrading);
   Print("Demo trading  = ",InpEnableDemoTrading);
   Print("Magic         = ",InpMagic);
   Print("Min margin lvl= ",DoubleToString(InpMinProjectedMarginLevelPct,2),"%");
   Print("Position limit= NONE ACCOUNT-WIDE");
   Print("One per symbol= ",InpOnePositionPerSymbol);
   Print("Lot policy    = BROKER MINIMUM LOT");
   if(InpRunMode==D2_EXECUTOR_TESTER)
   {
      Print("Queue         = tester\\files\\",InpQueueFile);
      Print("Execution log = tester\\files\\",InpExecutionFile);
      Print("Lifecycle log = tester\\files\\",InpLifecycleFile);
      Print("Driver        = OnTick (tester)");
   }
   else
   {
      Print("Queue         = Common\\Files\\",InpQueueFile);
      Print("Execution log = Common\\Files\\",InpExecutionFile);
      Print("Driver        = OnTimer (demo)");
   }
   Print("Processed IDs = ",ArraySize(g_processed));
   Print("=====================================================");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   if(InpRunMode==D2_EXECUTOR_TESTER)
      D2_ScanClosedLifecycle();
   if(InpRunMode==D2_EXECUTOR_DEMO)
      EventKillTimer();
   Print("EXECUTOR DEINIT reason=",reason);
}

void OnTimer()
{
   if(InpRunMode!=D2_EXECUTOR_DEMO) return;
   D2_TrailAllOurPositions();
   D2_ReadQueueAndExecute();
}

void OnTick()
{
   if(InpRunMode!=D2_EXECUTOR_TESTER) return;
   D2_ScanClosedLifecycle();
   D2_TrailAllOurPositions();
   D2_ReadQueueAndExecute();
}
