#pragma once

// Centralised defaults and assumption registry.
//
// Every value marked [ASSUMED] is a working default that has NOT been validated
// against a live broker/account. Treat them as hypotheses, not settings: the
// acceptance run on the target account is what turns an [ASSUMED] into a fact.
// Values marked [POLICY] are project decisions and are not tunable downward
// without an explicit policy change.

// ---------------------------------------------------------------- scheduling
#define AS_DEFAULT_SCAN_TIMER_MS            250      // [ASSUMED]
#define AS_DEFAULT_SCAN_BUDGET_US           20000    // [ASSUMED] 20 ms per slice
#define AS_DEFAULT_SYMBOLS_PER_SLICE        2        // [ASSUMED]
#define AS_DEFAULT_MINIMUM_BARS             300      // [ASSUMED]

// ---------------------------------------------------------------- data quality
#define AS_DEFAULT_MAX_TICK_AGE_SECONDS     10       // [ASSUMED]
#define AS_DEFAULT_SPREAD_WARMUP_SAMPLES    30       // [ASSUMED]
#define AS_SPREAD_SAMPLE_CAPACITY           240      // [ASSUMED]

#define AS_SPREAD_NORMAL_MAX_RATIO          1.30     // [ASSUMED]
#define AS_SPREAD_ELEVATED_MAX_RATIO        1.70     // [ASSUMED]
#define AS_SPREAD_HIGH_MAX_RATIO            2.20     // [ASSUMED]

// ---------------------------------------------------------------- volatility
#define AS_ATR_QUALITY_FLOOR_RATIO          0.50     // [ASSUMED]
#define AS_ATR_QUALITY_CEILING_RATIO        2.50     // [ASSUMED]
#define AS_ATR_QUALITY_LOOKBACK             100      // [ASSUMED]

// ---------------------------------------------------------------- structure
#define AS_ZONE_LOOKBACK_BARS               300      // [ASSUMED]
#define AS_ZONE_PIVOT_LEFT                  3        // [ASSUMED]
#define AS_ZONE_PIVOT_RIGHT                 3        // [ASSUMED]
#define AS_ZONE_WIDTH_ATR_FRACTION          0.20     // [ASSUMED]
#define AS_ZONE_PROXIMITY_ATR               1.50     // [ASSUMED] max distance to be "at" a zone
#define AS_STOP_BUFFER_ATR                  0.15     // [ASSUMED] beyond the zone edge
#define AS_MAX_STOP_DISTANCE_ATR            2.50     // [ASSUMED] reject structurally absurd stops

// ---------------------------------------------------------------- scoring
#define AS_SIGNAL_SCORE_THRESHOLD           75.0     // [ASSUMED]
#define AS_SIGNAL_SCORE_SEPARATION          10.0     // [ASSUMED] winner must lead by this much
#define AS_SIGNAL_TTL_SECONDS               900      // [ASSUMED] 15 min candidate lifetime

// ---------------------------------------------------------------- risk
#define AS_DEFAULT_RISK_PERCENT             0.25     // [POLICY]
#define AS_MAXIMUM_RISK_PERCENT             0.50     // [POLICY] hard ceiling per trade
#define AS_MINIMUM_RISK_REWARD              2.00     // [POLICY] hard floor
#define AS_RISK_ROUNDING_TOLERANCE          1.01     // [POLICY] max 1% overshoot from lot rounding

#define AS_DEFAULT_MAX_OPEN_RISK_PCT        1.00     // [ASSUMED] aggregate across open trades
#define AS_DEFAULT_MAX_CURRENCY_RISK_PCT    0.75     // [ASSUMED] per currency leg
#define AS_DEFAULT_MAX_ASSET_CLASS_RISK_PCT 1.00     // [ASSUMED]

#define AS_DEFAULT_DAILY_LOSS_LIMIT_PCT     3.00     // [ASSUMED], guard disabled by default
#define AS_DEFAULT_TOTAL_DRAWDOWN_LIMIT_PCT 8.00     // [ASSUMED], guard disabled by default
#define AS_DEFAULT_MAX_CONSECUTIVE_LOSSES   5        // [ASSUMED], guard disabled by default

// ---------------------------------------------------------------- execution
#define AS_DEFAULT_PREVIEW_TTL_SECONDS      30       // [ASSUMED]
#define AS_DEFAULT_MAX_DRIFT_POINTS         30       // [ASSUMED] symbol-specific validation needed
#define AS_RECONCILE_GRACE_SECONDS          30       // [ASSUMED] before an unknown send is escalated

// ---------------------------------------------------------------- news
#define AS_NEWS_PRE_MINUTES                 30       // [ASSUMED]
#define AS_NEWS_POST_MINUTES                15       // [ASSUMED]

// ---------------------------------------------------------------- statistics
// Below this sample count no probability is displayed at all. A rule score is
// not a probability, and a probability from 8 trades is not evidence.
#define AS_MIN_OUTCOME_SAMPLE               30       // [POLICY]

// ---------------------------------------------------------------- identity
#define AS_DEFAULT_SYMBOLS "XAUUSD,EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD,NZDUSD"
#define AS_MANAGED_CHART_MARKER "ALKSCN_MANAGED_CHART"
#define AS_MAGIC                20260806
#define AS_ORDER_COMMENT        "AlikhandeScanner"
#define AS_DATABASE_FILE        "AlikhandeScanner\\alikhande.sqlite"
#define AS_CSV_EXPORT_FILE      "AlikhandeScanner\\signals_export.csv"
