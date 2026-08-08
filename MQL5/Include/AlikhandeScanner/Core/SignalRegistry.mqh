#pragma once
class AS_SignalRegistry {
private:
   string m_ids[];
public:
   bool Contains(const string id)const{
      for(int i=0;i<ArraySize(m_ids);i++)if(m_ids[i]==id)return true;
      return false;
   }
   bool Remember(const string id){
      if(id=="" || Contains(id))return false;
      int n=ArraySize(m_ids);
      if(n>=2048){for(int i=1;i<n;i++)m_ids[i-1]=m_ids[i];ArrayResize(m_ids,n-1);n--;}
      ArrayResize(m_ids,n+1);m_ids[n]=id;return true;
   }
};
