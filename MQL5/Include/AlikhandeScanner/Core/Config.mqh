//+------------------------------------------------------------------+
//| Config.mqh                                                         |
//| Centralized defaults. Every value that isn't a documented broker  |
//| standard is marked [ASSUMED] — carried over as a policy from      |
//| v1.1.0 so tuning inputs never hide silently inside engine code.   |
//+------------------------------------------------------------------+
#property strict
#include "VersionInfo.mqh"

// --- Scheduler --------------------------------------------------------
#define CFG_TIMER_SLICE_MS        250   // [ASSUMED] v1.1.0 default
#define CFG_TIMER_BUDGET_MS       20    // [ASSUMED] v1.1.0 default
#define CFG_SYMBOLS_PER_SLICE     2     // [ASSUMED] v1.1.0 default

// --- Data quality -------------------------------------------------------
#define CFG_STALE_QUOTE_SECONDS   30    // [ASSUMED]

// --- Analysis timeframes -------------------------------------------------
#define CFG_TF_H4  PERIOD_H4
#define CFG_TF_H1  PERIOD_H1
#define CFG_TF_M15 PERIOD_M15
#define CFG_TF_M5  PERIOD_M5
#define CFG_ATR_PERIOD 14 // documented broker/community standard, not [ASSUMED]

// --- Zone / setup rules ---------------------------------------------------
#define CFG_ZONE_TOLERANCE_ATR    0.25  // [ASSUMED] proximity-to-zone tolerance, in ATR units
#define CFG_ATR_SL_BUFFER_MULT    0.5   // [ASSUMED] SL = zone edge +/- this * ATR
#define CFG_MIN_RR                2.0   // 2R target, documented in ACCEPTANCE_TESTS "Logic Gate"
#define CFG_PULLBACK_LOOKBACK_BARS 5    // [ASSUMED]

// --- Risk ------------------------------------------------------------
#define CFG_DEFAULT_RISK_PCT          0.5   // [ASSUMED] per-trade risk, percent of equity
#define CFG_DEFAULT_MAX_OPEN_RISK_PCT 2.0   // [ASSUMED]
#define CFG_DEFAULT_MAX_SYMBOL_RISK_PCT 1.0 // [ASSUMED]
#define CFG_DEFAULT_MAX_CCY_RISK_PCT  1.5   // [ASSUMED]
#define CFG_DEFAULT_DAILY_RISK_PCT    3.0   // [ASSUMED]

// --- News gate (P0 scope, see docs/ARCHITECTURE_V1.2.md section 6) ------
#define CFG_NEWS_PRE_MINUTES   30 // [ASSUMED]
#define CFG_NEWS_POST_MINUTES  15 // [ASSUMED]
#define CFG_NEWS_INCLUDE_MEDIUM false // [ASSUMED] high-impact only by default

// --- Execution ------------------------------------------------------
#define CFG_RECONCILE_GRACE_SECONDS 60 // [ASSUMED] before a SUBMITTING/UNKNOWN request is flagged stale
#define CFG_ORDER_DEVIATION_POINTS  10 // [ASSUMED]

// --- Safety -----------------------------------------------------------
// Alert-only by default; demo execution and account guards are opt-in.
#define CFG_ALERT_ONLY_DEFAULT true
#define CFG_ACCOUNT_GUARDS_ENABLED_DEFAULT false
