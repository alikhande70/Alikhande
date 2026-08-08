#pragma once
#include "SignalDomainV13.mqh"

class AS_ZoneSemanticsV13
  {
public:
   ENUM_AS_ZONE_RELATION Relation(const AS_TypedZone &zone,const double price) const
     {
      if(!zone.valid || zone.broken || zone.low<=0.0 || zone.high<=0.0 || zone.low>zone.high)
         return AS_ZONE_UNAVAILABLE;
      if(price < zone.low)
         return AS_ZONE_BELOW;
      if(price > zone.high)
         return AS_ZONE_ABOVE;
      return AS_ZONE_INSIDE;
     }

   bool IsDirectInteraction(const AS_TypedZone &zone,const double price) const
     {
      return Relation(zone,price)==AS_ZONE_INSIDE;
     }

   bool IsUsableAnchor(const AS_TypedZone &zone,const ENUM_AS_DIRECTION direction) const
     {
      if(!zone.valid || zone.broken)
         return false;
      if(direction==AS_DIR_LONG)
         return zone.kind==AS_ZONE_DEMAND;
      if(direction==AS_DIR_SHORT)
         return zone.kind==AS_ZONE_SUPPLY;
      return false;
     }
  };
