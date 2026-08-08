#pragma once
#include "Enums.mqh"

struct AS_SymbolSnapshot {
   string requested_symbol; string symbol; double bid; double ask; double point; int digits;
   double spread_points; double spread_ratio; datetime tick_time;
   ENUM_AS_SPREAD_STATE spread_state; ENUM_AS_DATA_STATE data_state;
};

struct AS_SymbolSpec {
   string symbol; int digits; double point; double tick_size; double tick_value;
   double volume_min; double volume_max; double volume_step; long trade_mode;
   int stops_level; int freeze_level; bool ready;
};

struct AS_TrendResult {
   ENUM_TIMEFRAMES timeframe; double direction_score; double strength; ENUM_AS_TREND_CLASS trend_class;
   double ema50; double ema200; double adx; double atr; double atr_ratio;
   datetime available_information_time; bool valid;
};

struct AS_Zone {
   string id; ENUM_TIMEFRAMES timeframe; double low; double high; double center; int touches; double quality;
   datetime pivot_time; datetime confirmation_time; bool broken; bool valid;
};

struct AS_SignalCandidate {
   string signal_id; string symbol; ENUM_AS_DIRECTION direction; ENUM_AS_SETUP_TYPE setup;
   double entry_low; double entry_high; double preferred_entry; double stop_loss; double take_profit;
   double nearest_support; double nearest_resistance;
   double long_score; double short_score; bool has_historical_estimate; double historical_win_rate;
   int sample_size; double confidence_low; double confidence_high; datetime confirmation_bar_time;
   datetime creation_time; datetime expires_at; string rule_version; string scoring_version;
   string parameter_hash; string reasons; bool hard_blocked; string validation_codes;
};

struct AS_TradePlan {
   string plan_id; string symbol; ENUM_AS_DIRECTION direction; double entry; double stop_loss; double take_profit;
   double risk_percent; double risk_amount; double actual_risk_amount; double lot_size; double margin_required;
   double preview_bid; double preview_ask; datetime created_at; datetime expires_at;
   double max_drift_points; double minimum_rr; string validation_codes; bool valid;
};
