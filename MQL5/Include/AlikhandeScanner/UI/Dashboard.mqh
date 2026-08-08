#pragma once
#include "Theme.mqh"
#include "../Domain/Models.mqh"
#include "../Core/VersionInfo.mqh"
#include "../Analysis/RegimeEngine.mqh"
#include "../Statistics/Statistics.mqh"
#include "../News/CalendarGate.mqh"

// Multi-tab control panel.
//
// Design rule: the Overview tab stays scannable and the Detail tab carries the
// depth. Putting every field on one surface turns the dashboard into a
// spreadsheet nobody reads under pressure.
//
// Built from chart objects rather than a CCanvas bitmap. The scanner runs on a
// 250 ms timer with a 20 ms processing budget; updating a handful of object
// properties comfortably fits that, whereas recompositing a bitmap every
// refresh does not.
//
// Objects are created once and thereafter only have their properties updated —
// ObjectCreate on an existing name is a no-op that still costs a lookup, and
// deleting/recreating rows per refresh is what makes MT5 panels flicker.

enum ENUM_AS_TAB
  {
   AS_TAB_OVERVIEW = 0,
   AS_TAB_DETAIL   = 1,
   AS_TAB_RISK     = 2,
   AS_TAB_HEALTH   = 3,
   AS_TAB_COUNT    = 4
  };

class AS_Dashboard
  {
private:
   string      m_prefix;
   int         m_x;
   int         m_y;
   int         m_width;
   int         m_rows;
   ENUM_AS_TAB m_active;
   string      m_selected_symbol;

   string Name(const string suffix) const { return m_prefix + suffix; }

   string TabName(const ENUM_AS_TAB tab) const
     {
      return Name("TAB_" + IntegerToString((int)tab));
     }

   string TabTitle(const ENUM_AS_TAB tab) const
     {
      switch(tab)
        {
         case AS_TAB_OVERVIEW: return "Overview";
         case AS_TAB_DETAIL:   return "Detail";
         case AS_TAB_RISK:     return "Risk";
         case AS_TAB_HEALTH:   return "Health";
        }
      return "?";
     }

   void Rect(const string name, const int x, const int y, const int w, const int h,
             const color background, const color border)
     {
      if(ObjectFind(0, name) < 0)
         ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
      ObjectSetInteger(0, name, OBJPROP_XSIZE, w);
      ObjectSetInteger(0, name, OBJPROP_YSIZE, h);
      ObjectSetInteger(0, name, OBJPROP_BGCOLOR, background);
      ObjectSetInteger(0, name, OBJPROP_COLOR, border);
      ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, name, OBJPROP_BACK, false);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }

   void Text(const string name, const int x, const int y, const string content,
             const color clr, const string font, const int size)
     {
      if(ObjectFind(0, name) < 0)
         ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
      ObjectSetString(0, name, OBJPROP_TEXT, content);
      ObjectSetString(0, name, OBJPROP_FONT, font);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, size);
      ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }

   void Button(const string name, const int x, const int y, const int w, const int h,
               const string caption, const bool active)
     {
      if(ObjectFind(0, name) < 0)
         ObjectCreate(0, name, OBJ_BUTTON, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
      ObjectSetInteger(0, name, OBJPROP_XSIZE, w);
      ObjectSetInteger(0, name, OBJPROP_YSIZE, h);
      ObjectSetString(0, name, OBJPROP_TEXT, caption);
      ObjectSetString(0, name, OBJPROP_FONT, AS_UI_FONT_UI);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, AS_UI_FONT_SIZE_HEAD);
      ObjectSetInteger(0, name, OBJPROP_BGCOLOR, active ? AS_UI_COLOR_ACCENT : AS_UI_COLOR_TAB_OFF);
      ObjectSetInteger(0, name, OBJPROP_COLOR, active ? clrWhite : AS_UI_COLOR_MUTED);
      ObjectSetInteger(0, name, OBJPROP_BORDER_COLOR, AS_UI_COLOR_BORDER);
      // Buttons latch when clicked; the panel is stateless so it is reset
      // immediately, otherwise the tab stays visually depressed.
      ObjectSetInteger(0, name, OBJPROP_STATE, false);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }

   void Hide(const string name)
     {
      if(ObjectFind(0, name) >= 0)
         ObjectSetInteger(0, name, OBJPROP_TIMEFRAMES, OBJ_NO_PERIODS);
     }

   void Show(const string name)
     {
      if(ObjectFind(0, name) >= 0)
         ObjectSetInteger(0, name, OBJPROP_TIMEFRAMES, OBJ_ALL_PERIODS);
     }

   int BodyTop(void) const { return m_y + AS_UI_HEADER_HEIGHT + AS_UI_TAB_HEIGHT; }

   color DirectionColor(const ENUM_AS_DIRECTION direction) const
     {
      if(direction == AS_DIR_LONG)  return AS_UI_COLOR_LONG;
      if(direction == AS_DIR_SHORT) return AS_UI_COLOR_SHORT;
      return AS_UI_COLOR_MUTED;
     }

public:
   AS_Dashboard(void)
     {
      m_prefix = "ALKSCN_";
      m_x = 12;
      m_y = 18;
      m_width = 720;
      m_rows = 0;
      m_active = AS_TAB_OVERVIEW;
      m_selected_symbol = "";
     }

   ENUM_AS_TAB ActiveTab(void) const { return m_active; }
   string SelectedSymbol(void) const { return m_selected_symbol; }

   void Create(const int symbol_count)
     {
      m_rows = symbol_count;
      const int height = AS_UI_HEADER_HEIGHT + AS_UI_TAB_HEIGHT
                         + (MathMax(symbol_count, 6) + 2) * AS_UI_ROW_HEIGHT + AS_UI_PADDING * 2;

      Rect(Name("BG"), m_x, m_y, m_width, height, AS_UI_COLOR_PANEL, AS_UI_COLOR_BORDER);
      Rect(Name("HEAD"), m_x, m_y, m_width, AS_UI_HEADER_HEIGHT,
           AS_UI_COLOR_HEADER, AS_UI_COLOR_BORDER);
      Text(Name("TITLE"), m_x + AS_UI_PADDING, m_y + 6,
           StringFormat("Alikhande Scanner  v%s  %s", AS_VERSION, AS_EDITION),
           AS_UI_COLOR_TEXT, AS_UI_FONT_UI, AS_UI_FONT_SIZE_TITLE);
      Text(Name("MODE"), m_x + m_width - 190, m_y + 6, "",
           AS_UI_COLOR_WARN, AS_UI_FONT_UI, AS_UI_FONT_SIZE_HEAD);

      const int tab_width = (m_width - AS_UI_PADDING * 2) / AS_TAB_COUNT;
      for(int i = 0; i < AS_TAB_COUNT; i++)
        {
         const ENUM_AS_TAB tab = (ENUM_AS_TAB)i;
         Button(TabName(tab), m_x + AS_UI_PADDING + i * tab_width,
                m_y + AS_UI_HEADER_HEIGHT, tab_width - 2, AS_UI_TAB_HEIGHT - 2,
                TabTitle(tab), tab == m_active);
        }

      Text(Name("COLS"), m_x + AS_UI_PADDING, BodyTop() + 2,
           "SYMBOL        REGIME    BIAS   SETUP        LONG SHORT  SPREAD  STATUS",
           AS_UI_COLOR_MUTED, AS_UI_FONT_MONO, AS_UI_FONT_SIZE_ROW);

      // One selection button per row, right-aligned inside the panel so it
      // stays reachable regardless of window width.
      for(int i = 0; i < symbol_count; i++)
         Button(Name("SEL_" + IntegerToString(i)),
                m_x + m_width - 62, BodyTop() + (i + 1) * AS_UI_ROW_HEIGHT + 2,
                52, AS_UI_ROW_HEIGHT - 3, "Chart", false);

      SwitchTab(m_active);
      ChartRedraw(0);
     }

   void Destroy(void)
     {
      ObjectsDeleteAll(0, m_prefix);
      ChartRedraw(0);
     }

   void SetMode(const string mode_text, const bool warn)
     {
      Text(Name("MODE"), m_x + m_width - 190, m_y + 6, mode_text,
           warn ? AS_UI_COLOR_WARN : AS_UI_COLOR_MUTED, AS_UI_FONT_UI, AS_UI_FONT_SIZE_HEAD);
     }

   void SwitchTab(const ENUM_AS_TAB tab)
     {
      m_active = tab;
      for(int i = 0; i < AS_TAB_COUNT; i++)
        {
         const ENUM_AS_TAB current = (ENUM_AS_TAB)i;
         const bool active = (current == tab);
         const string name = TabName(current);
         ObjectSetInteger(0, name, OBJPROP_BGCOLOR, active ? AS_UI_COLOR_ACCENT : AS_UI_COLOR_TAB_OFF);
         ObjectSetInteger(0, name, OBJPROP_COLOR, active ? clrWhite : AS_UI_COLOR_MUTED);
         ObjectSetInteger(0, name, OBJPROP_STATE, false);
        }

      // Overview owns the row grid and its per-row buttons; the other tabs
      // draw into a free-form body area.
      const bool overview = (tab == AS_TAB_OVERVIEW);
      if(overview) Show(Name("COLS")); else Hide(Name("COLS"));
      for(int i = 0; i < m_rows; i++)
        {
         const string row = Name("ROW_" + IntegerToString(i));
         const string sel = Name("SEL_" + IntegerToString(i));
         if(overview) { Show(row); Show(sel); }
         else         { Hide(row); Hide(sel); }
        }

      const int body_lines = 14;
      for(int i = 0; i < body_lines; i++)
        {
         const string line = Name("BODY_" + IntegerToString(i));
         if(overview) Hide(line); else Show(line);
        }

      ChartRedraw(0);
     }

   // ------------------------------------------------------------- overview

   void Row(const int index, const string symbol, const ENUM_AS_REGIME regime,
            const ENUM_AS_DIRECTION direction, const string setup,
            const double long_score, const double short_score,
            const double spread_points, const string status)
     {
      const string text = StringFormat("%-13s %-9s %-6s %-12s %4.0f %5.0f %7.1f  %s",
                                       StringSubstr(symbol, 0, 13),
                                       AS_RegimeName(regime),
                                       (direction == AS_DIR_LONG ? "LONG"
                                        : (direction == AS_DIR_SHORT ? "SHORT" : "-")),
                                       StringSubstr(setup, 0, 12),
                                       long_score, short_score, spread_points, status);
      Text(Name("ROW_" + IntegerToString(index)), m_x + AS_UI_PADDING,
           BodyTop() + (index + 1) * AS_UI_ROW_HEIGHT,
           text, DirectionColor(direction), AS_UI_FONT_MONO, AS_UI_FONT_SIZE_ROW);
     }

   // ---------------------------------------------------------------- body

   void BodyLine(const int line, const string text, const color clr)
     {
      Text(Name("BODY_" + IntegerToString(line)), m_x + AS_UI_PADDING,
           BodyTop() + line * AS_UI_ROW_HEIGHT + 2, text, clr,
           AS_UI_FONT_MONO, AS_UI_FONT_SIZE_ROW);
     }

   void ClearBody(void)
     {
      for(int i = 0; i < 14; i++)
         BodyLine(i, "", AS_UI_COLOR_TEXT);
     }

   // Detail view. Shows the score breakdown and the block reasons, because a
   // bare "84" is unactionable and undebuggable — the operator needs to know
   // which conditions produced it and what, if anything, is vetoing the trade.
   void RenderDetail(const AS_SignalCandidate &s, const AS_RegimeResult &regime,
                     const string h4, const string h1, const string m15, const string m5,
                     const AS_NewsVerdict &news)
     {
      ClearBody();
      if(s.symbol == "")
        {
         BodyLine(0, "Select a symbol on the Overview tab.", AS_UI_COLOR_MUTED);
         return;
        }

      int line = 0;
      BodyLine(line++, StringFormat("%s   %s   confidence %.0f%%",
                                    s.symbol, AS_RegimeName(regime.regime), regime.confidence),
               AS_UI_COLOR_ACCENT);
      BodyLine(line++, StringFormat("H4 %-9s H1 %-9s M15 %-9s M5 %-9s", h4, h1, m15, m5),
               AS_UI_COLOR_TEXT);
      BodyLine(line++, "", AS_UI_COLOR_TEXT);
      BodyLine(line++, StringFormat("Support %-12.5f  Resistance %.5f",
                                    s.nearest_support, s.nearest_resistance), AS_UI_COLOR_MUTED);
      BodyLine(line++, StringFormat("Entry %-14.5f  Stop %-14.5f  Target %.5f",
                                    s.preferred_entry, s.stop_loss, s.take_profit),
               DirectionColor(s.direction));
      BodyLine(line++, "", AS_UI_COLOR_TEXT);

      BodyLine(line++, StringFormat("Rule score   long %.0f / short %.0f",
                                    s.long_score, s.short_score), AS_UI_COLOR_TEXT);
      // Stated explicitly on screen, every time. The number above is a weighted
      // sum of conditions, not an estimated probability, and the two must never
      // be read as the same quantity.
      BodyLine(line++, "  (rule score is not a probability)", AS_UI_COLOR_MUTED);
      BodyLine(line++, "Historical   " + AS_FormatProbability(s), AS_UI_COLOR_MUTED);
      BodyLine(line++, "", AS_UI_COLOR_TEXT);

      // State and source are shown together, always. "CLEAR" from a live
      // calendar and "UNKNOWN" from no calendar are completely different
      // claims, and a panel that renders both as a quiet green tick is lying.
      color news_colour = AS_UI_COLOR_LONG;
      if(news.state == AS_NEWS_BLOCKED)      news_colour = AS_UI_COLOR_SHORT;
      else if(news.state == AS_NEWS_UNKNOWN) news_colour = AS_UI_COLOR_WARN;
      BodyLine(line++, StringFormat("News     %s via %s%s",
                                    AS_NewsStateName(news.state),
                                    AS_NewsSourceName(news.source),
                                    news.reason == "" ? "" : "  (" + news.reason + ")"),
               news_colour);
      BodyLine(line++, "", AS_UI_COLOR_TEXT);

      BodyLine(line++, "Reasons  " + (s.reasons == "" ? "-" : s.reasons), AS_UI_COLOR_LONG);
      BodyLine(line++, "Blocks   " + (s.validation_codes == "" ? "none" : s.validation_codes),
               s.validation_codes == "" ? AS_UI_COLOR_MUTED : AS_UI_COLOR_SHORT);
     }

   void RenderRisk(const AS_ExposureSummary &exposure, const AS_RiskState &risk,
                   const double per_trade_pct, const string guard_codes)
     {
      ClearBody();
      int line = 0;
      BodyLine(line++, "Exposure", AS_UI_COLOR_ACCENT);
      BodyLine(line++, StringFormat("  open positions      %d", exposure.open_positions),
               AS_UI_COLOR_TEXT);
      BodyLine(line++, StringFormat("  per-trade risk      %.2f%%", per_trade_pct), AS_UI_COLOR_TEXT);
      BodyLine(line++, StringFormat("  open risk           %.2f%%", exposure.open_risk_pct),
               AS_UI_COLOR_TEXT);
      BodyLine(line++, StringFormat("  %-3s exposure        %.2f%%",
                                    exposure.dominant_currency == "" ? "ccy" : exposure.dominant_currency,
                                    exposure.currency_risk_pct), AS_UI_COLOR_TEXT);
      BodyLine(line++, StringFormat("  asset-class risk    %.2f%%", exposure.asset_class_risk_pct),
               AS_UI_COLOR_TEXT);
      if(exposure.unbounded_positions > 0)
        {
         // Stated loudly: while this is non-zero every percentage above is a
         // lower bound, not a measurement.
         BodyLine(line++, StringFormat("  UNBOUNDED           %d position(s): %s",
                                       exposure.unbounded_positions,
                                       exposure.unbounded_symbols), AS_UI_COLOR_SHORT);
         BodyLine(line++, "  (figures above are lower bounds; new risk blocked)",
                  AS_UI_COLOR_SHORT);
        }
      BodyLine(line++, "", AS_UI_COLOR_TEXT);
      BodyLine(line++, "Account guards", AS_UI_COLOR_ACCENT);
      BodyLine(line++, StringFormat("  peak equity         %.2f", risk.peak_equity), AS_UI_COLOR_TEXT);
      BodyLine(line++, StringFormat("  day start equity    %.2f", risk.day_start_equity),
               AS_UI_COLOR_TEXT);
      BodyLine(line++, StringFormat("  consecutive losses  %d", risk.consecutive_losses),
               risk.consecutive_losses > 0 ? AS_UI_COLOR_WARN : AS_UI_COLOR_TEXT);
      BodyLine(line++, "  status              " + (guard_codes == "" ? "ok" : guard_codes),
               guard_codes == "" ? AS_UI_COLOR_LONG : AS_UI_COLOR_SHORT);
     }

   void RenderHealth(const int symbols_total, const int symbols_unresolved,
                     const double last_slice_ms, const double budget_ms,
                     const int indicator_handles, const bool database_open,
                     const string execution_state, const int suppressed_logs,
                     const string runtime_kind, const bool is_production,
                     const string persistence_target)
     {
      ClearBody();
      int line = 0;
      BodyLine(line++, "Runtime", AS_UI_COLOR_ACCENT);
      // Whether this run's records count as evidence is the first thing an
      // operator needs to know when reading anything else on this panel.
      BodyLine(line++, StringFormat("  context             %s%s", runtime_kind,
                                    is_production ? "" : "  (NOT production history)"),
               is_production ? AS_UI_COLOR_LONG : AS_UI_COLOR_WARN);
      BodyLine(line++, StringFormat("  symbols             %d (%d unresolved)",
                                    symbols_total, symbols_unresolved),
               symbols_unresolved > 0 ? AS_UI_COLOR_WARN : AS_UI_COLOR_TEXT);
      BodyLine(line++, StringFormat("  last slice          %.1f ms / %.0f ms budget",
                                    last_slice_ms, budget_ms),
               last_slice_ms > budget_ms ? AS_UI_COLOR_SHORT : AS_UI_COLOR_LONG);
      BodyLine(line++, StringFormat("  indicator handles   %d", indicator_handles),
               AS_UI_COLOR_TEXT);
      BodyLine(line++, "", AS_UI_COLOR_TEXT);
      BodyLine(line++, "Persistence", AS_UI_COLOR_ACCENT);
      BodyLine(line++, "  database            " + (database_open ? "open" : "CLOSED"),
               database_open ? AS_UI_COLOR_LONG : AS_UI_COLOR_SHORT);
      BodyLine(line++, "  target              " + persistence_target, AS_UI_COLOR_MUTED);
      BodyLine(line++, "  execution           " + execution_state, AS_UI_COLOR_TEXT);
      BodyLine(line++, StringFormat("  suppressed logs     %d", suppressed_logs),
               AS_UI_COLOR_MUTED);
     }

   // --------------------------------------------------------------- events

   // Returns true when the click belonged to the dashboard. `row_index` is set
   // to the selected row when a row button was clicked, otherwise -1.
   bool HandleClick(const string object_name, int &row_index)
     {
      row_index = -1;

      for(int i = 0; i < AS_TAB_COUNT; i++)
        {
         if(object_name != TabName((ENUM_AS_TAB)i))
            continue;
         SwitchTab((ENUM_AS_TAB)i);
         return true;
        }

      const string selection_prefix = Name("SEL_");
      if(StringFind(object_name, selection_prefix) == 0)
        {
         row_index = (int)StringToInteger(StringSubstr(object_name, StringLen(selection_prefix)));
         ObjectSetInteger(0, object_name, OBJPROP_STATE, false);
         return true;
        }

      return false;
     }

   void SetSelectedSymbol(const string symbol) { m_selected_symbol = symbol; }
  };
