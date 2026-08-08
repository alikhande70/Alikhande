#pragma once
#include "../Core/VersionInfo.mqh"
class AS_Dashboard {
private:string m_prefix;int m_row_h;
   void Label(string name,string text,int x,int y,color c){string n=m_prefix+name;if(ObjectFind(0,n)<0)ObjectCreate(0,n,OBJ_LABEL,0,0,0);ObjectSetInteger(0,n,OBJPROP_XDISTANCE,x);ObjectSetInteger(0,n,OBJPROP_YDISTANCE,y);ObjectSetInteger(0,n,OBJPROP_COLOR,c);ObjectSetInteger(0,n,OBJPROP_FONTSIZE,9);ObjectSetString(0,n,OBJPROP_TEXT,text);ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);}
public:
   AS_Dashboard(void){m_prefix="ALKSCN_";m_row_h=20;}
   void Clear(void){ObjectsDeleteAll(0,m_prefix);}
   void Header(void){Label("H0","Alikhande Scanner v"+AS_VERSION+" | Symbol | Spread | H1 | M15 | Long | Short | Status | Open",10,15,clrWhite);}
   void Row(const int row,const string symbol,const double spread,const string h1,const string m15,const double lng,const double sht,const string status){int y=15+(row+1)*m_row_h;string text=StringFormat("%-12s | %7.1f | %-8s | %-8s | %5.1f | %5.1f | %-14s",symbol,spread,h1,m15,lng,sht,status);Label("ROW_"+IntegerToString(row),text,10,y,(status=="LONG"?clrLime:(status=="SHORT"?clrTomato:clrSilver)));string b=m_prefix+"OPEN_"+symbol;if(ObjectFind(0,b)<0)ObjectCreate(0,b,OBJ_BUTTON,0,0,0);ObjectSetInteger(0,b,OBJPROP_XDISTANCE,780);ObjectSetInteger(0,b,OBJPROP_YDISTANCE,y-3);ObjectSetInteger(0,b,OBJPROP_XSIZE,55);ObjectSetInteger(0,b,OBJPROP_YSIZE,18);ObjectSetString(0,b,OBJPROP_TEXT,"Open");}
   bool ParseOpen(const string obj,string &symbol){string p=m_prefix+"OPEN_";if(StringFind(obj,p)!=0)return false;symbol=StringSubstr(obj,StringLen(p));return true;}
};
