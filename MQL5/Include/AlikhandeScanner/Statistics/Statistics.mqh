#pragma once
class AS_Statistics {
public:
   bool Wilson(const int wins,const int total,double &low,double &high){if(total<=0)return false;double z=1.96,p=(double)wins/total,den=1+z*z/total,center=(p+z*z/(2*total))/den,margin=z*MathSqrt((p*(1-p)+z*z/(4*total))/total)/den;low=MathMax(0.0,center-margin);high=MathMin(1.0,center+margin);return true;}
};
