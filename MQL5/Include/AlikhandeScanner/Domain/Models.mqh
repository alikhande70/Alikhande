#pragma once
#include "Enums.mqh"

// Plain data carried between layers. No behaviour lives here; engines own the
// logic and these structs own the shape.

struct AS_SymbolSnapshot
  {
   string               requested_symbol;
   string               symbol;
   double               bid;
   double               ask;
   double               point;
   int                  digits;
   double               spread_points;
   double               spread_ratio;
   double               spread_percentile;
   datetime             tick_time;
   ENUM_AS_SPREAD_STATE spread_state;
   ENUM_AS_DATA_STATE   data_state;
  };

struct AS_SymbolSpec
  {
   string   symbol;
   int      digits;
   double   point;
   double   tick_size;
   double   tick_value;
   double   contract_size;
   double   volume_min;
   double   volume_max;
   double   volume_step;
   long     trade_mode;
   int      stops_level;
   int      freeze_level;
   string   fingerprint;   // hash of the fields that affect risk maths
   bool     ready;
  };

struct AS_TrendResult
  {
   ENUM_TIMEFRAMES     timeframe;
   double              direction_score;   // -100..+100
   double              strength;          // 0..100, magnitude only
   ENUM_AS_TREND_CLASS trend_class;
   double              ema50;
   double              ema200;
   double              adx;
   double              atr;
   double              atr_ratio;
   // Wall-clock time at which this information first became knowable — the
   // close of the analysed bar, never its open. Guards against look-ahead.
   datetime            available_information_time;
   bool                valid;
  };

struct AS_Zone
  {
   string            id;
   ENUM_AS_ZONE_TYPE type;
   ENUM_TIMEFRAMES   timeframe;
   double            low;
   double            high;
   double            center;
   int               touches;
   double            quality;          // 0..100
   datetime          pivot_time;
   datetime          confirmation_time;
   bool              broken;
   bool              valid;
  };

struct AS_RegimeResult
  {
   ENUM_AS_REGIME regime;
   double         confidence;      // 0..100
   string         reason;
   bool           valid;
  };

// One scored line of the score breakdown, so the dashboard can explain *why*
// a score is what it is instead of showing a bare number.
struct AS_ScoreComponent
  {
   string component;
   double contribution;
  };

struct AS_SignalCandidate
  {
   string               signal_id;
   string               symbol;
   ENUM_AS_DIRECTION    direction;
   ENUM_AS_SETUP_TYPE   setup;
   ENUM_AS_SIGNAL_STATE state;

   double               preferred_entry;
   double               entry_low;
   double               entry_high;
   double               stop_loss;
   double               take_profit;
   double               nearest_support;
   double               nearest_resistance;
   // Where price sits relative to the anchoring zones, so the panel can say
   // "inside demand" rather than the ambiguous "near support".
   ENUM_AS_ZONE_RELATION demand_relation;
   ENUM_AS_ZONE_RELATION supply_relation;

   double               long_score;      // rule score, NOT a probability
   double               short_score;
   string               reasons;         // ';'-joined component breakdown
   string               validation_codes;
   bool                 hard_blocked;

   // Outcome-derived statistics. `has_historical_estimate` stays false until a
   // real, sufficiently large outcome sample exists; the UI must never render a
   // probability while it is false.
   bool                 has_historical_estimate;
   double               historical_win_rate;
   int                  sample_size;
   double               confidence_low;
   double               confidence_high;

   datetime             confirmation_bar_time;
   datetime             creation_time;
   datetime             expires_at;

   string               rule_version;
   string               scoring_version;
   string               parameter_hash;
   string               broker_spec_hash;
  };

struct AS_TradePlan
  {
   string            plan_id;
   string            signal_id;
   string            symbol;
   ENUM_AS_DIRECTION direction;
   double            entry;
   double            stop_loss;
   double            take_profit;
   double            risk_percent;
   double            risk_amount;
   double            actual_risk_amount;
   double            lot_size;
   double            margin_required;
   double            preview_bid;
   double            preview_ask;
   datetime          created_at;
   datetime          expires_at;
   double            max_drift_points;
   double            minimum_rr;
   string            validation_codes;
   bool              valid;
  };

struct AS_ExecutionRecord
  {
   string             execution_id;
   string             plan_id;
   string             signal_id;
   string             symbol;
   ENUM_AS_EXEC_STATE state;
   ulong              request_id;
   ulong              order_ticket;
   ulong              deal_ticket;
   ulong              position_id;
   double             requested_volume;
   double             filled_volume;
   uint               retcode;
   string             message;
   datetime           created_at;
   datetime           updated_at;
   bool               terminal;
  };

struct AS_Outcome
  {
   string   signal_id;
   string   result;        // TP | SL | EXPIRED | INVALIDATED | NOT_FILLED | AMBIGUOUS
   double   realized_r;    // realised result in R multiples
   double   mfe_r;         // maximum favourable excursion, in R
   double   mae_r;         // maximum adverse excursion, in R
   datetime closed_at;
  };

// Persisted risk state. Without this, a restart mid-drawdown silently resets
// the peak-equity baseline and the drawdown guard stops guarding.
struct AS_RiskState
  {
   int      day_key;
   double   day_start_equity;
   double   peak_equity;
   int      consecutive_losses;
   double   daily_risk_used_pct;
   datetime updated_at;
  };

struct AS_ExposureSummary
  {
   double open_risk_pct;
   double symbol_risk_pct;
   double currency_risk_pct;
   double asset_class_risk_pct;
   string dominant_currency;
   int    open_positions;
   // Positions whose worst case cannot be computed (no stop, or an unpriceable
   // symbol). These are NOT zero-risk. While any exist, the measured
   // percentages are lower bounds and no new risk may be admitted.
   int    unbounded_positions;
   string unbounded_symbols;
  };
