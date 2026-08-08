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
   bool SameOrder(const AS_ExecutionRecord &current,const ulong magic,const ulong ticket) const
     {
      if(ticket==0)return false;
      if(current.order_ticket>0 && ticket==current.order_ticket)return true;
      if((ulong)OrderGetInteger(ORDER_MAGIC)!=magic)return false;
      return OrderGetString(ORDER_SYMBOL)==current.symbol;
     }

   bool SameHistoryOrder(const AS_ExecutionRecord &current,const ulong magic,const ulong ticket) const
     {
      if(ticket==0)return false;
      if(current.order_ticket>0 && ticket==current.order_ticket)return true;
      if((ulong)HistoryOrderGetInteger(ticket,ORDER_MAGIC)!=magic)return false;
      return HistoryOrderGetString(ticket,ORDER_SYMBOL)==current.symbol;
     }
public:
   bool Rebuild(const AS_ExecutionRecord &current,const ulong magic,AS_ReconcileResultV13 &out) const
     {
      ZeroMemory(out);out.state=AS_EXEC_UNKNOWN;out.terminal=false;
      if(current.symbol==""){out.reason="NO_SYMBOL";return false;}

      // 1) Current positions are authoritative evidence that exposure exists.
      for(int i=PositionsTotal()-1;i>=0;i--){
         ulong ticket=PositionGetTicket(i);if(ticket==0)continue;
         if(PositionGetString(POSITION_SYMBOL)!=current.symbol)continue;
         if((ulong)PositionGetInteger(POSITION_MAGIC)!=magic)continue;
         out.position_id=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
         out.state=AS_EXEC_POSITION_ACTIVE;out.reason="AUTHORITATIVE_POSITION_FOUND";return true;
      }

      // 2) A still-active order is also authoritative. It may be pending broker
      // work even when no position exists yet, so absence of a position cannot
      // be interpreted as failure.
      for(int i=OrdersTotal()-1;i>=0;i--){
         ulong ticket=OrderGetTicket(i);if(!SameOrder(current,magic,ticket))continue;
         out.order_ticket=ticket;
         double initial=OrderGetDouble(ORDER_VOLUME_INITIAL);
         double remaining=OrderGetDouble(ORDER_VOLUME_CURRENT);
         out.entry_volume=MathMax(0.0,initial-remaining);
         out.state=(out.entry_volume>0.0?AS_EXEC_PARTIALLY_FILLED:AS_EXEC_ACCEPTED);
         out.reason="AUTHORITATIVE_ACTIVE_ORDER_FOUND";return true;
      }

      // 3) Reconstruct the completed/partial story from terminal history.
      datetime from=(current.updated_at>0 ? current.updated_at-300 : TimeCurrent()-86400*30);
      if(!HistorySelect(from,TimeCurrent()+60)){out.reason="HISTORY_SELECT_FAILED";return false;}

      const int deals=HistoryDealsTotal();
      for(int i=0;i<deals;i++){
         ulong deal=HistoryDealGetTicket(i);if(deal==0)continue;
         if((ulong)HistoryDealGetInteger(deal,DEAL_MAGIC)!=magic)continue;
         if(HistoryDealGetString(deal,DEAL_SYMBOL)!=current.symbol)continue;
         ulong position_id=(ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID);
         if(current.position_id>0 && position_id>0 && position_id!=current.position_id)continue;
         long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);
         double volume=HistoryDealGetDouble(deal,DEAL_VOLUME);
         if(entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_INOUT)out.entry_volume+=volume;
         if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY || entry==DEAL_ENTRY_INOUT)out.exit_volume+=volume;
         if(out.position_id==0&&position_id>0)out.position_id=position_id;
      }

      if(out.entry_volume>0.0 && out.exit_volume+1e-8>=out.entry_volume){
         out.state=AS_EXEC_COMPLETED;out.terminal=true;out.reason="HISTORY_SHOWS_CLOSED";return true;
      }
      if(out.entry_volume>out.exit_volume+1e-8){
         out.state=AS_EXEC_UNKNOWN;out.terminal=false;out.reason="HISTORY_EXPOSURE_WITHOUT_CURRENT_POSITION";return true;
      }

      // 4) If no deal exists, the order history can prove a clean terminal
      // rejection/cancellation. UNKNOWN is never made terminal merely to
      // unblock the engine.
      const int orders=HistoryOrdersTotal();
      for(int i=0;i<orders;i++){
         ulong ticket=HistoryOrderGetTicket(i);if(!SameHistoryOrder(current,magic,ticket))continue;
         out.order_ticket=ticket;
         long state=HistoryOrderGetInteger(ticket,ORDER_STATE);
         if(state==ORDER_STATE_REJECTED){out.state=AS_EXEC_REJECTED;out.terminal=true;out.reason="HISTORY_ORDER_REJECTED";return true;}
         if(state==ORDER_STATE_CANCELED||state==ORDER_STATE_EXPIRED){out.state=AS_EXEC_CANCELLED;out.terminal=true;out.reason="HISTORY_ORDER_CANCELLED_OR_EXPIRED";return true;}
      }

      out.state=AS_EXEC_UNKNOWN;out.terminal=false;out.reason="NO_AUTHORITATIVE_EXECUTION_EVIDENCE";return true;
   }
  };