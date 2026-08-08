//+------------------------------------------------------------------+
//| PortfolioRiskTests.mqh                                            |
//| Covers the pure-function parts of PortfolioRisk.mqh (currency leg |
//| extraction). Exposure math needs a live/tester account context —  |
//| covered by acceptance tests instead, not unit tests.               |
//+------------------------------------------------------------------+
#property strict
#include "TestFramework.mqh"
#include "../Risk/PortfolioRisk.mqh"

void RunPortfolioRiskTests()
  {
   string base, quote;

   ExtractCurrencyLegs("EURUSD", base, quote);
   TestAssertEquals(base, "EUR", "EURUSD base leg");
   TestAssertEquals(quote, "USD", "EURUSD quote leg");

   ExtractCurrencyLegs("EURUSD_o", base, quote);
   TestAssertEquals(base, "EUR", "EURUSD_o base leg (broker suffix stripped)");
   TestAssertEquals(quote, "USD", "EURUSD_o quote leg (broker suffix stripped)");

   ExtractCurrencyLegs("#GBPJPY", base, quote);
   TestAssertEquals(base, "GBP", "#GBPJPY base leg (broker prefix stripped)");
   TestAssertEquals(quote, "JPY", "#GBPJPY quote leg (broker prefix stripped)");

   ExtractCurrencyLegs("XAUUSD", base, quote);
   TestAssertEquals(base, "XAU", "XAUUSD base leg");
   TestAssertEquals(quote, "USD", "XAUUSD quote leg");
  }
