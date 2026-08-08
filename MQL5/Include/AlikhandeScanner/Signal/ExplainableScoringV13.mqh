#pragma once

struct AS_ScoreComponentV13
  {
   string code;
   double weight;
   double contribution;
   string explanation;
  };

struct AS_ScoreResultV13
  {
   double raw_score;
   double final_score;
   string positive_reasons;
   string penalties;
   string veto_codes;
   bool hard_blocked;
  };

class AS_ExplainableScoringV13
  {
private:
   double Clamp(const double value) const { return MathMax(0.0,MathMin(100.0,value)); }
public:
   void Evaluate(const AS_ScoreComponentV13 &components[],
                 const string penalties[],
                 const double penalty_values[],
                 const string veto_codes[],
                 AS_ScoreResultV13 &out) const
     {
      ZeroMemory(out);
      double total=0.0;
      for(int i=0;i<ArraySize(components);i++)
        {
         total+=components[i].contribution;
         if(components[i].contribution>0.0)
            out.positive_reasons+=components[i].code+"="+DoubleToString(components[i].contribution,1)+";";
        }
      out.raw_score=Clamp(total);

      double penalty_total=0.0;
      const int pcount=MathMin(ArraySize(penalties),ArraySize(penalty_values));
      for(int i=0;i<pcount;i++)
        {
         penalty_total+=MathMax(0.0,penalty_values[i]);
         out.penalties+=penalties[i]+"=-"+DoubleToString(MathMax(0.0,penalty_values[i]),1)+";";
        }

      for(int i=0;i<ArraySize(veto_codes);i++)
        {
         if(veto_codes[i]=="")continue;
         out.veto_codes+=veto_codes[i]+";";
         out.hard_blocked=true;
        }
      out.final_score=Clamp(out.raw_score-penalty_total);
     }
  };
