#pragma once
string AS_Fnv1a(const string text) {
   uint hash=2166136261;
   for(int i=0;i<StringLen(text);i++) { hash^=(uint)StringGetCharacter(text,i); hash*=16777619; }
   return StringFormat("%08X",hash);
}
