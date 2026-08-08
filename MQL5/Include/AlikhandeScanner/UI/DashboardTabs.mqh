//+------------------------------------------------------------------+
//| DashboardTabs.mqh                                                 |
//| Multi-tab control panel, replacing UI/Dashboard.mqh.               |
//|                                                                    |
//| Built from native chart objects (OBJ_RECTANGLE_LABEL / OBJ_BUTTON |
//| / OBJ_LABEL), not CCanvas bitmap rendering — the EA's processing  |
//| budget is 20ms per timer slice (Core/Config.mqh), and per-object  |
//| property updates are far cheaper than redrawing a bitmap on every |
//| refresh. Tabs: Overview / Detail / Risk / News / Health.          |
//| See docs/ARCHITECTURE_V1.2.md section 7.                          |
//+------------------------------------------------------------------+
#property strict

#define DASH_PREFIX "Alikhande_Dash_"

enum ENUM_DASH_TAB
  {
   DASH_TAB_OVERVIEW = 0,
   DASH_TAB_DETAIL   = 1,
   DASH_TAB_RISK     = 2,
   DASH_TAB_NEWS     = 3,
   DASH_TAB_HEALTH   = 4,
   DASH_TAB_COUNT    = 5
  };

// Dark, high-contrast palette — legible over any chart background since the
// panel paints its own opaque backing rectangle first.
#define DASH_COLOR_BG        C'18,18,22'
#define DASH_COLOR_PANEL     C'26,27,33'
#define DASH_COLOR_BORDER    C'46,48,56'
#define DASH_COLOR_TEXT      C'230,232,236'
#define DASH_COLOR_MUTED     C'150,154,163'
#define DASH_COLOR_ACCENT    C'64,156,255'
#define DASH_COLOR_GOOD      C'56,193,114'
#define DASH_COLOR_WARN      C'240,177,50'
#define DASH_COLOR_BAD       C'232,86,86'
#define DASH_COLOR_TAB_OFF   C'34,36,43'
#define DASH_COLOR_TAB_ON    DASH_COLOR_ACCENT

int    g_DashX = 20;
int    g_DashY = 40;
int    g_DashWidth = 640;
int    g_DashHeight = 420;
int    g_DashTabHeight = 30;
ENUM_DASH_TAB g_DashActiveTab = DASH_TAB_OVERVIEW;

string DashTabLabel(const ENUM_DASH_TAB t)
  {
   switch(t)
     {
      case DASH_TAB_OVERVIEW: return "Overview";
      case DASH_TAB_DETAIL:   return "Detail";
      case DASH_TAB_RISK:     return "Risk";
      case DASH_TAB_NEWS:     return "News";
      case DASH_TAB_HEALTH:   return "Health";
     }
   return "?";
  }

string DashTabButtonName(const ENUM_DASH_TAB t)
  {
   return DASH_PREFIX + "tab_" + IntegerToString((int)t);
  }

string DashContentName(const ENUM_DASH_TAB t, const string field)
  {
   return StringFormat("%scontent_%d_%s", DASH_PREFIX, (int)t, field);
  }

//+------------------------------------------------------------------+
//| Low-level object helpers                                          |
//+------------------------------------------------------------------+
void DashCreateRect(const string name, const int x, const int y, const int w, const int h,
                     const color bg, const color border)
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, h);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, bg);
   ObjectSetInteger(0, name, OBJPROP_COLOR, border);
   ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_BACK, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
  }

void DashCreateLabel(const string name, const int x, const int y, const string text,
                      const color clr, const int fontSize = 9, const string font = "Segoe UI")
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetString(0, name, OBJPROP_FONT, font);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, fontSize);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
  }

void DashCreateButton(const string name, const int x, const int y, const int w, const int h,
                       const string text, const bool active)
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, h);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, active ? DASH_COLOR_TAB_ON : DASH_COLOR_TAB_OFF);
   ObjectSetInteger(0, name, OBJPROP_COLOR, active ? clrWhite : DASH_COLOR_MUTED);
   ObjectSetInteger(0, name, OBJPROP_BORDER_COLOR, DASH_COLOR_BORDER);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_STATE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
  }

//+------------------------------------------------------------------+
//| Build the panel shell + tab strip once. Content rows are created  |
//| lazily by each tab's Update function so unused tabs cost nothing. |
//+------------------------------------------------------------------+
void DashboardCreate()
  {
   DashCreateRect(DASH_PREFIX + "bg", g_DashX, g_DashY, g_DashWidth, g_DashHeight,
                  DASH_COLOR_BG, DASH_COLOR_BORDER);
   DashCreateRect(DASH_PREFIX + "header", g_DashX, g_DashY, g_DashWidth, g_DashTabHeight,
                  DASH_COLOR_PANEL, DASH_COLOR_BORDER);

   int tabW = g_DashWidth / DASH_TAB_COUNT;
   for(int i = 0; i < DASH_TAB_COUNT; i++)
     {
      ENUM_DASH_TAB t = (ENUM_DASH_TAB)i;
      DashCreateButton(DashTabButtonName(t), g_DashX + i * tabW, g_DashY, tabW, g_DashTabHeight,
                       DashTabLabel(t), t == g_DashActiveTab);
     }

   ChartRedraw(0);
  }

void DashboardDestroy()
  {
   ObjectsDeleteAll(0, DASH_PREFIX);
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Tab switching — toggles button styling and content visibility.    |
//| Each tab's content objects live under a per-tab name prefix so    |
//| show/hide is a single ObjectSetInteger sweep, not a rebuild.      |
//+------------------------------------------------------------------+
void DashboardSwitchTab(const ENUM_DASH_TAB newTab)
  {
   g_DashActiveTab = newTab;

   for(int i = 0; i < DASH_TAB_COUNT; i++)
     {
      ENUM_DASH_TAB t = (ENUM_DASH_TAB)i;
      bool active = (t == newTab);
      string btn = DashTabButtonName(t);
      ObjectSetInteger(0, btn, OBJPROP_BGCOLOR, active ? DASH_COLOR_TAB_ON : DASH_COLOR_TAB_OFF);
      ObjectSetInteger(0, btn, OBJPROP_COLOR, active ? clrWhite : DASH_COLOR_MUTED);
      ObjectSetInteger(0, btn, OBJPROP_STATE, false);
     }

   int total = ObjectsTotal(0, 0, -1);
   for(int i = total - 1; i >= 0; i--)
     {
      string name = ObjectName(0, i, 0, -1);
      if(StringFind(name, DASH_PREFIX + "content_") != 0)
         continue;
      // content_<tabIndex>_<field>
      int tabIndex = (int)StringToInteger(StringSubstr(name, StringLen(DASH_PREFIX) + 8, 1));
      bool visible = (tabIndex == (int)newTab);
      ObjectSetInteger(0, name, OBJPROP_TIMEFRAMES, visible ? OBJ_ALL_PERIODS : OBJ_NO_PERIODS);
     }

   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Call from OnChartEvent(CHARTEVENT_OBJECT_CLICK, ...). Returns     |
//| true if the click was consumed by the dashboard.                  |
//+------------------------------------------------------------------+
bool DashboardHandleClick(const string clickedObject)
  {
   for(int i = 0; i < DASH_TAB_COUNT; i++)
     {
      ENUM_DASH_TAB t = (ENUM_DASH_TAB)i;
      if(clickedObject == DashTabButtonName(t))
        {
         DashboardSwitchTab(t);
         return true;
        }
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Overview tab: one row per symbol. Explainability lives on Detail  |
//| (score breakdown + block reasons), not here — Overview stays a    |
//| scan-friendly summary, per the "kill the Excel dashboard" rule.   |
//+------------------------------------------------------------------+
void DashboardUpdateOverviewRow(const int rowIndex, const string symbol, const string regime,
                                 const string bias, const string setup, const double longScore,
                                 const double shortScore, const string spreadLabel,
                                 const string newsLabel, const string status, const color statusColor)
  {
   int y = g_DashY + g_DashTabHeight + 8 + rowIndex * 20;
   int x = g_DashX + 10;
   int colW = 90;

   string cols[9];
   cols[0] = symbol; cols[1] = regime; cols[2] = bias; cols[3] = setup;
   cols[4] = StringFormat("%.0f", longScore); cols[5] = StringFormat("%.0f", shortScore);
   cols[6] = spreadLabel; cols[7] = newsLabel; cols[8] = status;

   for(int c = 0; c < 9; c++)
     {
      string name = DashContentName(DASH_TAB_OVERVIEW, StringFormat("r%d_c%d", rowIndex, c));
      color clr = (c == 8) ? statusColor : DASH_COLOR_TEXT;
      DashCreateLabel(name, x + c * colW, y, cols[c], clr, 8);
     }
  }

//+------------------------------------------------------------------+
//| Detail tab: MTF state, S/R, entry/SL/TP, explainability, blocks.  |
//| explanationLines is a pre-formatted "+18 H4 trend" style list;    |
//| blockLines is empty when the signal is tradable.                  |
//+------------------------------------------------------------------+
void DashboardUpdateDetail(const string symbol, const string h4, const string h1,
                            const string m15, const string m5, const double support,
                            const double resistance, const double entry, const double sl,
                            const double tp, const string &explanationLines[],
                            const string &blockLines[])
  {
   int x = g_DashX + 10;
   int y = g_DashY + g_DashTabHeight + 10;
   int lineH = 18;
   int row = 0;

   DashCreateLabel(DashContentName(DASH_TAB_DETAIL, "title"), x, y + lineH * row++,
                   symbol + " — Detail", DASH_COLOR_ACCENT, 11);
   DashCreateLabel(DashContentName(DASH_TAB_DETAIL, "mtf"), x, y + lineH * row++,
                   StringFormat("H4 %s   H1 %s   M15 %s   M5 %s", h4, h1, m15, m5),
                   DASH_COLOR_TEXT, 9);
   DashCreateLabel(DashContentName(DASH_TAB_DETAIL, "sr"), x, y + lineH * row++,
                   StringFormat("Support %.5f   Resistance %.5f", support, resistance),
                   DASH_COLOR_MUTED, 9);
   DashCreateLabel(DashContentName(DASH_TAB_DETAIL, "etp"), x, y + lineH * row++,
                   StringFormat("Entry %.5f   SL %.5f   TP %.5f", entry, sl, tp),
                   DASH_COLOR_TEXT, 9);

   row++;
   DashCreateLabel(DashContentName(DASH_TAB_DETAIL, "reasons_hdr"), x, y + lineH * row++,
                   "Reasons:", DASH_COLOR_MUTED, 9);
   for(int i = 0; i < ArraySize(explanationLines); i++)
      DashCreateLabel(DashContentName(DASH_TAB_DETAIL, StringFormat("reason_%d", i)),
                      x + 10, y + lineH * row++, explanationLines[i], DASH_COLOR_GOOD, 9);

   row++;
   if(ArraySize(blockLines) > 0)
     {
      DashCreateLabel(DashContentName(DASH_TAB_DETAIL, "blocks_hdr"), x, y + lineH * row++,
                      "Blocked:", DASH_COLOR_BAD, 9);
      for(int i = 0; i < ArraySize(blockLines); i++)
         DashCreateLabel(DashContentName(DASH_TAB_DETAIL, StringFormat("block_%d", i)),
                         x + 10, y + lineH * row++, blockLines[i], DASH_COLOR_BAD, 9);
     }
   else
     {
      DashCreateLabel(DashContentName(DASH_TAB_DETAIL, "blocks_hdr"), x, y + lineH * row++,
                      "No blocks — tradable", DASH_COLOR_GOOD, 9);
     }
  }

//+------------------------------------------------------------------+
//| Risk tab                                                           |
//+------------------------------------------------------------------+
void DashboardUpdateRisk(const double tradeRiskPct, const double openRiskPct,
                          const double currencyRiskPct, const string currencyLabel,
                          const double dailyUsedPct, const double dailyBudgetPct)
  {
   int x = g_DashX + 10;
   int y = g_DashY + g_DashTabHeight + 10;
   int lineH = 20;
   int row = 0;

   DashCreateLabel(DashContentName(DASH_TAB_RISK, "trade"), x, y + lineH * row++,
                   StringFormat("Trade Risk        %.2f%%", tradeRiskPct), DASH_COLOR_TEXT, 10);
   DashCreateLabel(DashContentName(DASH_TAB_RISK, "open"), x, y + lineH * row++,
                   StringFormat("Open Risk         %.2f%%", openRiskPct), DASH_COLOR_TEXT, 10);
   DashCreateLabel(DashContentName(DASH_TAB_RISK, "ccy"), x, y + lineH * row++,
                   StringFormat("%s Exposure    %.2f%%", currencyLabel, currencyRiskPct),
                   DASH_COLOR_TEXT, 10);
   color dailyColor = (dailyUsedPct >= dailyBudgetPct) ? DASH_COLOR_BAD : DASH_COLOR_GOOD;
   DashCreateLabel(DashContentName(DASH_TAB_RISK, "daily"), x, y + lineH * row++,
                   StringFormat("Daily Budget      %.2f%% / %.2f%%", dailyUsedPct, dailyBudgetPct),
                   dailyColor, 10);
  }

//+------------------------------------------------------------------+
//| News tab                                                            |
//+------------------------------------------------------------------+
void DashboardUpdateNewsRow(const int rowIndex, const string symbol, const string severityLabel,
                             const color severityColor, const string nextEventLabel)
  {
   int y = g_DashY + g_DashTabHeight + 10 + rowIndex * 20;
   int x = g_DashX + 10;

   DashCreateLabel(DashContentName(DASH_TAB_NEWS, StringFormat("sym_%d", rowIndex)),
                   x, y, symbol, DASH_COLOR_TEXT, 9);
   DashCreateLabel(DashContentName(DASH_TAB_NEWS, StringFormat("sev_%d", rowIndex)),
                   x + 100, y, severityLabel, severityColor, 9);
   DashCreateLabel(DashContentName(DASH_TAB_NEWS, StringFormat("evt_%d", rowIndex)),
                   x + 220, y, nextEventLabel, DASH_COLOR_MUTED, 9);
  }

//+------------------------------------------------------------------+
//| Health tab                                                         |
//+------------------------------------------------------------------+
void DashboardUpdateHealth(const bool restartRecoveryPending, const datetime lastTick,
                            const double cpuBudgetUsedMs, const double cpuBudgetMs,
                            const int dbWriteFailures, const int dedupBlocks)
  {
   int x = g_DashX + 10;
   int y = g_DashY + g_DashTabHeight + 10;
   int lineH = 20;
   int row = 0;

   color restartColor = restartRecoveryPending ? DASH_COLOR_WARN : DASH_COLOR_GOOD;
   DashCreateLabel(DashContentName(DASH_TAB_HEALTH, "restart"), x, y + lineH * row++,
                   restartRecoveryPending ? "Restart recovery: PENDING" : "Restart recovery: clean",
                   restartColor, 10);

   int ageSec = (int)(TimeCurrent() - lastTick);
   color tickColor = (ageSec > 30) ? DASH_COLOR_BAD : DASH_COLOR_GOOD;
   DashCreateLabel(DashContentName(DASH_TAB_HEALTH, "tick"), x, y + lineH * row++,
                   StringFormat("Last tick age: %ds", ageSec), tickColor, 10);

   color cpuColor = (cpuBudgetUsedMs > cpuBudgetMs) ? DASH_COLOR_BAD : DASH_COLOR_GOOD;
   DashCreateLabel(DashContentName(DASH_TAB_HEALTH, "cpu"), x, y + lineH * row++,
                   StringFormat("CPU budget: %.1fms / %.1fms", cpuBudgetUsedMs, cpuBudgetMs),
                   cpuColor, 10);

   DashCreateLabel(DashContentName(DASH_TAB_HEALTH, "dbfail"), x, y + lineH * row++,
                   StringFormat("DB write failures: %d", dbWriteFailures),
                   dbWriteFailures > 0 ? DASH_COLOR_WARN : DASH_COLOR_GOOD, 10);

   DashCreateLabel(DashContentName(DASH_TAB_HEALTH, "dedup"), x, y + lineH * row++,
                   StringFormat("Alert dedup blocks: %d", dedupBlocks), DASH_COLOR_MUTED, 10);
  }
