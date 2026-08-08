#pragma once
#include "SignalDomainV13.mqh"
#include "ZoneSemanticsV13.mqh"
#include "../Data/RuntimeSnapshots.mqh"

class AS_LiveValidatorV13
  {
private:
   AS_ZoneSemanticsV13 m_zone_semantics;
public:
   bool Validate(const AS_StructuralCandidateV13 &candidate,
                 const AS_TypedZone &anchor,
                 const AS_QuoteState &quote,
                 const double minimum_rr,
                 AS_LiveValidationV13 &out) const
     {
      ZeroMemory(out);
      out.candidate_id = candidate.candidate_id;
      out.symbol = candidate.symbol;
      out.direction = candidate.direction;
      out.bid = quote.bid;
      out.ask = quote.ask;
      out.evaluated_at = TimeCurrent();

      if(!candidate.valid)
        {
         out.veto_codes += "STRUCTURAL_CANDIDATE_INVALID;";
         return false;
        }
      if(!quote.fresh || quote.data_state!=AS_DATA_READY)
        {
         out.veto_codes += "QUOTE_NOT_FRESH;";
         return false;
        }
      if(!m_zone_semantics.IsUsableAnchor(anchor,candidate.direction))
        {
         out.veto_codes += "ANCHOR_ZONE_INVALID;";
         return false;
        }

      const double interaction_price=(candidate.direction==AS_DIR_LONG ? quote.bid : quote.ask);
      out.zone_relation=m_zone_semantics.Relation(anchor,interaction_price);
      if(out.zone_relation==AS_ZONE_UNAVAILABLE)
        {
         out.veto_codes += "ZONE_UNAVAILABLE;";
         return false;
        }

      // A direct inside-zone interaction is valid by construction. Nearby
      // interactions may be introduced later only through an explicit distance
      // policy; v1.3 does not hide that policy inside a nearest-zone search.
      if(out.zone_relation!=AS_ZONE_INSIDE)
        {
         out.veto_codes += "PRICE_NOT_IN_ANCHOR_ZONE;";
         return false;
        }

      const double buffer=MathMax(candidate.structural_atr*0.15,quote.point*5.0);
      out.entry=(candidate.direction==AS_DIR_LONG ? quote.ask : quote.bid);
      out.stop_loss=(candidate.direction==AS_DIR_LONG ? anchor.low-buffer : anchor.high+buffer);
      out.risk_distance=MathAbs(out.entry-out.stop_loss);
      if(out.risk_distance<=0.0 || candidate.structural_atr<=0.0 || out.risk_distance>candidate.structural_atr*2.5)
        {
         out.veto_codes += "INVALID_STRUCTURAL_STOP;";
         return false;
        }

      const double rr=MathMax(2.0,minimum_rr);
      out.take_profit=(candidate.direction==AS_DIR_LONG
                       ? out.entry+rr*out.risk_distance
                       : out.entry-rr*out.risk_distance);
      out.live_score=candidate.structural_score;
      out.reasons="DIRECT_ZONE_INTERACTION;LIVE_QUOTE_VALID;";
      out.tradable=true;
      return true;
     }
  };
