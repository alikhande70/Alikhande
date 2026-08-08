#property strict
#property version "1.20"
#property description "In-terminal self-tests for logic the static gate cannot evaluate."

#include <AlikhandeScanner/Testing/TestRunner.mqh>
#include <AlikhandeScanner/Signals/SignalLifecycle.mqh>
#include <AlikhandeScanner/Statistics/Statistics.mqh>
#include <AlikhandeScanner/Analysis/ZoneEngine.mqh>
#include <AlikhandeScanner/Analysis/TrendEngine.mqh>
#include <AlikhandeScanner/Risk/PortfolioRisk.mqh>
#include <AlikhandeScanner/Core/Hash.mqh>
#include <AlikhandeScanner/News/CalendarGate.mqh>
#include <AlikhandeScanner/Execution/ArmedIntent.mqh>

//+------------------------------------------------------------------+
void TestLifecycle(AS_TestRunner &t)
  {
   t.Suite("signal lifecycle");

   t.Check(AS_SignalTransitionAllowed(AS_SIGNAL_CANDIDATE, AS_SIGNAL_CONFIRMED),
           "CANDIDATE -> CONFIRMED allowed");
   t.Check(AS_SignalTransitionAllowed(AS_SIGNAL_PREVIEWED, AS_SIGNAL_ACTIVE),
           "PREVIEWED -> ACTIVE allowed");
   t.Check(AS_SignalTransitionAllowed(AS_SIGNAL_ACTIVE, AS_SIGNAL_TP),
           "ACTIVE -> TP allowed");

   t.Check(!AS_SignalTransitionAllowed(AS_SIGNAL_CANDIDATE, AS_SIGNAL_ACTIVE),
           "CANDIDATE -> ACTIVE rejected (skips CONFIRMED and PREVIEWED)");
   t.Check(!AS_SignalTransitionAllowed(AS_SIGNAL_TP, AS_SIGNAL_ACTIVE),
           "terminal TP cannot transition");
   t.Check(!AS_SignalTransitionAllowed(AS_SIGNAL_ACTIVE, AS_SIGNAL_ACTIVE),
           "self-transition rejected");

   t.Check(AS_SignalStateIsScorable(AS_SIGNAL_TP) && AS_SignalStateIsScorable(AS_SIGNAL_SL),
           "TP and SL are scorable");
   t.Check(!AS_SignalStateIsScorable(AS_SIGNAL_EXPIRED)
           && !AS_SignalStateIsScorable(AS_SIGNAL_INVALIDATED),
           "EXPIRED and INVALIDATED are NOT scorable (they describe the scanner)");
  }

//+------------------------------------------------------------------+
void TestWilson(AS_TestRunner &t)
  {
   t.Suite("Wilson interval");

   double low = 0.0, high = 0.0;

   t.Check(!AS_Statistics::Wilson(0, 0, low, high), "zero sample rejected");
   t.Check(!AS_Statistics::Wilson(5, 3, low, high), "wins > total rejected");

   t.Check(AS_Statistics::Wilson(50, 100, low, high), "50/100 computes");
   t.Check(low < 0.50 && high > 0.50, "interval brackets the point estimate");
   t.CheckClose(low, 0.404, 0.01, "50/100 lower bound");
   t.CheckClose(high, 0.596, 0.01, "50/100 upper bound");

   // The property that matters at small n: the interval must stay inside
   // [0,1] and stay wide, which is exactly where the normal approximation
   // misbehaves and would report an impossible bound.
   t.Check(AS_Statistics::Wilson(5, 5, low, high), "5/5 computes");
   t.Check(low >= 0.0 && high <= 1.0, "5/5 stays inside [0,1]");
   t.Check(low < 0.70, "5/5 lower bound stays honest about small n");

   t.Check(AS_Statistics::Wilson(0, 20, low, high), "0/20 computes");
   t.Check(low >= 0.0 && high > 0.0, "0/20 has a non-degenerate upper bound");

   double wide_low = 0.0, wide_high = 0.0, narrow_low = 0.0, narrow_high = 0.0;
   AS_Statistics::Wilson(15, 30, wide_low, wide_high);
   AS_Statistics::Wilson(500, 1000, narrow_low, narrow_high);
   t.Check((wide_high - wide_low) > (narrow_high - narrow_low),
           "interval narrows as the sample grows");
  }

//+------------------------------------------------------------------+
void TestZoneLookups(AS_TestRunner &t)
  {
   t.Suite("zone lookups");

   AS_Zone zones[];
   ArrayResize(zones, 3);

   ZeroMemory(zones[0]);
   zones[0].type = AS_ZONE_DEMAND;
   zones[0].low = 1.0950; zones[0].high = 1.0970; zones[0].center = 1.0960;
   zones[0].valid = true;

   ZeroMemory(zones[1]);
   zones[1].type = AS_ZONE_SUPPLY;
   zones[1].low = 1.1040; zones[1].high = 1.1060; zones[1].center = 1.1050;
   zones[1].valid = true;

   ZeroMemory(zones[2]);
   zones[2].type = AS_ZONE_DEMAND;
   zones[2].low = 1.0850; zones[2].high = 1.0870; zones[2].center = 1.0860;
   zones[2].valid = true;

   int index = -1;

   // The case v1.1.0 could not express: price sitting INSIDE a demand zone.
   // Its nearest-zone search required zone.high <= bid, so this returned
   // nothing and no pullback setup could ever qualify.
   t.Check(AS_FindNearestZone(zones, AS_ZONE_DEMAND, 1.0960, 0.0050, index),
           "demand zone found while price is inside it");
   t.Check(index == 0, "nearest demand zone is the containing one");
   t.Check(AS_PriceInsideZone(zones[0], 1.0960), "price recognised as inside the zone");

   t.Check(AS_FindNearestZone(zones, AS_ZONE_DEMAND, 1.0955, 0.0050, index) && index == 0,
           "nearest demand zone chosen by distance");
   t.Check(!AS_FindNearestZone(zones, AS_ZONE_SUPPLY, 1.0960, 0.0010, index),
           "supply zone beyond max distance is not returned");

   t.Check(AS_FindZoneBeyond(zones, AS_ZONE_SUPPLY, 1.0960, true, index) && index == 1,
           "opposing supply zone found above price");
   t.Check(AS_FindZoneBeyond(zones, AS_ZONE_DEMAND, 1.0900, false, index) && index == 2,
           "opposing demand zone found below price");
   t.Check(!AS_FindZoneBeyond(zones, AS_ZONE_SUPPLY, 1.2000, true, index),
           "no zone above an extreme price");

   // The three-way relation. UNAVAILABLE must be distinguishable from
   // "outside the band" — collapsing them is what made v1.1.0 blind.
   t.Check(AS_ZoneRelation(zones[0], 1.0960) == AS_ZONE_REL_INSIDE, "inside detected");
   t.Check(AS_ZoneRelation(zones[0], 1.0900) == AS_ZONE_REL_BELOW, "below detected");
   t.Check(AS_ZoneRelation(zones[0], 1.1000) == AS_ZONE_REL_ABOVE, "above detected");

   AS_Zone malformed;
   ZeroMemory(malformed);
   malformed.valid = true;
   malformed.low = 1.10; malformed.high = 1.09;   // inverted band
   t.Check(AS_ZoneRelation(malformed, 1.095) == AS_ZONE_REL_UNAVAILABLE,
           "inverted band reports UNAVAILABLE, not a position");

   AS_Zone invalid_zone;
   ZeroMemory(invalid_zone);
   t.Check(AS_ZoneRelation(invalid_zone, 1.0) == AS_ZONE_REL_UNAVAILABLE,
           "invalid zone reports UNAVAILABLE");

   // Anchoring direction: demand anchors longs, supply anchors shorts.
   t.Check(AS_ZoneAnchors(zones[0], AS_DIR_LONG), "demand anchors a long");
   t.Check(!AS_ZoneAnchors(zones[0], AS_DIR_SHORT), "demand does not anchor a short");
   t.Check(AS_ZoneAnchors(zones[1], AS_DIR_SHORT), "supply anchors a short");
   t.Check(!AS_ZoneAnchors(zones[1], AS_DIR_LONG), "supply does not anchor a long");
   t.Check(!AS_ZoneAnchors(zones[0], AS_DIR_NONE), "no direction anchors nothing");

   // A broken zone must never be returned.
   zones[0].broken = true;
   t.Check(!(AS_FindNearestZone(zones, AS_ZONE_DEMAND, 1.0960, 0.0005, index) && index == 0),
           "broken zone is excluded");
   t.Check(AS_ZoneRelation(zones[0], 1.0960) == AS_ZONE_REL_UNAVAILABLE,
           "broken zone reports UNAVAILABLE even with price inside it");
   t.Check(!AS_ZoneAnchors(zones[0], AS_DIR_LONG), "broken zone cannot anchor");
  }

//+------------------------------------------------------------------+
void TestDirectionalBonus(AS_TestRunner &t)
  {
   t.Suite("directional strength");

   AS_TrendResult bullish;
   ZeroMemory(bullish);
   bullish.valid = true;
   bullish.direction_score = 60.0;
   bullish.strength = 45.0;

   AS_TrendResult bearish;
   ZeroMemory(bearish);
   bearish.valid = true;
   bearish.direction_score = -60.0;
   bearish.strength = 45.0;

   AS_TrendResult neutral;
   ZeroMemory(neutral);
   neutral.valid = true;
   neutral.direction_score = 0.0;
   neutral.strength = 30.0;

   t.CheckClose(AS_DirectionalBonus(bullish, AS_DIR_LONG), 45.0, 1e-9,
                "bullish trend feeds the long side");
   t.CheckClose(AS_DirectionalBonus(bullish, AS_DIR_SHORT), 0.0, 1e-9,
                "bullish trend contributes nothing to the short side");
   t.CheckClose(AS_DirectionalBonus(bearish, AS_DIR_SHORT), 45.0, 1e-9,
                "bearish trend feeds the short side");
   t.CheckClose(AS_DirectionalBonus(bearish, AS_DIR_LONG), 0.0, 1e-9,
                "bearish trend contributes nothing to the long side");

   // The H4-neutral bug: a neutral trend must give NEITHER side a bonus.
   t.CheckClose(AS_DirectionalBonus(neutral, AS_DIR_LONG), 0.0, 1e-9,
                "neutral trend gives the long side nothing");
   t.CheckClose(AS_DirectionalBonus(neutral, AS_DIR_SHORT), 0.0, 1e-9,
                "neutral trend gives the short side nothing");

   AS_TrendResult invalid;
   ZeroMemory(invalid);
   invalid.valid = false;
   invalid.direction_score = 80.0;
   invalid.strength = 70.0;
   t.CheckClose(AS_DirectionalBonus(invalid, AS_DIR_LONG), 0.0, 1e-9,
                "invalid trend contributes nothing");
  }

//+------------------------------------------------------------------+
void TestExposure(AS_TestRunner &t)
  {
   t.Suite("portfolio exposure");

   AS_PortfolioRisk portfolio;

   t.Check(portfolio.AssetClass("EURUSD") == AS_ASSET_FX, "EURUSD is FX");
   t.Check(portfolio.AssetClass("XAUUSD") == AS_ASSET_METAL, "XAUUSD is metal");
   t.Check(portfolio.AssetClass("XAUUSD_o") == AS_ASSET_METAL, "broker suffix tolerated");
   t.Check(portfolio.AssetClass("BTCUSD") == AS_ASSET_CRYPTO, "BTCUSD is crypto");

   AS_ExposureSummary exposure;
   ZeroMemory(exposure);
   exposure.open_risk_pct = 0.80;
   exposure.currency_risk_pct = 0.60;
   exposure.asset_class_risk_pct = 0.50;
   exposure.dominant_currency = "USD";

   string reason = "";
   t.Check(portfolio.Allows(exposure, 0.15, 1.00, 0.75, 1.00, reason),
           "trade inside every cap is allowed");

   // A position with no computable worst case must block everything. Treating
   // it as zero risk lets the caps pass *because* the dangerous position is
   // invisible to them.
   AS_ExposureSummary unbounded = exposure;
   unbounded.unbounded_positions = 1;
   unbounded.unbounded_symbols = "XAUUSD;";
   t.Check(!portfolio.Allows(unbounded, 0.01, 99.0, 99.0, 99.0, reason),
           "unbounded position blocks even with caps set absurdly wide");
   t.Check(StringFind(reason, "UNBOUNDED_RISK") >= 0,
           "block reason names unbounded risk");
   t.Check(StringFind(reason, "XAUUSD") >= 0,
           "block reason names the offending symbol");

   t.Check(!portfolio.Allows(exposure, 0.30, 1.00, 0.75, 1.00, reason),
           "trade breaching the open-risk cap is blocked");
   t.Check(StringFind(reason, "OPEN_RISK") >= 0, "block reason names the open-risk cap");

   t.Check(!portfolio.Allows(exposure, 0.20, 2.00, 0.75, 2.00, reason),
           "trade breaching the currency cap is blocked");
   t.Check(StringFind(reason, "USD") >= 0, "block reason names the dominant currency");
  }

//+------------------------------------------------------------------+
void TestNewsGate(AS_TestRunner &t)
  {
   t.Suite("calendar gate");

   AS_CalendarGate gate;

   AS_RuntimeContext production;
   ZeroMemory(production);
   production.kind = AS_RUNTIME_TERMINAL;
   production.is_production = true;

   AS_RuntimeContext tester;
   ZeroMemory(tester);
   tester.kind = AS_RUNTIME_TESTER;
   tester.is_production = false;

   // Outside the terminal the calendar is not consulted at all, and the honest
   // answer is UNKNOWN. Reporting CLEAR here is the fail-open bug: a backtest
   // would trade through every high-impact release while appearing filtered.
   const AS_NewsVerdict in_tester = gate.Evaluate("EURUSD", tester, 30, 15, false);
   t.Check(in_tester.state == AS_NEWS_UNKNOWN, "tester yields UNKNOWN, not CLEAR");
   t.Check(in_tester.source == AS_NEWS_SOURCE_UNAVAILABLE, "tester source is UNAVAILABLE");

   AS_NewsVerdict unknown;
   ZeroMemory(unknown);
   unknown.state = AS_NEWS_UNKNOWN;

   AS_NewsVerdict blocked;
   ZeroMemory(blocked);
   blocked.state = AS_NEWS_BLOCKED;

   AS_NewsVerdict clear;
   ZeroMemory(clear);
   clear.state = AS_NEWS_CLEAR;

   gate.ApplyRuntimePolicy(production);
   t.Check(gate.BlocksTrading(unknown), "production: UNKNOWN blocks (fail-safe)");
   t.Check(gate.BlocksTrading(blocked), "production: BLOCKED blocks");
   t.Check(!gate.BlocksTrading(clear), "production: CLEAR does not block");
   t.Check(!gate.IsNewsBlind(), "production run is not news-blind");

   gate.ApplyRuntimePolicy(tester);
   t.Check(!gate.BlocksTrading(unknown),
           "tester: UNKNOWN does not block, or no backtest could ever trade");
   t.Check(gate.BlocksTrading(blocked), "tester: an actual BLOCKED verdict still blocks");
   t.Check(gate.IsNewsBlind(), "tester run is flagged news-blind");

   t.Check(AS_NewsStateName(AS_NEWS_UNKNOWN) == "UNKNOWN", "state name round trip");
   t.Check(AS_NewsSourceName(AS_NEWS_SOURCE_LIVE) == "LIVE", "source name round trip");
  }

//+------------------------------------------------------------------+
void TestArming(AS_TestRunner &t)
  {
   t.Suite("two-step arming");

   AS_IntentArming arming;
   arming.SetTtl(60);

   AS_TradePlan plan;
   ZeroMemory(plan);
   plan.valid = true;
   plan.plan_id = "SIG_A_PLAN";
   plan.symbol = "EURUSD";
   plan.lot_size = 0.10;

   string reason = "";

   // Nothing may execute without an arm first.
   t.Check(!arming.IsArmed(), "starts disarmed");
   t.Check(!arming.Confirm(plan, reason), "confirm without arm is refused");
   t.Check(reason == "NO_ARMED_INTENT", "refusal names the missing arm");

   t.Check(arming.Arm(plan), "valid plan arms");
   t.Check(arming.IsArmed(), "intent reads armed");
   t.Check(arming.Confirm(plan, reason), "confirm after arm succeeds");
   t.Check(!arming.IsArmed(), "confirming consumes the intent");
   t.Check(!arming.Confirm(plan, reason), "the same arm cannot fire twice");

   // A plan replaced underneath the operator must not execute: they armed
   // something they can no longer see.
   AS_TradePlan superseded;
   ZeroMemory(superseded);
   superseded.valid = true;
   superseded.plan_id = "SIG_B_PLAN";
   superseded.symbol = "EURUSD";

   arming.Arm(plan);
   t.Check(!arming.Confirm(superseded, reason), "superseded plan is refused");
   t.Check(reason == "ARMED_PLAN_SUPERSEDED", "refusal names the supersession");
   t.Check(!arming.IsArmed(), "a refused confirm disarms rather than lingering");

   // An invalid plan cannot be armed at all.
   AS_TradePlan invalid;
   ZeroMemory(invalid);
   invalid.valid = false;
   t.Check(!arming.Arm(invalid), "invalid plan cannot be armed");

   // Expiry: arming is permission that decays.
   AS_IntentArming short_lived;
   short_lived.SetTtl(5);          // clamped minimum
   short_lived.Arm(plan);
   t.Check(short_lived.IsArmed(), "freshly armed intent is live");
   t.Check(!short_lived.Sweep(), "sweep does not expire a live intent");
  }

//+------------------------------------------------------------------+
void TestHash(AS_TestRunner &t)
  {
   t.Suite("hashing");

   t.Check(AS_Fnv1a("alpha") == AS_Fnv1a("alpha"), "32-bit hash is deterministic");
   t.Check(AS_Fnv1a("alpha") != AS_Fnv1a("beta"), "32-bit hash separates inputs");
   t.Check(StringLen(AS_Fnv1a("alpha")) == 8, "32-bit hash is 8 hex characters");

   t.Check(AS_Fnv1a64("alpha") == AS_Fnv1a64("alpha"), "64-bit hash is deterministic");
   t.Check(AS_Fnv1a64("alpha") != AS_Fnv1a64("beta"), "64-bit hash separates inputs");
   t.Check(StringLen(AS_Fnv1a64("alpha")) == 16, "64-bit hash is 16 hex characters");

   // Single-character difference must not collide — signal ids differ by
   // exactly this little.
   t.Check(AS_Fnv1a64("EURUSD|1|1|1000|RULE-1.2.0")
           != AS_Fnv1a64("EURUSD|1|1|1001|RULE-1.2.0"),
           "adjacent confirmation times produce different ids");
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   AS_TestRunner runner;

   TestLifecycle(runner);
   TestWilson(runner);
   TestZoneLookups(runner);
   TestDirectionalBonus(runner);
   TestExposure(runner);
   TestNewsGate(runner);
   TestArming(runner);
   TestHash(runner);

   if(runner.Summary())
      Print("Alikhande self-tests PASSED");
   else
      PrintFormat("Alikhande self-tests FAILED (%d)", runner.Failed());
  }
