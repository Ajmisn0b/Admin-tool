//+------------------------------------------------------------------+
//| Risk.mqh                                                         |
//| Position sizing from a fixed share of equity at risk.            |
//+------------------------------------------------------------------+

// Round down to the broker's volume step; 0 when below the minimum lot.
double NormalizeLots(const string symbol, double lots)
  {
   double step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0.0)
      return 0.0;
   lots = MathFloor(lots / step + 1e-9) * step;
   if(lots < vmin)
      return 0.0;
   int digits = (int)MathMax(0.0, MathCeil(-MathLog10(step)));
   return NormalizeDouble(MathMin(lots, vmax), digits);
  }

// Lots such that hitting the stop loses riskPercent of equity.
double LotsForRisk(const string symbol, const bool isBuy, const double price, const double stopDistance, const double riskPercent)
  {
   double stopPrice = isBuy ? price - stopDistance : price + stopDistance;
   double lossPerLot;
   if(!OrderCalcProfit(isBuy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, symbol, 1.0, price, stopPrice, lossPerLot) || lossPerLot >= 0.0)
      return 0.0;
   double riskMoney = AccountInfoDouble(ACCOUNT_EQUITY) * riskPercent / 100.0;
   return NormalizeLots(symbol, riskMoney / -lossPerLot);
  }

// True when the account has free margin for this order.
bool MarginOk(const string symbol, const bool isBuy, const double lots, const double price)
  {
   double margin;
   if(!OrderCalcMargin(isBuy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, symbol, lots, price, margin))
      return false;
   return margin <= AccountInfoDouble(ACCOUNT_MARGIN_FREE);
  }
//+------------------------------------------------------------------+
