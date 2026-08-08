#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"

struct AS_ReconcileResultV13
  {
   ENUM_AS_EXEC_STATE state;
   ulong position_id;
   double entry_volume;
   double exit_volume;
   bool terminal;
   string reason;
  };

class AS_ReconcilerV13
  {
public:
   bool Rebuild(const AS_ExecutionRecord &current,const ulong magic,AS_ReconcileResultV13 &out) const
     {
      ZeroMemory(out);
      out.state=AS_EXEC_UNKNOWN;
      if(current.symbol==""){out.reason="NO_SYMBOL";return false;}

      for(int i=PositionsTotal()-1;i>=0;i--){
         ulong ticket=PositionGetTicket(i);if(ticket==0)continue;
         if(PositionGetString(POSITION_SYMBOL)!=current.symbol)continue;
         if((ulong)PositionGetInteger(POSITION_MAGIC)!=magic)continue;
         out.position_id=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
         out.state=AS_EXEC_POSITION_ACTIVE;
         out.terminal=false;
         out.reason="AUTHORITATIVE_POSITION_FOUND";
         return true;
      }

      datetime from=(current.updated_at>0 ? current.updated_at-86400 : TimeCurrent()-86400*30);
      if(!HistorySelect(from,TimeCurrent()+60)){out.reason="HISTORY_SELECT_FAILED";return false;}
      const int total=HistoryDealsTotal();
      for(int i=0;i<total;i++){
         ulong deal=HistoryDealGetTicket(i);if(deal==0)continue;
         if((ulong)HistoryDealGetInteger(deal,DEAL_MAGIC)!=magic)continue;
         if(HistoryDealGetString(deal,DEAL_SYMBOL)!=current.symbol)continue;
         long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);
         double volume=HistoryDealGetDouble(deal,DEAL_VOLUME);
         if(entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_INOUT)out.entry_volume+=volume;
         if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY || entry==DEAL_ENTRY_INOUT)out.exit_volume+=volume;
      }

      if(out.entry_volume>0.0 && out.exit_volume+1e-8>=out.entry_volume){
         out.state=AS_EXEC_COMPLETED;out.terminal=true;out.reason="HISTORY_SHOWS_CLOSED";return true;
      }
      if(out.entry_volume>0.0){
         out.state=AS_EXEC_RECONCILING;out.terminal=false;out.reason="HISTORY_ENTRY_WITHOUT_ACTIVE_POSITION";return true;
      }
      out.state=AS_EXEC_UNKNOWN;out.terminal=false;out.reason="NO_AUTHORITATIVE_EXECUTION_EVIDENCE";return true;
   }
  };
