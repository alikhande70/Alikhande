#pragma once
#include "../Domain/Models.mqh"
#include "../Core/VersionInfo.mqh"
#include "../Core/SignalRegistry.mqh"

class AS_SignalLogger {
private: AS_SignalRegistry m_registry;
public:
   bool AppendUnique(const AS_SignalCandidate &s){
      if(s.signal_id==""||m_registry.Contains(s.signal_id))return false;
      int h=FileOpen("AlikhandeScanner\\signals_v2.csv",FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ,';');if(h==INVALID_HANDLE)return false;
      if(FileSize(h)==0)FileWrite(h,"schema","signal_id","server_time","confirmation_time","symbol","direction","setup","long_score","short_score","entry","sl","tp","support","resistance","rule_version","scoring_version","parameter_hash","reasons","codes");
      FileSeek(h,0,SEEK_END);FileWrite(h,AS_SCHEMA_VERSION,s.signal_id,(long)s.creation_time,(long)s.confirmation_bar_time,s.symbol,(int)s.direction,(int)s.setup,s.long_score,s.short_score,s.preferred_entry,s.stop_loss,s.take_profit,s.nearest_support,s.nearest_resistance,s.rule_version,s.scoring_version,s.parameter_hash,s.reasons,s.validation_codes);
      FileFlush(h);FileClose(h);m_registry.Remember(s.signal_id);return true;
   }
};
