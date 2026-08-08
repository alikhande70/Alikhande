#pragma once
#include "../Core/VersionInfo.mqh"
#include "../Domain/Models.mqh"

class AS_Dashboard {
private:
   string m_prefix;
   int m_row_h;
   ENUM_AS_TAB m_tab;

   void Label(const string name,const string text,const int x,const int y,const color c,const int size=9){
      string n=m_prefix+name;
      if(ObjectFind(0,n)<0)ObjectCreate(0,n,OBJ_LABEL,0,0,0);
      ObjectSetInteger(0,n,OBJPROP_XDISTANCE,x);ObjectSetInteger(0,n,OBJPROP_YDISTANCE,y);
      ObjectSetInteger(0,n,OBJPROP_COLOR,c);ObjectSetInteger(0,n,OBJPROP_FONTSIZE,size);
      ObjectSetString(0,n,OBJPROP_TEXT,text);ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);
   }

   void Button(const string name,const string text,const int x,const int y,const int w,const int h,const bool active=false){
      string n=m_prefix+name;
      if(ObjectFind(0,n)<0)ObjectCreate(0,n,OBJ_BUTTON,0,0,0);
      ObjectSetInteger(0,n,OBJPROP_XDISTANCE,x);ObjectSetInteger(0,n,OBJPROP_YDISTANCE,y);
      ObjectSetInteger(0,n,OBJPROP_XSIZE,w);ObjectSetInteger(0,n,OBJPROP_YSIZE,h);
      ObjectSetInteger(0,n,OBJPROP_BGCOLOR,active?C'45,89,120':C'32,36,43');
      ObjectSetInteger(0,n,OBJPROP_COLOR,clrWhite);ObjectSetString(0,n,OBJPROP_TEXT,text);
   }

   string TabName(ENUM_AS_TAB t){
      if(t==AS_TAB_OVERVIEW)return "Overview";
      if(t==AS_TAB_SIGNAL)return "Signal";
      if(t==AS_TAB_RISK)return "Risk";
      if(t==AS_TAB_HISTORY)return "History";
      if(t==AS_TAB_STATS)return "Stats";
      if(t==AS_TAB_SETTINGS)return "Settings";
      return "System";
   }
public:
   AS_Dashboard(void){m_prefix="ALKSCN_";m_row_h=22;m_tab=AS_TAB_OVERVIEW;}
   void Clear(){ObjectsDeleteAll(0,m_prefix);}
   ENUM_AS_TAB Tab()const{return m_tab;}

   void Build(){
      Clear();
      Label("TITLE",AS_PRODUCT_NAME+"  "+AS_VERSION,12,10,clrWhite,11);
      int x=12;
      for(int i=0;i<=AS_TAB_SYSTEM;i++){
         ENUM_AS_TAB t=(ENUM_AS_TAB)i;
         Button("TAB_"+IntegerToString(i),TabName(t),x,32,76,20,t==m_tab);x+=80;
      }
      if(m_tab==AS_TAB_OVERVIEW)Header();
   }

   void Header(){Label("H0","Symbol       Spread   Regime        Bias    Setup       Long Short News   Status",12,62,clrSilver,9);}

   void Row(const int row,const string symbol,const double spread,const AS_RegimeResult &regime,const AS_SignalCandidate &s,const string news,const string status){
      if(m_tab!=AS_TAB_OVERVIEW)return;
      int y=62+(row+1)*m_row_h;
      string bias=(s.direction==AS_DIR_LONG?"LONG":(s.direction==AS_DIR_SHORT?"SHORT":"-"));
      string text=StringFormat("%-11s %7.1f %-13s %-7s %-11s %5.0f %5.0f %-6s %-12s",symbol,spread,EnumToString(regime.regime),bias,EnumToString(s.setup),s.long_score,s.short_score,news,status);
      Label("ROW_"+IntegerToString(row),text,12,y,(status=="READY"?clrLime:(status=="BLOCKED"?clrTomato:clrSilver)));
      Button("OPEN_"+symbol,"Open",760,y-2,52,18,false);Button("DETAIL_"+symbol,"Detail",816,y-2,58,18,false);
   }

   void SignalDetail(const AS_SignalCandidate &s){
      if(m_tab!=AS_TAB_SIGNAL)return;
      if(s.symbol==""){Label("SIG0","Select a symbol from Overview.",12,70,clrSilver,10);return;}
      Label("SIG1",StringFormat("%s | %s | %s",s.symbol,EnumToString(s.direction),EnumToString(s.setup)),12,70,clrWhite,11);
      Label("SIG2",StringFormat("Long %.0f | Short %.0f | Regime %s %.0f%%",s.long_score,s.short_score,EnumToString(s.regime),s.regime_confidence),12,96,clrSilver,9);
      Label("SIG3",StringFormat("Entry %.5f | SL %.5f | TP %.5f",s.preferred_entry,s.stop_loss,s.take_profit),12,120,clrSilver,9);
      Label("SIG4","Reasons: "+s.reasons,12,144,clrSilver,9);
      Label("SIG5","Blocks: "+s.validation_codes,12,168,s.hard_blocked?clrTomato:clrSilver,9);
      Label("SIG6","Historical probability: UNAVAILABLE until validated outcome sample exists",12,192,clrSilver,9);
      Label("SIG7","Parameter hash: "+s.parameter_hash+" | Broker spec: "+s.broker_spec_hash,12,216,clrSilver,8);
      Button("PREVIEW_"+s.symbol,"Build Risk Preview",12,244,140,22,false);
   }

   void RiskDetail(const AS_TradePlan &p,const string message,const bool can_execute){
      if(m_tab!=AS_TAB_RISK)return;
      if(p.symbol==""){Label("R0","No risk preview. Select a READY signal first.",12,70,clrSilver,10);return;}
      Label("R1",StringFormat("%s | Risk %.2f%% | %.2f | Lot %.2f",p.symbol,p.risk_percent,p.actual_risk_amount,p.lot_size),12,70,clrWhite,10);
      Label("R2",StringFormat("Entry %.5f | SL %.5f | TP %.5f | Margin %.2f",p.entry,p.stop_loss,p.take_profit,p.margin_required),12,96,clrSilver,9);
      Label("R3",message,12,122,can_execute?clrLime:clrTomato,9);
      Label("R4","Broker spec snapshot: "+p.broker_spec_hash,12,146,clrSilver,8);
      if(can_execute)Button("EXECUTE_"+p.symbol,"Confirm DEMO Order",12,176,150,24,false);
   }

   void History(string &rows[]){
      if(m_tab!=AS_TAB_HISTORY)return;
      Label("HH","Recent persisted signals",12,70,clrWhite,10);
      if(ArraySize(rows)==0){Label("H_EMPTY","No persisted signal history yet.",12,96,clrSilver,9);return;}
      for(int i=0;i<ArraySize(rows);i++)Label("HROW_"+IntegerToString(i),rows[i],12,96+i*22,clrSilver,9);
   }

   void Stats(const int total,const int wins,const int losses,const double win_rate,const double avg_r,const double ci_low,const double ci_high,const int minimum_sample){
      if(m_tab!=AS_TAB_STATS)return;
      Label("ST0","Evidence statistics — terminal Shadow/Demo outcomes only",12,70,clrWhite,10);
      Label("ST1",StringFormat("Samples %d | TP %d | SL %d | Avg R %.3f",total,wins,losses,avg_r),12,98,clrSilver,9);
      if(total<minimum_sample){
         Label("ST2",StringFormat("Historical probability: UNAVAILABLE — need at least %d terminal outcomes",minimum_sample),12,124,clrTomato,9);
         Label("ST3",StringFormat("Descriptive observed win rate %.1f%% is not a calibrated probability",win_rate),12,150,clrSilver,9);
      }else{
         Label("ST2",StringFormat("Observed win rate %.1f%% | Wilson 95%% %.1f–%.1f%%",win_rate,ci_low,ci_high),12,124,clrSilver,9);
         Label("ST3","Validation/OOS/calibration gates must still pass before displaying probability in Overview.",12,150,clrTomato,9);
      }
   }

   void Settings(const string mode,const string parameter_hash,const string symbols,const double risk_pct,const double max_open_risk,const bool news_gate,const bool account_guard,const int timer_ms){
      if(m_tab!=AS_TAB_SETTINGS)return;
      Label("SET0","Effective runtime configuration (read-only in v1.2 RC)",12,70,clrWhite,10);
      Label("SET1","Mode: "+mode+" | Parameter hash: "+parameter_hash,12,98,clrSilver,9);
      Label("SET2",StringFormat("Risk/trade %.2f%% | Max scanner open risk %.2f%%",risk_pct,max_open_risk),12,124,clrSilver,9);
      Label("SET3",StringFormat("News gate %s | Account guard %s | Timer %d ms",news_gate?"ON":"OFF",account_guard?"ON":"OFF",timer_ms),12,150,clrSilver,9);
      Label("SET4","Symbols: "+symbols,12,176,clrSilver,8);
      Label("SET5","Safety-critical settings remain inputs until runtime control persistence is separately validated.",12,204,clrTomato,8);
   }

   void System(const AS_HealthSnapshot &h,const string extra){
      if(m_tab!=AS_TAB_SYSTEM)return;
      Label("SYS1",StringFormat("Health: %s | Demo: %s | DB: %s | Data: %s | Trade: %s",EnumToString(h.state),h.demo_account?"YES":"NO",h.db_ready?"READY":"FAIL",h.data_ready?"READY":"WAIT",h.trade_allowed?"ALLOWED":"BLOCKED"),12,70,h.state==AS_HEALTH_OK?clrLime:clrTomato,10);
      Label("SYS2","Reasons: "+h.reasons,12,95,clrSilver,9);
      Label("SYS3",extra,12,120,clrSilver,9);
   }

   bool ParseOpen(const string obj,string &symbol){string p=m_prefix+"OPEN_";if(StringFind(obj,p)!=0)return false;symbol=StringSubstr(obj,StringLen(p));return true;}
   bool ParseDetail(const string obj,string &symbol){string p=m_prefix+"DETAIL_";if(StringFind(obj,p)!=0)return false;symbol=StringSubstr(obj,StringLen(p));return true;}
   bool ParsePreview(const string obj,string &symbol){string p=m_prefix+"PREVIEW_";if(StringFind(obj,p)!=0)return false;symbol=StringSubstr(obj,StringLen(p));return true;}
   bool ParseExecute(const string obj,string &symbol){string p=m_prefix+"EXECUTE_";if(StringFind(obj,p)!=0)return false;symbol=StringSubstr(obj,StringLen(p));return true;}
   bool ParseTab(const string obj,ENUM_AS_TAB &tab){string p=m_prefix+"TAB_";if(StringFind(obj,p)!=0)return false;int v=(int)StringToInteger(StringSubstr(obj,StringLen(p)));if(v<0||v>AS_TAB_SYSTEM)return false;tab=(ENUM_AS_TAB)v;return true;}
   void SetTab(const ENUM_AS_TAB tab){m_tab=tab;Build();}
};
