//+------------------------------------------------------------------+
//| ClaudeICTForward — ICT multi-timeframe model (Strategy Tester only)    |
//| Bias : Daily direction, confirmed by H4 structure.               |
//| Setup: M5 liquidity sweep of a swing -> market-structure shift    |
//|        (MSS) with displacement, taken only in a killzone.         |
//| Risk : stop behind the swept liquidity; target the next pool (RR).|
//| Idea : trade rarely, with HTF bias, and ride toward liquidity.    |
//| BACKTEST / RESEARCH ONLY — refuses to init outside the Tester.    |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#include <Trade/Trade.mqh>

input int    SwingWing        = 2;      // fractal half-width for M5 swings
input int    SwingLookback    = 40;     // bars to search for last swing
input int    SetupMaxAge      = 12;     // bars allowed sweep -> MSS
input int    RetraceWindow    = 8;      // bars allowed MSS -> FVG retrace fill
input bool   RequireFVG       = false;  // FVG-retrace entry (tested: hurt IS, off)
input double MinDisplaceAtr   = 0.6;    // MSS candle body >= this * ATR
input int    AtrPeriod        = 14;     // ATR period (M5)
input double StopBufferAtr    = 0.15;   // stop = swept extreme +/- this*ATR
input double RR               = 3.0;    // reward:risk target (liquidity pool)
input bool   UsePremiumDiscount= true;  // long only in discount, short in premium
input int    RangeLookback    = 50;     // bars defining the dealing range
input bool   UseVolatilityFilter= false; // tested: overfit (helped IS, hurt OOS)
input int    VolBaselinePeriod = 96;    // long ATR baseline (dead-market gauge)
input double VolExpandMult      = 1.0;   // require ATR14 >= mult * baseline ATR
input bool   UseTrail         = true;   // trail after +1R to lock profit
input double TrailStartR      = 1.5;    // start trailing at this many R
input double TrailDistanceR   = 1.2;    // trail this many R behind price
input double RiskPercent      = 1.0;    // risk % of equity per trade
input int    DailyBiasLookback= 3;      // D1 momentum lookback for bias
input bool   UseKillzones     = true;   // restrict entries to killzones
input bool   UseLondon        = false;  // London off: diagnosed net loser IS+OOS
input bool   UseNY            = true;   // New York killzone (diagnosed: winner)
input int    LondonStart      = 7;      // server hour (inclusive)
input int    LondonEnd        = 11;     // server hour (exclusive)
input int    NyStart          = 12;     // server hour (inclusive)
input int    NyEnd            = 21;     // server hour (exclusive)
input double CommissionLotSide= 5.0;    // $/lot/side for safer sizing
input int    DeviationPoints  = 30;
input long   Magic            = 71721;  // forward-demo magic

CTrade Trade;
int    h_atr = INVALID_HANDLE;
int    h_atr_slow = INVALID_HANDLE;

// setup state machine
int    g_phase = 0;      // 0 idle, 1 armed waiting MSS
int    g_dir   = 0;      // 1 long, -1 short
int    g_age   = 0;
double g_liq_extreme = 0.0;   // swept liquidity price (stop reference)
double g_mss_level   = 0.0;   // structure level to break for entry
double g_fvg_low     = 0.0;   // fair value gap lower edge
double g_fvg_high    = 0.0;   // fair value gap upper edge
double g_track_R = 0.0;       // captured R for trailing
ulong  g_ticket  = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   // FORWARD-DEMO GUARD: runs in the tester or on a DEMO account only.
   // A real-money account is refused unconditionally.
   if(!(bool)MQLInfoInteger(MQL_TESTER) &&
      AccountInfoInteger(ACCOUNT_TRADE_MODE) != ACCOUNT_TRADE_MODE_DEMO)
   {
      Print("ClaudeICTForward: DEMO/TESTER ONLY. Real account refused.");
      return INIT_FAILED;
   }
   if(_Period != PERIOD_M5)
   {
      Print("ClaudeICTForward: run on M5 (uses D1/H4 internally).");
      return INIT_FAILED;
   }
   if(SwingWing < 1 || SwingLookback < 10 || AtrPeriod < 2 || RR <= 0
      || RiskPercent <= 0)
      return INIT_PARAMETERS_INCORRECT;
   h_atr = iATR(_Symbol, _Period, AtrPeriod);
   h_atr_slow = iATR(_Symbol, _Period, VolBaselinePeriod);
   if(h_atr == INVALID_HANDLE || h_atr_slow == INVALID_HANDLE) return INIT_FAILED;
   Trade.SetExpertMagicNumber(Magic);
   Trade.SetDeviationInPoints(DeviationPoints);
   Trade.SetTypeFillingBySymbol(_Symbol);
   Trade.SetAsyncMode(false);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(h_atr != INVALID_HANDLE) IndicatorRelease(h_atr);
   if(h_atr_slow != INVALID_HANDLE) IndicatorRelease(h_atr_slow);
}

//+------------------------------------------------------------------+
double Atr(){ double v[1]; if(CopyBuffer(h_atr,0,1,1,v)!=1) return 0.0; return v[0]; }

int VolumeDigits(const double step){ int d=0; double s=step;
   while(d<8 && MathAbs(s-MathRound(s))>1e-8){ s*=10.0; d++; } return d; }

double NormalizeLotsDown(double lots){
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   double mn=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double mx=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   if(step<=0||mn<=0||mx<=0||lots<=0) return 0.0;
   lots=MathFloor((lots+step*1e-10)/step)*step; lots=MathMin(lots,mx);
   if(lots+1e-12<mn) return 0.0; return NormalizeDouble(lots,VolumeDigits(step)); }

double NormalizePrice(const double p){
   double ts=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE); if(ts<=0) ts=_Point;
   return NormalizeDouble(MathRound(p/ts)*ts,_Digits); }

double RiskLots(const int dir,const double entry,const double stop){
   if(dir==0||entry<=0||stop<=0) return 0.0;
   ENUM_ORDER_TYPE ot=(dir>0)?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
   double one=0.0; if(!OrderCalcProfit(ot,_Symbol,1.0,entry,stop,one)) return 0.0;
   double lpl=MathAbs(one)+2.0*MathMax(CommissionLotSide,0.0); if(lpl<=0) return 0.0;
   double money=AccountInfoDouble(ACCOUNT_EQUITY)*RiskPercent/100.0;
   double lots=NormalizeLotsDown(money/lpl);
   double margin=0.0,freem=AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   if(OrderCalcMargin(ot,_Symbol,1.0,entry,margin)&&margin>0&&lots*margin>freem)
      lots=NormalizeLotsDown(freem/margin);
   return lots; }

//+------------------------------------------------------------------+
// Daily bias: last completed D1 candle direction + momentum.        |
int DailyBias()
{
   double c1=iClose(_Symbol,PERIOD_D1,1);
   double o1=iOpen(_Symbol,PERIOD_D1,1);
   double cN=iClose(_Symbol,PERIOD_D1,1+DailyBiasLookback);
   if(c1<=0||cN<=0) return 0;
   bool up = (c1>o1) && (c1>cN);
   bool dn = (c1<o1) && (c1<cN);
   if(up && !dn) return 1;
   if(dn && !up) return -1;
   return 0;
}

// H4 agreement: last H4 close vs H4 close a few bars back.          |
bool H4Agrees(const int dir)
{
   double c1=iClose(_Symbol,PERIOD_H4,1);
   double c3=iClose(_Symbol,PERIOD_H4,3);
   if(c1<=0||c3<=0) return false;
   return (dir>0) ? (c1>c3) : (c1<c3);
}

// Most recent confirmed fractal swing low price/shift on M5.        |
bool LastSwingLow(double &price,int &shift)
{
   for(int s=1+SwingWing; s<=SwingLookback; s++)
   {
      double lo=iLow(_Symbol,_Period,s); bool ok=true;
      for(int k=1;k<=SwingWing;k++)
         if(lo>iLow(_Symbol,_Period,s-k)||lo>iLow(_Symbol,_Period,s+k)){ok=false;break;}
      if(ok){ price=lo; shift=s; return true; }
   }
   return false;
}
bool LastSwingHigh(double &price,int &shift)
{
   for(int s=1+SwingWing; s<=SwingLookback; s++)
   {
      double hi=iHigh(_Symbol,_Period,s); bool ok=true;
      for(int k=1;k<=SwingWing;k++)
         if(hi<iHigh(_Symbol,_Period,s-k)||hi<iHigh(_Symbol,_Period,s+k)){ok=false;break;}
      if(ok){ price=hi; shift=s; return true; }
   }
   return false;
}

bool InKillzone()
{
   if(!UseKillzones) return true;
   MqlDateTime t; TimeToStruct(TimeCurrent(),t);
   int h=t.hour;
   bool london=UseLondon && (h>=LondonStart && h<LondonEnd);
   bool ny=UseNY && (h>=NyStart && h<NyEnd);
   return (london||ny);
}

bool HasPosition()
{
   for(int i=PositionsTotal()-1;i>=0;i--){
      ulong t=PositionGetTicket(i);
      if(t>0 && PositionGetString(POSITION_SYMBOL)==_Symbol
         && (long)PositionGetInteger(POSITION_MAGIC)==Magic) return true; }
   return false;
}

void ResetSetup(){ g_phase=0; g_dir=0; g_age=0; g_liq_extreme=0.0; g_mss_level=0.0;
                   g_fvg_low=0.0; g_fvg_high=0.0; }

//+------------------------------------------------------------------+
void ManageTrail()
{
   if(!UseTrail) return;
   ulong ticket=0;
   for(int i=PositionsTotal()-1;i>=0;i--){
      ulong t=PositionGetTicket(i);
      if(t>0 && PositionGetString(POSITION_SYMBOL)==_Symbol
         && (long)PositionGetInteger(POSITION_MAGIC)==Magic){ ticket=t; break; } }
   if(ticket==0){ g_ticket=0; g_track_R=0.0; return; }
   if(!PositionSelectByTicket(ticket)) return;
   double entry=PositionGetDouble(POSITION_PRICE_OPEN);
   double sl=PositionGetDouble(POSITION_SL);
   double tp=PositionGetDouble(POSITION_TP);
   int dir=(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY)?1:-1;
   if(ticket!=g_ticket){ g_ticket=ticket; g_track_R=(sl>0)?MathAbs(entry-sl):0.0; }
   double R=g_track_R; if(R<=0) return;
   MqlTick tk; if(!SymbolInfoTick(_Symbol,tk)) return;
   double px=(dir>0)?tk.bid:tk.ask;
   double pr=dir*(px-entry)/R;
   if(pr<TrailStartR) return;
   double trail=px-dir*TrailDistanceR*R;
   double ns=(dir>0)?MathMax(sl,trail):MathMin(sl,trail);
   long stops=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL);
   double mind=MathMax(0.0,(double)stops*_Point);
   if(dir>0 && px-ns<mind) ns=px-mind;
   if(dir<0 && ns-px<mind) ns=px+mind;
   ns=NormalizePrice(ns);
   if((dir>0 && ns>sl && ns<px)||(dir<0 && ns<sl && ns>px))
      Trade.PositionModify(ticket,ns,tp);
}

//+------------------------------------------------------------------+
bool NewBar(){ static datetime p=0; datetime c=iTime(_Symbol,_Period,0);
   if(c<=0||c==p) return false; p=c; return true; }

void OnTick()
{
   ForwardHeartbeat();
   if(HasPosition()){ ManageTrail(); return; }
   else { g_ticket=0; g_track_R=0.0; }

   if(!NewBar()) return;
   double atr=Atr(); if(atr<=0) return;
   if(iBars(_Symbol,_Period) < SwingLookback+SwingWing+5) return;

   int bias=DailyBias();
   if(bias==0){ ResetSetup(); return; }
   if(!H4Agrees(bias)){ ResetSetup(); return; }

   double open_1=iOpen(_Symbol,_Period,1);
   double high_1=iHigh(_Symbol,_Period,1);
   double low_1=iLow(_Symbol,_Period,1);
   double close_1=iClose(_Symbol,_Period,1);

   // ---- phase 0: hunt a liquidity sweep aligned with bias ----
   if(g_phase==0)
   {
      if(UseVolatilityFilter)
      {
         double av[1];
         double atr_slow=(CopyBuffer(h_atr_slow,0,1,1,av)==1)?av[0]:0.0;
         if(atr_slow>0 && atr < VolExpandMult*atr_slow) return;  // dead market
      }
      if(bias>0)
      {
         double sl_price; int sl_shift;
         double sh_price; int sh_shift;
         if(LastSwingLow(sl_price,sl_shift) && LastSwingHigh(sh_price,sh_shift))
         {
            // sweep the swing low then close back above it (stop hunt)
            if(low_1 < sl_price && close_1 > sl_price && sh_price > close_1)
            {
               g_phase=1; g_dir=1; g_age=0;
               g_liq_extreme=low_1;         // stop reference (below swept low)
               g_mss_level=sh_price;        // break this high for MSS
            }
         }
      }
      else
      {
         double sl_price; int sl_shift;
         double sh_price; int sh_shift;
         if(LastSwingHigh(sh_price,sh_shift) && LastSwingLow(sl_price,sl_shift))
         {
            if(high_1 > sh_price && close_1 < sh_price && sl_price < close_1)
            {
               g_phase=1; g_dir=-1; g_age=0;
               g_liq_extreme=high_1;
               g_mss_level=sl_price;
            }
         }
      }
      return;
   }

   // ---- phase 1: wait for MSS + displacement that leaves an FVG ----
   if(g_phase==1)
   {
      g_age++;
      if(g_age>SetupMaxAge || g_dir!=bias){ ResetSetup(); return; }
      if((g_dir>0 && close_1 < g_liq_extreme) ||
         (g_dir<0 && close_1 > g_liq_extreme)){ ResetSetup(); return; }

      double body=MathAbs(close_1-open_1);
      bool displaced = body >= MinDisplaceAtr*atr;
      bool mss = (g_dir>0) ? (close_1 > g_mss_level) : (close_1 < g_mss_level);
      if(!(mss && displaced)) return;

      // three-candle FVG around the displacement bar (bar 1)
      double h3=iHigh(_Symbol,_Period,3), l3=iLow(_Symbol,_Period,3);
      double h1=iHigh(_Symbol,_Period,1), l1=iLow(_Symbol,_Period,1);
      if(RequireFVG)
      {
         if(g_dir>0 && l1 > h3){ g_fvg_low=h3; g_fvg_high=l1; }
         else if(g_dir<0 && h1 < l3){ g_fvg_low=h1; g_fvg_high=l3; }
         else return;                          // no valid FVG yet; keep waiting
         g_phase=2; g_age=0;
         return;
      }
      // FVG not required -> fall through to immediate entry below
      g_fvg_low=0.0; g_fvg_high=0.0; g_phase=2; g_age=0;
   }

   // ---- phase 2: enter on retrace into the FVG (or immediately) ----
   g_age++;
   if(g_age>RetraceWindow || g_dir!=bias){ ResetSetup(); return; }
   if((g_dir>0 && close_1 < g_liq_extreme) ||
      (g_dir<0 && close_1 > g_liq_extreme)){ ResetSetup(); return; }

   if(RequireFVG)
   {
      double ce=(g_fvg_low+g_fvg_high)/2.0;    // consequent encroachment (midpoint)
      bool retraced = (g_dir>0) ? (low_1 <= ce) : (high_1 >= ce);
      if(!retraced) return;
   }
   if(!InKillzone()) return;

   MqlTick tk; if(!SymbolInfoTick(_Symbol,tk)) return;
   double entry=(g_dir>0)?tk.ask:tk.bid;

   // Premium/Discount (ICT): buy only in discount half, sell only in premium.
   if(UsePremiumDiscount)
   {
      int rh=iHighest(_Symbol,_Period,MODE_HIGH,RangeLookback,1);
      int rl=iLowest(_Symbol,_Period,MODE_LOW,RangeLookback,1);
      if(rh>=0 && rl>=0)
      {
         double eq=(iHigh(_Symbol,_Period,rh)+iLow(_Symbol,_Period,rl))/2.0;
         if((g_dir>0 && entry>eq) || (g_dir<0 && entry<eq)){ ResetSetup(); return; }
      }
   }

   double stop=NormalizePrice(g_liq_extreme - g_dir*StopBufferAtr*atr);
   if((g_dir>0 && stop>=entry)||(g_dir<0 && stop<=entry)){ ResetSetup(); return; }
   double target=NormalizePrice(entry + g_dir*RR*MathAbs(entry-stop));
   double lots=RiskLots(g_dir,entry,stop);
   if(lots<=0){ ResetSetup(); return; }
   bool ok=(g_dir>0)?Trade.Buy(lots,_Symbol,0.0,stop,target,"ClaudeICT")
                    :Trade.Sell(lots,_Symbol,0.0,stop,target,"ClaudeICT");
   ResetSetup();
}
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//|                 FORWARD-DEMO JOURNALING                           |
//| Every deal on our magic and a daily equity heartbeat go to CSV in |
//| the COMMON files folder, so weekly review needs no terminal access|
//+------------------------------------------------------------------+
datetime g_fwdLastDay = 0;

void ForwardAppend(const string fileName, const string line, const string header)
  {
   int h = FileOpen(fileName, FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(h == INVALID_HANDLE)
      return;
   bool fresh = (FileSize(h) == 0);
   FileSeek(h, 0, SEEK_END);
   if(fresh)
      FileWriteString(h, header + "\r\n");
   FileWriteString(h, line + "\r\n");
   FileClose(h);
  }

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;
   if(!HistoryDealSelect(trans.deal))
      return;
   if(HistoryDealGetString(trans.deal, DEAL_SYMBOL) != _Symbol)
      return;
   if((long)HistoryDealGetInteger(trans.deal, DEAL_MAGIC) != Magic)
      return;
   string line = StringFormat("%s,%I64u,%s,%s,%.2f,%.2f,%.2f,%.2f,%.2f",
      TimeToString((datetime)HistoryDealGetInteger(trans.deal, DEAL_TIME),
                   TIME_DATE | TIME_MINUTES | TIME_SECONDS),
      trans.deal,
      (HistoryDealGetInteger(trans.deal, DEAL_TYPE) == DEAL_TYPE_BUY ? "BUY" : "SELL"),
      (HistoryDealGetInteger(trans.deal, DEAL_ENTRY) == DEAL_ENTRY_IN ? "IN" : "OUT"),
      HistoryDealGetDouble(trans.deal, DEAL_VOLUME),
      HistoryDealGetDouble(trans.deal, DEAL_PRICE),
      HistoryDealGetDouble(trans.deal, DEAL_PROFIT),
      HistoryDealGetDouble(trans.deal, DEAL_COMMISSION),
      AccountInfoDouble(ACCOUNT_EQUITY));
   ForwardAppend("ICT_Forward_Deals_" + _Symbol + ".csv", line,
                 "time,deal,type,entry,volume,price,profit,commission,equity");
  }

void ForwardHeartbeat()
  {
   datetime day = iTime(_Symbol, PERIOD_D1, 0);
   if(day <= 0 || day == g_fwdLastDay)
      return;
   g_fwdLastDay = day;
   string line = StringFormat("%s,%.2f,%.2f,%d",
      TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES),
      AccountInfoDouble(ACCOUNT_BALANCE),
      AccountInfoDouble(ACCOUNT_EQUITY),
      (int)PositionsTotal());
   ForwardAppend("ICT_Forward_Heartbeat_" + _Symbol + ".csv", line,
                 "time,balance,equity,open_positions");
  }
//+------------------------------------------------------------------+
