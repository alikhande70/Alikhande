#pragma once
#include "Database.mqh"
#include "../Statistics/Statistics.mqh"
#include "../Domain/Enums.mqh"

class AS_ReadModels {
private:
   AS_Database *m_db;
public:
   AS_ReadModels(void){m_db=NULL;}
   void Attach(AS_Database &db){m_db=&db;}

   int RecentSignals(string &rows[],const int limit=8){
      ArrayResize(rows,0);
      if(m_db==NULL||!m_db.Ready()||limit<=0)return 0;
      string sql=StringFormat("SELECT symbol,direction,setup,state,long_score,short_score,created_at FROM signals ORDER BY created_at DESC LIMIT %d",limit);
      int q=DatabasePrepare(m_db.Handle(),sql);if(q==INVALID_HANDLE)return 0;
      int n=0;
      while(DatabaseRead(q)){
         string symbol="";long direction=0,setup=0,state=0,created=0;double long_score=0,short_score=0;
         DatabaseColumnText(q,0,symbol);DatabaseColumnLong(q,1,direction);DatabaseColumnLong(q,2,setup);DatabaseColumnLong(q,3,state);
         DatabaseColumnDouble(q,4,long_score);DatabaseColumnDouble(q,5,short_score);DatabaseColumnLong(q,6,created);
         ArrayResize(rows,n+1);
         rows[n]=StringFormat("%-11s %-6s %-18s L%3.0f/S%3.0f  %s",symbol,EnumToString((ENUM_AS_DIRECTION)direction),EnumToString((ENUM_AS_SIGNAL_STATE)state),long_score,short_score,TimeToString((datetime)created,TIME_DATE|TIME_MINUTES));
         n++;
      }
      DatabaseFinalize(q);return n;
   }

   bool OutcomeStats(const ENUM_AS_OUTCOME_SOURCE source,const string rule_version,const string scoring_version,const string parameter_hash,int &total,int &wins,int &losses,double &win_rate,double &avg_r,double &wilson_low,double &wilson_high){
      total=0;wins=0;losses=0;win_rate=0;avg_r=0;wilson_low=0;wilson_high=0;
      if(m_db==NULL||!m_db.Ready()||source==AS_OUTCOME_SOURCE_UNKNOWN)return false;
      int q=DatabasePrepare(m_db.Handle(),"SELECT COUNT(*),SUM(CASE WHEN state=?1 THEN 1 ELSE 0 END),SUM(CASE WHEN state=?2 THEN 1 ELSE 0 END),AVG(r_multiple) FROM outcomes WHERE state IN (?1,?2) AND evidence_source=?3 AND rule_version=?4 AND scoring_version=?5 AND parameter_hash=?6");
      if(q==INVALID_HANDLE)return false;
      bool bound=DatabaseBind(q,0,(int)AS_SIGNAL_TP)&&DatabaseBind(q,1,(int)AS_SIGNAL_SL)&&DatabaseBind(q,2,(int)source)&&DatabaseBind(q,3,rule_version)&&DatabaseBind(q,4,scoring_version)&&DatabaseBind(q,5,parameter_hash);
      if(bound&&DatabaseRead(q)){
         DatabaseColumnInteger(q,0,total);DatabaseColumnInteger(q,1,wins);DatabaseColumnInteger(q,2,losses);DatabaseColumnDouble(q,3,avg_r);
      }
      DatabaseFinalize(q);
      if(!bound)return false;
      if(total>0)win_rate=100.0*wins/total;
      AS_Statistics stats;double lo=0,hi=0;if(total>0&&stats.Wilson(wins,total,lo,hi)){wilson_low=lo*100.0;wilson_high=hi*100.0;}
      return true;
   }
};