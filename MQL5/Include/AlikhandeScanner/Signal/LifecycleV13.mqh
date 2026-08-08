#pragma once

enum ENUM_AS_SIGNAL_LIFECYCLE_V13
  {
   AS_V13_CANDIDATE = 0,
   AS_V13_CONFIRMED = 1,
   AS_V13_LIVE_BLOCKED = 2,
   AS_V13_LIVE_TRADABLE = 3,
   AS_V13_ACTIVE = 4,
   AS_V13_TP = 5,
   AS_V13_SL = 6,
   AS_V13_EXPIRED = 7,
   AS_V13_INVALIDATED = 8,
   AS_V13_NOT_FILLED = 9
  };

class AS_LifecycleV13
  {
public:
   bool Terminal(const ENUM_AS_SIGNAL_LIFECYCLE_V13 state) const
     {
      return state==AS_V13_TP || state==AS_V13_SL || state==AS_V13_EXPIRED ||
             state==AS_V13_INVALIDATED || state==AS_V13_NOT_FILLED;
     }

   bool CanTransition(const ENUM_AS_SIGNAL_LIFECYCLE_V13 from,
                      const ENUM_AS_SIGNAL_LIFECYCLE_V13 to) const
     {
      if(Terminal(from)) return false;
      if(from==AS_V13_CANDIDATE) return to==AS_V13_CONFIRMED || to==AS_V13_INVALIDATED;
      if(from==AS_V13_CONFIRMED) return to==AS_V13_LIVE_BLOCKED || to==AS_V13_LIVE_TRADABLE || to==AS_V13_EXPIRED || to==AS_V13_INVALIDATED;
      if(from==AS_V13_LIVE_BLOCKED) return to==AS_V13_LIVE_TRADABLE || to==AS_V13_EXPIRED || to==AS_V13_INVALIDATED;
      if(from==AS_V13_LIVE_TRADABLE) return to==AS_V13_LIVE_BLOCKED || to==AS_V13_ACTIVE || to==AS_V13_EXPIRED || to==AS_V13_INVALIDATED || to==AS_V13_NOT_FILLED;
      if(from==AS_V13_ACTIVE) return to==AS_V13_TP || to==AS_V13_SL || to==AS_V13_INVALIDATED;
      return false;
     }
  };
