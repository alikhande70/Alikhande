#pragma once

// ---------------------------------------------------------------- data state
enum ENUM_AS_DATA_STATE
  {
   AS_DATA_UNINITIALIZED,
   AS_DATA_SELECTING,
   AS_DATA_DOWNLOADING,
   AS_DATA_SYNCHRONIZING,
   AS_DATA_READY,
   AS_DATA_STALE,
   AS_DATA_ERROR
  };

// ---------------------------------------------------------------- trend
enum ENUM_AS_TREND_CLASS
  {
   AS_STRONG_BEARISH = -3,
   AS_BEARISH        = -2,
   AS_WEAK_BEARISH   = -1,
   AS_NEUTRAL        =  0,
   AS_WEAK_BULLISH   =  1,
   AS_BULLISH        =  2,
   AS_STRONG_BULLISH =  3
  };

enum ENUM_AS_DIRECTION
  {
   AS_DIR_NONE  =  0,
   AS_DIR_LONG  =  1,
   AS_DIR_SHORT = -1
  };

// ---------------------------------------------------------------- structure
// Zones are typed at construction. v1.1.0 merged swing highs and swing lows
// into a single untyped band, which inflated the touch count that feeds zone
// quality, which feeds the score. Supply and demand are tracked separately.
enum ENUM_AS_ZONE_TYPE
  {
   AS_ZONE_SUPPLY,   // formed by swing highs
   AS_ZONE_DEMAND    // formed by swing lows
  };

// Where price sits relative to a zone.
//
// An explicit three-way relation rather than a pair of booleans. The boolean
// form quietly conflates two different situations — "price is not inside the
// zone" and "there is no usable zone" — and that conflation is what produced
// v1.1.0's blindness at the entry trigger. Making UNAVAILABLE its own answer
// forces every caller to decide what to do about it.
//
// Lives in Domain rather than beside the zone engine because Models carries it
// on the signal candidate, and Domain must never depend upward on Analysis.
enum ENUM_AS_ZONE_RELATION
  {
   AS_ZONE_REL_UNAVAILABLE,  // no usable zone (invalid, broken, malformed)
   AS_ZONE_REL_BELOW,        // price is below the band
   AS_ZONE_REL_INSIDE,       // price is within the band — the interaction case
   AS_ZONE_REL_ABOVE         // price is above the band
  };

enum ENUM_AS_SETUP_TYPE
  {
   AS_SETUP_NONE,
   AS_TREND_PULLBACK,
   AS_SUPPORT_REJECTION,
   AS_RESISTANCE_REJECTION,
   AS_BREAKOUT_RETEST      // reserved; never emitted until it has its own tests
  };

// ---------------------------------------------------------------- regime
enum ENUM_AS_REGIME
  {
   AS_REGIME_UNKNOWN,
   AS_REGIME_TREND_UP,
   AS_REGIME_TREND_DOWN,
   AS_REGIME_RANGE,
   AS_REGIME_VOLATILE,
   AS_REGIME_QUIET,
   AS_REGIME_ILLIQUID
  };

// ---------------------------------------------------------------- quotes
enum ENUM_AS_SPREAD_STATE
  {
   AS_SPREAD_WARMING_UP,
   AS_SPREAD_NORMAL,
   AS_SPREAD_ELEVATED,
   AS_SPREAD_HIGH,
   AS_SPREAD_EXTREME,
   AS_SPREAD_STALE,
   AS_SPREAD_NO_TICK
  };

// ---------------------------------------------------------------- lifecycle
// A signal is never "shown once and forgotten". Every candidate walks this
// machine and every transition is persisted, which is what makes outcome
// statistics possible later.
enum ENUM_AS_SIGNAL_STATE
  {
   AS_SIGNAL_NONE,
   AS_SIGNAL_CANDIDATE,     // score cleared threshold, not yet actionable
   AS_SIGNAL_CONFIRMED,     // setup qualified and structurally valid
   AS_SIGNAL_PREVIEWED,     // shown to the operator with a sized plan
   AS_SIGNAL_ACTIVE,        // a position exists against this signal
   AS_SIGNAL_TP,
   AS_SIGNAL_SL,
   AS_SIGNAL_EXPIRED,       // TTL elapsed without action
   AS_SIGNAL_INVALIDATED,   // structure broke before entry
   AS_SIGNAL_NOT_FILLED,
   AS_SIGNAL_AMBIGUOUS      // outcome could not be reconciled — needs a human
  };

// ---------------------------------------------------------------- execution
enum ENUM_AS_EXEC_STATE
  {
   AS_EXEC_IDLE,
   AS_EXEC_SUBMITTING,
   AS_EXEC_ACCEPTED,
   AS_EXEC_PARTIALLY_FILLED,
   AS_EXEC_FILLED,
   AS_EXEC_POSITION_ACTIVE,
   AS_EXEC_REJECTED,
   AS_EXEC_CANCELLED,
   AS_EXEC_UNKNOWN,         // sent, no confirmation — must be reconciled
   AS_EXEC_RECONCILING,
   AS_EXEC_COMPLETED
  };

// Operating mode. Real trading is not reachable in the 1.x line at all: there
// is no enum member for it, so no configuration mistake can select it.
enum ENUM_AS_RUN_MODE
  {
   AS_MODE_ALERT_ONLY,   // scan and report; no order ever leaves the terminal
   AS_MODE_SHADOW,       // full plan + preflight, logged as if sent, never sent
   // Demo accounts only, AND every order requires a two-step human action
   // (arm, then confirm). There is deliberately no mode that sends
   // automatically: an EA that fires on its own is not supervised.
   AS_MODE_DEMO_CONFIRM
  };

// ---------------------------------------------------------------- exposure
enum ENUM_AS_ASSET_CLASS
  {
   AS_ASSET_UNKNOWN,
   AS_ASSET_FX,
   AS_ASSET_METAL,
   AS_ASSET_INDEX,
   AS_ASSET_CRYPTO,
   AS_ASSET_STOCK
  };

enum ENUM_AS_CHART_REUSE
  {
   AS_CHART_MANAGED_ONLY,
   AS_CHART_REUSE_ANY_MATCHING,
   AS_CHART_ALWAYS_OPEN_NEW
  };
