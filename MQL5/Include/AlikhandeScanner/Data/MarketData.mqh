//+------------------------------------------------------------------+
//| MarketData.mqh                                                     |
//| Live quote + indicator buffer access. EMA buffers are read with   |
//| explicit chronological indexing (index 0 = current/forming bar,   |
//| ascending index = further into the past) — the v1.1.0 changelog   |
//| calls out a chronology bug here, so every read is index-explicit  |
//| rather than assumed.                                              |
//+------------------------------------------------------------------+
#property strict

struct MarketSnapshot
  {
   double bid, ask, spreadPoints;
   double atr;
   double atrQualityRatio; // ATR / its own N-bar average — normalizes "is ATR unusually high/low"
   double ema20, ema50, ema200;
   datetime tickTime;
  };

double ReadAtr(const string symbol, const ENUM_TIMEFRAMES tf, const int period, const int shift)
  {
   int handle = iATR(symbol, tf, period);
   if(handle == INVALID_HANDLE)
      return 0.0;

   double buf[];
   ArraySetAsSeries(buf, true);
   if(CopyBuffer(handle, 0, shift, 1, buf) <= 0)
      return 0.0;
   return buf[0];
  }

double ReadAtrQualityRatio(const string symbol, const ENUM_TIMEFRAMES tf, const int period,
                            const int avgWindow)
  {
   int handle = iATR(symbol, tf, period);
   if(handle == INVALID_HANDLE)
      return 1.0;

   double buf[];
   ArraySetAsSeries(buf, true);
   if(CopyBuffer(handle, 0, 0, avgWindow, buf) <= 0 || ArraySize(buf) < avgWindow)
      return 1.0;

   double sum = 0.0;
   for(int i = 0; i < avgWindow; i++)
      sum += buf[i];
   double avg = sum / avgWindow;
   if(avg <= 0.0)
      return 1.0;

   return buf[0] / avg;
  }

double ReadEma(const string symbol, const ENUM_TIMEFRAMES tf, const int period, const int shift)
  {
   int handle = iMA(symbol, tf, period, 0, MODE_EMA, PRICE_CLOSE);
   if(handle == INVALID_HANDLE)
      return 0.0;

   double buf[];
   ArraySetAsSeries(buf, true); // index 0 = most recent — explicit, not assumed
   if(CopyBuffer(handle, 0, shift, 1, buf) <= 0)
      return 0.0;
   return buf[0];
  }

MarketSnapshot FetchMarketSnapshot(const string symbol, const ENUM_TIMEFRAMES atrTf,
                                    const int atrPeriod)
  {
   MarketSnapshot snap;
   MqlTick tick;
   if(SymbolInfoTick(symbol, tick))
     {
      snap.bid = tick.bid;
      snap.ask = tick.ask;
      snap.tickTime = tick.time;
     }

   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   snap.spreadPoints = (point > 0.0) ? (snap.ask - snap.bid) / point : 0.0;

   snap.atr = ReadAtr(symbol, atrTf, atrPeriod, 0);
   snap.atrQualityRatio = ReadAtrQualityRatio(symbol, atrTf, atrPeriod, 20);

   snap.ema20  = ReadEma(symbol, atrTf, 20, 0);
   snap.ema50  = ReadEma(symbol, atrTf, 50, 0);
   snap.ema200 = ReadEma(symbol, atrTf, 200, 0);

   return snap;
  }
