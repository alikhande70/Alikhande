#pragma once
#include "../Domain/Models.mqh"
class AS_CircuitBreaker {
private: bool m_blocked; string m_reasons;
public:
   AS_CircuitBreaker(void){m_blocked=false;m_reasons="";}
   void Reset(){m_blocked=false;m_reasons="";}
   void Trip(const string reason){m_blocked=true;if(StringFind(m_reasons,reason)<0)m_reasons+=reason+";";}
   bool Blocked()const{return m_blocked;}
   string Reasons()const{return m_reasons;}
};
