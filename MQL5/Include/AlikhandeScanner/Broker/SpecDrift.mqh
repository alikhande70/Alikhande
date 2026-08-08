#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Hash.mqh"

class AS_SpecDrift {
public:
   string Hash(const AS_SymbolSpec &s){
      string raw=StringFormat("%s|%d|%.10f|%.10f|%.10f|%.4f|%.4f|%.4f|%.4f|%d|%d|%I64d",s.symbol,s.digits,s.point,s.tick_size,s.tick_value,s.contract_size,s.volume_min,s.volume_max,s.volume_step,s.stops_level,s.freeze_level,s.filling_mode);
      return AS_Fnv1a(raw);
   }
   bool Changed(const string previous_hash,const AS_SymbolSpec &current){return previous_hash!=""&&previous_hash!=current.spec_hash;}
};
