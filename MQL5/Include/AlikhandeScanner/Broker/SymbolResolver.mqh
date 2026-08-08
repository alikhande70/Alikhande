#pragma once
#include "../Domain/Models.mqh"

class AS_SymbolResolver {
private:
   string Upper(string value){ StringToUpper(value); return value; }
   string BaseName(string value){
      StringTrimLeft(value); StringTrimRight(value);
      if(StringLen(value)>0 && StringSubstr(value,0,1)=="#") value=StringSubstr(value,1);
      int len=StringLen(value);
      if(len>2 && StringSubstr(value,len-2,2)=="_o") value=StringSubstr(value,0,len-2);
      return value;
   }
   bool SelectCandidate(const string candidate,string &resolved){
      bool custom=false;
      if(SymbolExist(candidate,custom) && SymbolSelect(candidate,true)){resolved=candidate;return true;}
      return false;
   }
public:
   bool Resolve(const string requested,string &resolved){
      resolved=""; string clean=requested; StringTrimLeft(clean); StringTrimRight(clean); if(clean=="")return false;
      if(SelectCandidate(clean,resolved))return true;
      string base=BaseName(clean);
      if(SelectCandidate(base+"_o",resolved))return true;
      if(SelectCandidate("#"+base,resolved))return true;
      if(SelectCandidate(base,resolved))return true;
      string target=Upper(base); int total=SymbolsTotal(false);
      for(int i=0;i<total;i++){
         string name=SymbolName(i,false); string normalized=Upper(BaseName(name));
         if(normalized==target && SymbolSelect(name,true)){resolved=name;return true;}
      }
      return false;
   }
};
