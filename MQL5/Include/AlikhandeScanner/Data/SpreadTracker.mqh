#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"
class AS_SpreadTracker {
private: double m_samples[]; int m_capacity; int m_count; int m_pos;
public:
   AS_SpreadTracker(void){m_capacity=240;m_count=0;m_pos=0;ArrayResize(m_samples,m_capacity);}
   void Add(const double value){ if(value<=0)return; m_samples[m_pos]=value; m_pos=(m_pos+1)%m_capacity; if(m_count<m_capacity)m_count++; }
   int Count(void)const{return m_count;}
   double Median(void){ if(m_count==0)return 0; double tmp[]; ArrayResize(tmp,m_count); for(int i=0;i<m_count;i++)tmp[i]=m_samples[i]; ArraySort(tmp); if((m_count%2)==1)return tmp[m_count/2]; return (tmp[m_count/2-1]+tmp[m_count/2])/2.0; }
   ENUM_AS_SPREAD_STATE Classify(const double current,const int minimum_samples,double &ratio){ if(m_count<minimum_samples){ratio=0;return AS_SPREAD_WARMING_UP;} double med=Median(); if(med<=0){ratio=0;return AS_SPREAD_WARMING_UP;} ratio=current/med; if(ratio<AS_SPREAD_NORMAL_MAX_RATIO)return AS_SPREAD_NORMAL; if(ratio<AS_SPREAD_ELEVATED_MAX_RATIO)return AS_SPREAD_ELEVATED; if(ratio<AS_SPREAD_HIGH_MAX_RATIO)return AS_SPREAD_HIGH; return AS_SPREAD_EXTREME; }
};
