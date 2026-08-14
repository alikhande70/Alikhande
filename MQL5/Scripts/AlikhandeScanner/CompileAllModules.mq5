#property strict
#property version "1.30"
#property description "Parses every Alikhande module so MetaEditor reports errors for all of them."

// Compile this FIRST. The EA only pulls in what it uses, so a broken module
// that nothing currently references would otherwise stay invisible until the
// day something starts using it.

#include <AlikhandeScanner/Core/Config.mqh>
#include <AlikhandeScanner/Core/VersionInfo.mqh>
#include <AlikhandeScanner/Core/Hash.mqh>
#include <AlikhandeScanner/Core/Log.mqh>
#include <AlikhandeScanner/Domain/Enums.mqh>
#include <AlikhandeScanner/Domain/Models.mqh>
#include <AlikhandeScanner/Persistence/Database.mqh>
#include <AlikhandeScanner/Persistence/Repositories.mqh>
#include <AlikhandeScanner/Broker/SymbolResolver.mqh>
#include <AlikhandeScanner/Broker/SymbolSpec.mqh>
#include <AlikhandeScanner/Data/IndicatorCache.mqh>
#include <AlikhandeScanner/Data/MarketData.mqh>
#include <AlikhandeScanner/Data/SpreadTracker.mqh>
#include <AlikhandeScanner/Analysis/TrendEngine.mqh>
#include <AlikhandeScanner/Analysis/ZoneEngine.mqh>
#include <AlikhandeScanner/Analysis/RegimeEngine.mqh>
#include <AlikhandeScanner/Signals/SignalEngine.mqh>
#include <AlikhandeScanner/Signals/SignalLifecycle.mqh>
#include <AlikhandeScanner/Statistics/Statistics.mqh>
#include <AlikhandeScanner/Risk/PortfolioRisk.mqh>
#include <AlikhandeScanner/Risk/RiskPlanner.mqh>
#include <AlikhandeScanner/Risk/TradeGuards.mqh>
#include <AlikhandeScanner/Risk/AccountRiskGuard.mqh>
#include <AlikhandeScanner/Execution/Preflight.mqh>
#include <AlikhandeScanner/Execution/ExecutionEngine.mqh>
#include <AlikhandeScanner/UI/Theme.mqh>
#include <AlikhandeScanner/UI/Dashboard.mqh>

void OnStart()
  {
   // Instantiating each type forces the compiler past declaration-only checks
   // into the member definitions.
   AS_Log              log;
   AS_Database         database;
   AS_Repositories     repositories;
   AS_SymbolResolver   resolver;
   AS_SymbolSpecReader spec_reader;
   AS_IndicatorCache   indicators;
   AS_MarketData       market;
   AS_SpreadTracker    spreads;
   AS_TrendEngine      trend;
   AS_ZoneEngine       zones;
   AS_RegimeEngine     regime;
   AS_SignalEngine     signal;
   AS_Statistics       statistics;
   AS_PortfolioRisk    portfolio;
   AS_RiskPlanner      planner;
   AS_TradeGuards      guards;
   AS_AccountRiskGuard account_guard;
   AS_Preflight        preflight;
   AS_ExecutionEngine  execution;
   AS_Dashboard        dashboard;

   PrintFormat("Alikhande %s (%s) - all modules parsed. Schema v%d, rules %s.",
               AS_VERSION, AS_EDITION, AS_DB_SCHEMA_VERSION, AS_RULE_VERSION);
  }
