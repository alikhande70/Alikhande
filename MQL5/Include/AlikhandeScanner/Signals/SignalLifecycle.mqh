#pragma once
#include "../Domain/Models.mqh"
#include "../Persistence/Repositories.mqh"
#include "../Signal/LifecycleV13.mqh"

class AS_SignalLifecycle {
private:
   AS_Repositories *m_repo;
   AS_LifecycleV13 m_rules;

   ENUM_AS_SIGNAL_LIFECYCLE_V13 Map(const ENUM_AS_SIGNAL_STATE state) const {
      if(state==AS_SIGNAL_CANDIDATE)return AS_V13_CANDIDATE;
      if(state==AS_SIGNAL_CONFIRMED)return AS_V13_CONFIRMED;
      if(state==AS_SIGNAL_ACTIVE)return AS_V13_ACTIVE;
      if(state==AS_SIGNAL_TP)return AS_V13_TP;
      if(state==AS_SIGNAL_SL)return AS_V13_SL;
      if(state==AS_SIGNAL_EXPIRED)return AS_V13_EXPIRED;
      if(state==AS_SIGNAL_INVALIDATED)return AS_V13_INVALIDATED;
      if(state==AS_SIGNAL_NOT_FILLED)return AS_V13_NOT_FILLED;
      return AS_V13_CANDIDATE;
   }
public:
   AS_SignalLifecycle(void){m_repo=NULL;}
   void Attach(AS_Repositories &repo){m_repo=&repo;}

   bool Register(AS_SignalCandidate &s){
      if(s.signal_id=="")return false;
      if(m_repo!=NULL&&m_repo.SignalExists(s.signal_id))return false;
      s.state=(s.direction==AS_DIR_NONE?AS_SIGNAL_WATCH:AS_SIGNAL_CONFIRMED);
      if(m_repo!=NULL)return m_repo.SaveSignal(s);
      return true;
   }

   bool ExpireIfNeeded(AS_SignalCandidate &s){
      if(s.signal_id==""||TimeCurrent()<=s.expires_at)return false;
      ENUM_AS_SIGNAL_LIFECYCLE_V13 from=Map(s.state);
      if(m_rules.Terminal(from))return false;
      if(from!=AS_V13_CONFIRMED&&from!=AS_V13_LIVE_BLOCKED&&from!=AS_V13_LIVE_TRADABLE)return false;
      s.state=AS_SIGNAL_EXPIRED;
      if(m_repo!=NULL)m_repo.UpdateSignalState(s.signal_id,s.state);
      return true;
   }

   bool Activate(AS_SignalCandidate &s){
      if(s.state!=AS_SIGNAL_CONFIRMED)return false;
      if(!m_rules.CanTransition(AS_V13_LIVE_TRADABLE,AS_V13_ACTIVE))return false;
      s.state=AS_SIGNAL_ACTIVE;
      if(m_repo!=NULL)m_repo.UpdateSignalState(s.signal_id,s.state);
      return true;
   }
};