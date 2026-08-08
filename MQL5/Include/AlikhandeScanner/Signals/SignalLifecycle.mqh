#pragma once
#include "../Domain/Models.mqh"
#include "../Persistence/Repositories.mqh"
class AS_SignalLifecycle {
private: AS_Repositories *m_repo;
public: AS_SignalLifecycle(void){m_repo=NULL;} void Attach(AS_Repositories &repo){m_repo=&repo;} bool Register(AS_SignalCandidate &s){if(s.signal_id=="")return false;if(m_repo!=NULL&&m_repo.SignalExists(s.signal_id))return false;s.state=(s.direction==AS_DIR_NONE?AS_SIGNAL_WATCH:AS_SIGNAL_CONFIRMED);if(m_repo!=NULL)return m_repo.SaveSignal(s);return true;} bool ExpireIfNeeded(AS_SignalCandidate &s){if(s.signal_id==""||TimeCurrent()<=s.expires_at)return false;if(s.state==AS_SIGNAL_TP||s.state==AS_SIGNAL_SL||s.state==AS_SIGNAL_INVALIDATED||s.state==AS_SIGNAL_EXPIRED)return false;s.state=AS_SIGNAL_EXPIRED;if(m_repo!=NULL)m_repo.UpdateSignalState(s.signal_id,s.state);return true;} bool Activate(AS_SignalCandidate &s){if(s.state!=AS_SIGNAL_CONFIRMED)return false;s.state=AS_SIGNAL_ACTIVE;if(m_repo!=NULL)m_repo.UpdateSignalState(s.signal_id,s.state);return true;}
};
