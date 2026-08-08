#pragma once
#include "../Domain/Models.mqh"
#include "../Persistence/Repositories.mqh"
class AS_OutcomeEngine {
private: AS_Repositories *m_repo;
public:
   AS_OutcomeEngine(void){m_repo=NULL;}
   void Attach(AS_Repositories &repo){m_repo=&repo;}
   bool Update(AS_SignalCandidate &s){if(s.signal_id==""||s.state!=AS_SIGNAL_ACTIVE)return false;MqlTick tick;if(!SymbolInfoTick(s.symbol,tick))return false;double px=(s.direction==AS_DIR_LONG?tick.bid:tick.ask);ENUM_AS_SIGNAL_STATE next=AS_SIGNAL_ACTIVE;if(s.direction==AS_DIR_LONG){if(px<=s.stop_loss)next=AS_SIGNAL_SL;else if(px>=s.take_profit)next=AS_SIGNAL_TP;}else if(s.direction==AS_DIR_SHORT){if(px>=s.stop_loss)next=AS_SIGNAL_SL;else if(px<=s.take_profit)next=AS_SIGNAL_TP;}if(next==AS_SIGNAL_ACTIVE&&TimeCurrent()>s.expires_at)next=AS_SIGNAL_EXPIRED;if(next==AS_SIGNAL_ACTIVE)return false;s.state=next;if(m_repo!=NULL){m_repo.UpdateSignalState(s.signal_id,next);double risk=MathAbs(s.preferred_entry-s.stop_loss);double r=(risk>0?(s.direction==AS_DIR_LONG?(px-s.preferred_entry):(s.preferred_entry-px))/risk:0);m_repo.SaveOutcome(s.signal_id,next,px,r,"SHADOW_OR_SIGNAL_OUTCOME");}return true;}
};
