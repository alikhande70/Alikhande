//+------------------------------------------------------------------+
//| CompileAllModules.mq5                                              |
//| Includes every header so MetaEditor parses all modules. Required   |
//| gate: 0 errors / 0 warnings (docs/v1.1.0_ACCEPTANCE_TESTS.md).     |
//| Compile this FIRST, before SymbolDiscovery/SymbolSpec/the EA.      |
//+------------------------------------------------------------------+
#property copyright "Alikhande"
#property version   "1.20"

#include <AlikhandeScanner/Core/Config.mqh>
#include <AlikhandeScanner/Core/VersionInfo.mqh>
#include <AlikhandeScanner/Core/Hash.mqh>
#include <AlikhandeScanner/Core/ParameterHash.mqh>
#include <AlikhandeScanner/Core/NewBarDetector.mqh>
#include <AlikhandeScanner/Core/SignalRegistry.mqh>

#include <AlikhandeScanner/Domain/Enums.mqh>
#include <AlikhandeScanner/Domain/Models.mqh>
#include <AlikhandeScanner/Domain/SignalLifecycle.mqh>

#include <AlikhandeScanner/Storage/Database.mqh>
#include <AlikhandeScanner/Storage/SignalLogger.mqh>

#include <AlikhandeScanner/Broker/SymbolResolver.mqh>
#include <AlikhandeScanner/Broker/SymbolSpec.mqh>

#include <AlikhandeScanner/Data/MarketData.mqh>
#include <AlikhandeScanner/Data/SpreadTracker.mqh>

#include <AlikhandeScanner/Analysis/TrendEngine.mqh>
#include <AlikhandeScanner/Analysis/ZoneEngine.mqh>

#include <AlikhandeScanner/Signals/SignalEngine.mqh>

#include <AlikhandeScanner/Risk/PortfolioRisk.mqh>
#include <AlikhandeScanner/Trading/RiskPlanner.mqh>
#include <AlikhandeScanner/Trading/DemoExecution.mqh>

#include <AlikhandeScanner/Safety/TradeGuards.mqh>
#include <AlikhandeScanner/Safety/AccountRiskGuard.mqh>

#include <AlikhandeScanner/News/NewsFilter.mqh>

#include <AlikhandeScanner/Execution/TradeRequestTracker.mqh>
#include <AlikhandeScanner/Execution/ExecutionStateMachine.mqh>
#include <AlikhandeScanner/Execution/OrderPreflight.mqh>

#include <AlikhandeScanner/Health/SystemHealth.mqh>
#include <AlikhandeScanner/Statistics/Statistics.mqh>
#include <AlikhandeScanner/UI/DashboardTabs.mqh>

#include <AlikhandeScanner/Tests/TestFramework.mqh>
#include <AlikhandeScanner/Tests/SignalLifecycleTests.mqh>
#include <AlikhandeScanner/Tests/PortfolioRiskTests.mqh>
#include <AlikhandeScanner/Tests/ExecutionTests.mqh>

void OnStart()
  {
   Print("Alikhande: all modules parsed. ", AlikhandeVersionString());
  }
