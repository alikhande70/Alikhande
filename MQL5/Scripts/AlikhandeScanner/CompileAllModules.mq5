#property strict
#property version "1.10"
#include <AlikhandeScanner/Core/Config.mqh>
#include <AlikhandeScanner/Core/VersionInfo.mqh>
#include <AlikhandeScanner/Core/Hash.mqh>
#include <AlikhandeScanner/Core/NewBarDetector.mqh>
#include <AlikhandeScanner/Core/SignalRegistry.mqh>
#include <AlikhandeScanner/Domain/Models.mqh>
#include <AlikhandeScanner/Broker/SymbolResolver.mqh>
#include <AlikhandeScanner/Broker/SymbolSpec.mqh>
#include <AlikhandeScanner/Data/MarketData.mqh>
#include <AlikhandeScanner/Data/SpreadTracker.mqh>
#include <AlikhandeScanner/Analysis/TrendEngine.mqh>
#include <AlikhandeScanner/Analysis/ZoneEngine.mqh>
#include <AlikhandeScanner/Signals/SignalEngine.mqh>
#include <AlikhandeScanner/Statistics/Statistics.mqh>
#include <AlikhandeScanner/Storage/SignalLogger.mqh>
#include <AlikhandeScanner/Safety/TradeGuards.mqh>
#include <AlikhandeScanner/Safety/AccountRiskGuard.mqh>
#include <AlikhandeScanner/Trading/RiskPlanner.mqh>
#include <AlikhandeScanner/Trading/DemoExecution.mqh>
#include <AlikhandeScanner/UI/Dashboard.mqh>
void OnStart(){AS_MarketData a;AS_SymbolResolver b;AS_SymbolSpecReader c;AS_TrendEngine d;AS_ZoneEngine e;AS_SignalEngine f;AS_Statistics g;AS_SignalLogger h;AS_TradeGuards i;AS_AccountRiskGuard j;AS_RiskPlanner k;AS_DemoExecution l;AS_Dashboard m;AS_NewBarDetector n;AS_SignalRegistry o;Print("Alikhande compile-all modules parsed, version ",AS_VERSION);}
