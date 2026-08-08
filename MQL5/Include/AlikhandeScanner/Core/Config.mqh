#pragma once

// Alikhande Scanner v1.1.0 centralized defaults and assumption registry.
// Values marked ASSUMED must be validated on the target broker/account.

#define AS_DEFAULT_SCAN_TIMER_MS              250      // [ASSUMED] ScannerPanel-derived scheduling default
#define AS_DEFAULT_SCAN_BUDGET_US             20000    // [ASSUMED] 20 ms processing budget
#define AS_DEFAULT_SYMBOLS_PER_SLICE           2       // [ASSUMED]
#define AS_DEFAULT_SPEC_WAIT_SECONDS          10       // [ASSUMED]
#define AS_DEFAULT_MAX_TICK_AGE_SECONDS       10       // [ASSUMED]
#define AS_DEFAULT_SPREAD_WARMUP_SAMPLES      30       // [ASSUMED]
#define AS_DEFAULT_MINIMUM_BARS              300       // [ASSUMED]

#define AS_DEFAULT_RISK_PERCENT               0.25     // Project decision
#define AS_MAXIMUM_RISK_PERCENT               0.50     // Project hard ceiling
#define AS_MINIMUM_RISK_REWARD                2.00     // Project hard floor
#define AS_DEFAULT_PREVIEW_TTL_SECONDS        30       // [ASSUMED]
#define AS_DEFAULT_MAX_DRIFT_POINTS           30       // [ASSUMED], symbol-specific validation still required

#define AS_SPREAD_NORMAL_MAX_RATIO            1.30
#define AS_SPREAD_ELEVATED_MAX_RATIO          1.70
#define AS_SPREAD_HIGH_MAX_RATIO              2.20
#define AS_ATR_QUALITY_FLOOR_RATIO             0.50     // ScannerPanel-derived gate
#define AS_ATR_QUALITY_CEILING_RATIO           2.50     // ScannerPanel-derived gate
#define AS_ATR_QUALITY_LOOKBACK               100

#define AS_DEFAULT_DAILY_LOSS_LIMIT_PCT        3.00     // [ASSUMED], disabled by default
#define AS_DEFAULT_TOTAL_DRAWDOWN_LIMIT_PCT    8.00     // [ASSUMED], disabled by default
#define AS_DEFAULT_MAX_CONSECUTIVE_LOSSES      5        // [ASSUMED], disabled by default

#define AS_DEFAULT_SYMBOLS "XAUUSD,EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD,NZDUSD"
#define AS_MANAGED_CHART_MARKER "ALKSCN_MANAGED_CHART"
#define AS_MAGIC_BASE 20260806
#define AS_ORDER_COMMENT "AlikhandeScanner"
