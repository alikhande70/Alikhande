#pragma once

// FNV-1a. Not cryptographic — used for stable identity (signal ids, parameter
// and broker-spec fingerprints) where the only requirements are determinism
// across runs and a low collision rate at the scale of a few million strings.

string AS_Fnv1a(const string text)
  {
   uint hash = 2166136261;
   const int len = StringLen(text);
   for(int i = 0; i < len; i++)
     {
      hash ^= (uint)StringGetCharacter(text, i);
      hash *= 16777619;
     }
   return StringFormat("%08X", hash);
  }

// 64-bit variant for fingerprints where collisions would silently corrupt
// history (parameter sets, broker specs) rather than merely duplicate a row.
string AS_Fnv1a64(const string text)
  {
   ulong hash = 14695981039346656037;
   const int len = StringLen(text);
   for(int i = 0; i < len; i++)
     {
      hash ^= (ulong)StringGetCharacter(text, i);
      hash *= 1099511628211;
     }
   return StringFormat("%016I64X", hash);
  }
