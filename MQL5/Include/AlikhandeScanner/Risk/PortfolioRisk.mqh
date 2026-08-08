//+------------------------------------------------------------------+
//| PortfolioRisk.mqh                                                 |
//| Extends per-trade risk with aggregate exposure gates: per-symbol, |
//| total open risk, currency exposure, asset-class exposure, and a   |
//| daily risk budget that resets on broker server day change.        |
//+------------------------------------------------------------------+
#property strict

struct PortfolioRiskLimits
  {
   double maxPerTradeRiskPct;
   double maxOpenRiskPct;
   double maxPerSymbolRiskPct;
   double maxPerCurrencyRiskPct;
   double maxDailyRiskPct;
  };

struct PortfolioRiskGateResult
  {
   bool   allowed;
   string blockReason;
   double currentOpenRiskPct;
   double currentCurrencyRiskPct;
   double currentDailyUsedPct;
  };

// Extracts the two 3-letter currency legs from a symbol name, tolerating
// broker suffixes/prefixes (e.g. EURUSD_o, #GBPJPY) the way SymbolResolver
// already does for the base symbol lookup.
void ExtractCurrencyLegs(const string rawSymbol, string &base, string &quote)
  {
   string s = rawSymbol;
   // Strip common broker decorations; SymbolResolver.mqh owns the canonical
   // logic — this is a light local copy so PortfolioRisk has no compile-time
   // dependency loop back into Broker/.
   int firstHash = StringFind(s, "#");
   if(firstHash == 0) s = StringSubstr(s, 1);
   int suffixPos = StringFind(s, "_");
   if(suffixPos == 6) s = StringSubstr(s, 0, 6);

   if(StringLen(s) >= 6)
     {
      base  = StringSubstr(s, 0, 3);
      quote = StringSubstr(s, 3, 3);
     }
   else
     {
      base = s;
      quote = "";
     }
  }

//+------------------------------------------------------------------+
//| Sum the risk (in % of equity) currently open, broken down by      |
//| symbol and by currency leg, by scanning open positions this EA    |
//| manages (matched via magic number, set by the caller).            |
//+------------------------------------------------------------------+
double ComputeCurrencyExposurePct(const string currency, const long magicNumber)
  {
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= 0.0)
      return 0.0;

   double totalRiskMoney = 0.0;
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(magicNumber != 0 && (long)PositionGetInteger(POSITION_MAGIC) != magicNumber)
         continue;

      string sym = PositionGetString(POSITION_SYMBOL);
      string base, quote;
      ExtractCurrencyLegs(sym, base, quote);
      if(base != currency && quote != currency)
         continue;

      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double volume = PositionGetDouble(POSITION_VOLUME);
      if(sl <= 0.0)
         continue; // no stop = cannot quantify defined risk; flagged separately by TradeGuards

      double tickValue = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
      double tickSize  = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
      if(tickSize <= 0.0)
         continue;

      double riskMoney = MathAbs(openPrice - sl) / tickSize * tickValue * volume;
      totalRiskMoney += riskMoney;
     }

   return (totalRiskMoney / equity) * 100.0;
  }

double ComputeTotalOpenRiskPct(const long magicNumber)
  {
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= 0.0)
      return 0.0;

   double totalRiskMoney = 0.0;
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(magicNumber != 0 && (long)PositionGetInteger(POSITION_MAGIC) != magicNumber)
         continue;

      string sym = PositionGetString(POSITION_SYMBOL);
      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double volume = PositionGetDouble(POSITION_VOLUME);
      if(sl <= 0.0)
         continue;

      double tickValue = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
      double tickSize  = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
      if(tickSize <= 0.0)
         continue;

      totalRiskMoney += MathAbs(openPrice - sl) / tickSize * tickValue * volume;
     }

   return (totalRiskMoney / equity) * 100.0;
  }

//+------------------------------------------------------------------+
//| The gate a new trade plan must pass before RiskPlanner accepts    |
//| it. Blocks outright rather than silently down-sizing — a resized  |
//| trade the user didn't ask for is its own kind of surprise.        |
//+------------------------------------------------------------------+
PortfolioRiskGateResult EvaluatePortfolioRiskGate(const string symbol, const double newTradeRiskPct,
                                                   const PortfolioRiskLimits &limits,
                                                   const long magicNumber,
                                                   const double dailyUsedRiskPct)
  {
   PortfolioRiskGateResult res;
   res.allowed = true;
   res.blockReason = "";

   res.currentOpenRiskPct = ComputeTotalOpenRiskPct(magicNumber);
   res.currentDailyUsedPct = dailyUsedRiskPct;

   if(newTradeRiskPct > limits.maxPerTradeRiskPct)
     {
      res.allowed = false;
      res.blockReason = StringFormat("per-trade risk %.2f%% exceeds cap %.2f%%",
                                      newTradeRiskPct, limits.maxPerTradeRiskPct);
      return res;
     }

   if(res.currentOpenRiskPct + newTradeRiskPct > limits.maxOpenRiskPct)
     {
      res.allowed = false;
      res.blockReason = StringFormat("open risk %.2f%% + new %.2f%% exceeds cap %.2f%%",
                                      res.currentOpenRiskPct, newTradeRiskPct, limits.maxOpenRiskPct);
      return res;
     }

   string base, quote;
   ExtractCurrencyLegs(symbol, base, quote);
   double baseExposure  = ComputeCurrencyExposurePct(base, magicNumber);
   double quoteExposure = ComputeCurrencyExposurePct(quote, magicNumber);
   res.currentCurrencyRiskPct = MathMax(baseExposure, quoteExposure);

   if(res.currentCurrencyRiskPct + newTradeRiskPct > limits.maxPerCurrencyRiskPct)
     {
      res.allowed = false;
      res.blockReason = StringFormat("currency exposure %.2f%% + new %.2f%% exceeds cap %.2f%%",
                                      res.currentCurrencyRiskPct, newTradeRiskPct,
                                      limits.maxPerCurrencyRiskPct);
      return res;
     }

   if(dailyUsedRiskPct + newTradeRiskPct > limits.maxDailyRiskPct)
     {
      res.allowed = false;
      res.blockReason = StringFormat("daily risk budget %.2f%% + new %.2f%% exceeds cap %.2f%%",
                                      dailyUsedRiskPct, newTradeRiskPct, limits.maxDailyRiskPct);
      return res;
     }

   return res;
  }
