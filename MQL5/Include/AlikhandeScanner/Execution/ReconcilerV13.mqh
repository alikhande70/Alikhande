#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"

struct AS_ReconcileResultV13
  {
   ENUM_AS_EXEC_STATE state;
   ulong position_id;
   ulong order_ticket;
   double entry_volume;
   double exit_volume;
   bool terminal;
   string reason;
  };

class AS_ReconcilerV13
  {
private:
   bool SameActiveOrder(const AS_ExecutionRecord &current,const ulong magic,const ulong ticket) const
     {
      if(ticket==0)return false;
      if(current.order_ticket>0)return ticket==current.order_ticket;
      return (ulong)OrderGetInteger(ORDER_MAGIC)==magic && OrderGetString(ORDER_SYMBOL)==current.symbol;
     }

   bool SameHistoryOrder(const AS_ExecutionRecord &current,const ulong magic,const ulong ticket) const
     {
      if(ticket==0)return false;
      if(current.order_ticket>0)return ticket==current.order_ticket;
      return (ulong)HistoryOrderGetInteger(ticket,ORDER_MAGIC)==magic && HistoryOrderGetString(ticket,ORDER_SYMBOL)==current.symbol;
     }

   ulong CorrelatedPositionId(const AS_ExecutionRecord &current,const ulong magic) const
     {
      if(current.position_id>0)return current.position_id;
      if(current.order_ticket>0 && HistoryOrderSelect(current.order_ticket)){
         if((ulong)HistoryOrderGetInteger(current.order_ticket,ORDER_MAGIC)==magic && HistoryOrderGetString(current.order_ticket,ORDER_SYMBOL)==current.symbol){
            ulong position_id=(ulong)HistoryOrderGetInteger(current.order_ticket,ORDER_POSITION_ID);
            if(position_id>0)return position_id;
         }
      }
      if(current.order_ticket>0){
         for(int i=0;i<HistoryDealsTotal();i++){
            ulong deal=HistoryDealGetTicket(i);if(deal==0)continue;
            if((ulong)HistoryDealGetInteger(deal,DEAL_MAGIC)!=magic)continue;
            if(HistoryDealGetString(deal,DEAL_SYMBOL)!=current.symbol)continue;
            if((ulong)HistoryDealGetInteger(deal,DEAL_ORDER)!=current.order_ticket)continue;
            long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);
            if(entry!=DEAL_ENTRY_IN && entry!=DEAL_ENTRY_INOUT)continue;
            ulong position_id=(ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID);
            if(position_id>0)return position_id;
         }
      }
      return 0;
     }
public:
   bool Rebuild(const AS_ExecutionRecord &current,const ulong magic,AS_ReconcileResultV13 &out) const
     {
      ZeroMemory(out);out.state=AS_EXEC_UNKNOWN;out.terminal=false;
      if(current.symbol==""){out.reason="NO_SYMBOL";return false;}

      datetime from=(current.created_at>0 ? current.created_at-3600 : (current.updated_at>0 ? current.updated_at-86400 : TimeCurrent()-86400*30));
      if(!HistorySelect(from,TimeCurrent()+60)){out.reason="HISTORY_SELECT_FAILED";return false;}
      ulong correlation_position=CorrelatedPositionId(current,magic);
      out.position_id=correlation_position;

      if(correlation_position>0){
         for(int i=PositionsTotal()-1;i>=0;i--){
            ulong ticket=PositionGetTicket(i);if(ticket==0)continue;
            if((ulong)PositionGetInteger(POSITION_MAGIC)!=magic)continue;
            if(PositionGetString(POSITION_SYMBOL)!=current.symbol)continue;
            if((ulong)PositionGetInteger(POSITION_IDENTIFIER)!=correlation_position)continue;
            out.state=AS_EXEC_POSITION_ACTIVE;out.reason="AUTHORITATIVE_POSITION_FOUND";return true;
         }
      }

      for(int i=OrdersTotal()-1;i>=0;i--){
         ulong ticket=OrderGetTicket(i);if(!SameActiveOrder(current,magic,ticket))continue;
         out.order_ticket=ticket;
         double initial=OrderGetDouble(ORDER_VOLUME_INITIAL),remaining=OrderGetDouble(ORDER_VOLUME_CURRENT);
         out.entry_volume=MathMax(0.0,initial-remaining);
         out.state=(out.entry_volume>0.0?AS_EXEC_PARTIALLY_FILLED:AS_EXEC_ACCEPTED);
         out.reason="AUTHORITATIVE_ACTIVE_ORDER_FOUND";return true;
      }

      if(correlation_position>0){
         const int deals=HistoryDealsTotal();
         for(int i=0;i<deals;i++){
            ulong deal=HistoryDealGetTicket(i);if(deal==0)continue;
            if((ulong)HistoryDealGetInteger(deal,DEAL_MAGIC)!=magic)continue;
            if(HistoryDealGetString(deal,DEAL_SYMBOL)!=current.symbol)continue;
            if((ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID)!=correlation_position)continue;
            long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);double volume=HistoryDealGetDouble(deal,DEAL_VOLUME);
            if(entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_INOUT)out.entry_volume+=volume;
            if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY || entry==DEAL_ENTRY_INOUT)out.exit_volume+=volume;
         }
         if(out.entry_volume>0.0 && out.exit_volume+1e-8>=out.entry_volume){out.state=AS_EXEC_COMPLETED;out.terminal=true;out.reason="HISTORY_SHOWS_CLOSED";return true;}
         if(out.entry_volume>out.exit_volume+1e-8){out.state=AS_EXEC_UNKNOWN;out.terminal=false;out.reason="HISTORY_EXPOSURE_WITHOUT_CURRENT_POSITION";return true;}
      }

      const int orders=HistoryOrdersTotal();
      for(int i=0;i<orders;i++){
         ulong ticket=HistoryOrderGetTicket(i);if(!SameHistoryOrder(current,magic,ticket))continue;
         out.order_ticket=ticket;long state=HistoryOrderGetInteger(ticket,ORDER_STATE);
         if(state==ORDER_STATE_REJECTED){out.state=AS_EXEC_REJECTED;out.terminal=true;out.reason="HISTORY_ORDER_REJECTED";return true;}
         if(state==ORDER_STATE_CANCELED||state==ORDER_STATE_EXPIRED){out.state=AS_EXEC_CANCELLED;out.terminal=true;out.reason="HISTORY_ORDER_CANCELLED_OR_EXPIRED";return true;}
         if(state==ORDER_STATE_FILLED||state==ORDER_STATE_PARTIAL){out.state=AS_EXEC_UNKNOWN;out.terminal=false;out.reason="ORDER_FILLED_WITHOUT_CORRELATED_POSITION_EVIDENCE";return true;}
      }

      out.state=AS_EXEC_UNKNOWN;out.terminal=false;out.reason="NO_AUTHORITATIVE_EXECUTION_EVIDENCE";return true;
   }
  };