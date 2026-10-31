//+------------------------------------------------------------------+
//| GoldScalper.mq5                                                  |
//| Scalping EA for XAUUSD with pluggable entry strategies.          |
//| One position at a time; stop = ATR multiple, target = R multiple,|
//| optional time exit; risk-based sizing with daily limits.         |
//+------------------------------------------------------------------+
#property version   "0.20"
#property description "XAUUSD scalping framework: swap strategies in the inputs and compare them in the Strategy Tester."

#include <Trade/Trade.mqh>
#include "Strategies.mqh"
#include "Risk.mqh"

enum ENUM_STRATEGY
  {
   STRAT_BOLLINGER_REVERT = 0, // Bollinger mean reversion
   STRAT_EMA_CROSS        = 1, // EMA crossover
   STRAT_RSI_REVERT       = 2  // RSI mean reversion (best in the backtest)
  };

input group "Strategy"
// Defaults are the backtest's best setup: RSI(14) 20/80 on M1, London + New York hours.
input ENUM_STRATEGY   InpStrategy         = STRAT_RSI_REVERT;
input ENUM_TIMEFRAMES InpTimeframe        = PERIOD_M1;
input int             InpRsiPeriod        = 14;     // RSI period
input double          InpRsiLow           = 20.0;   // RSI: buy below this, sell above 100 - this
input int             InpRsiTrendEma      = 0;      // RSI: trend EMA filter period (0 = off)
input int             InpBandsPeriod      = 50;     // Bollinger period
input double          InpBandsDeviation   = 3.0;    // Bollinger deviations
input int             InpFastEma          = 9;      // EMA cross: fast period
input int             InpSlowEma          = 21;     // EMA cross: slow period

input group "Exits"
input int             InpAtrPeriod        = 14;
input double          InpStopAtr          = 3.0;    // stop loss = ATR x this
input double          InpRewardRisk       = 1.5;    // take profit = stop x this
input int             InpMaxBars          = 60;     // close after N bars (0 = off)

input group "Risk"
input double          InpRiskPercent      = 0.5;    // equity risked per trade, %
input double          InpFixedLots        = 0.0;    // > 0 overrides risk sizing
input int             InpMaxTradesPerDay  = 10;     // 0 = no limit
input double          InpMaxDailyLossPct  = 2.0;    // stop trading for the day after this loss, %

input group "Filters"
// 10-19 server time = London 08:00-17:00 on the usual GMT+2/+3 broker clock
input int             InpSessionStartHour = 10;     // server time, inclusive
input int             InpSessionEndHour   = 19;     // server time, exclusive (start > end wraps midnight)
input int             InpMaxSpreadPoints  = 0;      // 0 = off; points depend on the broker's digits

input group "General"
input ulong           InpMagic            = 26103101;

CTrade     g_trade;
CStrategy *g_strategy = NULL;
int        g_atrHandle = INVALID_HANDLE;

//+------------------------------------------------------------------+
int OnInit(void)
  {
   if(InpStopAtr <= 0.0 || InpRewardRisk <= 0.0 || InpRiskPercent < 0.0 || InpMaxBars < 0)
     {
      Print("Invalid exit or risk inputs");
      return INIT_PARAMETERS_INCORRECT;
     }
   switch(InpStrategy)
     {
      case STRAT_EMA_CROSS:
         g_strategy = new CEmaCross(InpFastEma, InpSlowEma);
         break;
      case STRAT_RSI_REVERT:
         g_strategy = new CRsiRevert(InpRsiPeriod, InpRsiLow, InpRsiTrendEma);
         break;
      default:
         g_strategy = new CBollingerRevert(InpBandsPeriod, InpBandsDeviation);
     }
   if(!g_strategy.Init(_Symbol, InpTimeframe))
     {
      Print("Strategy init failed: ", g_strategy.Name());
      return INIT_PARAMETERS_INCORRECT;
     }
   g_atrHandle = iATR(_Symbol, InpTimeframe, InpAtrPeriod);
   if(g_atrHandle == INVALID_HANDLE)
      return INIT_FAILED;

   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   g_trade.SetDeviationInPoints(30);
   PrintFormat("GoldScalper started: %s on %s %s", g_strategy.Name(), _Symbol, EnumToString(InpTimeframe));
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_strategy != NULL)
      delete g_strategy;
   if(g_atrHandle != INVALID_HANDLE)
      IndicatorRelease(g_atrHandle);
  }

//+------------------------------------------------------------------+
void OnTick(void)
  {
   ApplyTimeExit();
   if(!IsNewBar() || HasPosition())
      return;
   if(!InSession() || !SpreadOk() || !DailyLimitsOk())
      return;

   int signal = g_strategy.Signal();
   if(signal == SIGNAL_NONE)
      return;
   OpenTrade(signal == SIGNAL_BUY);
  }

//+------------------------------------------------------------------+
void OpenTrade(const bool isBuy)
  {
   double atr[];
   MqlTick tick;
   if(CopyBuffer(g_atrHandle, 0, 1, 1, atr) != 1 || !SymbolInfoTick(_Symbol, tick))
      return;

   double minStop = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double stopDist = MathMax(atr[0] * InpStopAtr, minStop);
   double takeDist = MathMax(stopDist * InpRewardRisk, minStop);
   double price = isBuy ? tick.ask : tick.bid;
   double sl = NormalizeDouble(isBuy ? price - stopDist : price + stopDist, _Digits);
   double tp = NormalizeDouble(isBuy ? price + takeDist : price - takeDist, _Digits);

   double lots = InpFixedLots > 0.0 ? NormalizeLots(_Symbol, InpFixedLots)
                                    : LotsForRisk(_Symbol, isBuy, price, stopDist, InpRiskPercent);
   if(lots <= 0.0)
     {
      Print("Skip: position size below the broker minimum for this stop");
      return;
     }
   if(!MarginOk(_Symbol, isBuy, lots, price))
     {
      Print("Skip: not enough free margin");
      return;
     }

   string comment = g_strategy.Name();
   bool ok = isBuy ? g_trade.Buy(lots, _Symbol, price, sl, tp, comment)
                   : g_trade.Sell(lots, _Symbol, price, sl, tp, comment);
   if(!ok)
      PrintFormat("Order failed: %u %s", g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
  }

//+------------------------------------------------------------------+
//| Close our position once it has been open InpMaxBars bars.        |
//+------------------------------------------------------------------+
void ApplyTimeExit(void)
  {
   if(InpMaxBars <= 0)
      return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !IsOurs())
         continue;
      datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
      if(iBarShift(_Symbol, InpTimeframe, opened) >= InpMaxBars)
         g_trade.PositionClose(ticket);
     }
  }

//+------------------------------------------------------------------+
bool IsNewBar(void)
  {
   static datetime lastBar = 0;
   datetime bar = iTime(_Symbol, InpTimeframe, 0);
   if(bar == 0 || bar == lastBar)
      return false;
   lastBar = bar;
   return true;
  }

// Assumes the position is already selected.
bool IsOurs(void)
  {
   return PositionGetString(POSITION_SYMBOL) == _Symbol && (ulong)PositionGetInteger(POSITION_MAGIC) == InpMagic;
  }

bool HasPosition(void)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
      if(PositionGetTicket(i) != 0 && IsOurs())
         return true;
   return false;
  }

bool InSession(void)
  {
   MqlDateTime now;
   TimeToStruct(TimeCurrent(), now);
   if(InpSessionStartHour <= InpSessionEndHour)
      return now.hour >= InpSessionStartHour && now.hour < InpSessionEndHour;
   return now.hour >= InpSessionStartHour || now.hour < InpSessionEndHour;
  }

bool SpreadOk(void)
  {
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return false;
   return InpMaxSpreadPoints <= 0 || (tick.ask - tick.bid) / _Point <= InpMaxSpreadPoints;
  }

//+------------------------------------------------------------------+
//| Trades opened today and today's P/L (closed + floating) for this |
//| EA, read from history so a restart does not reset the limits.    |
//+------------------------------------------------------------------+
bool DailyLimitsOk(void)
  {
   datetime dayStart = iTime(_Symbol, PERIOD_D1, 0);
   if(dayStart == 0 || !HistorySelect(dayStart, TimeCurrent() + 60))
      return false;

   int    trades = 0;
   double pnl = 0.0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
     {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0 || HistoryDealGetString(deal, DEAL_SYMBOL) != _Symbol ||
         (ulong)HistoryDealGetInteger(deal, DEAL_MAGIC) != InpMagic)
         continue;
      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal, DEAL_ENTRY);
      if(entry == DEAL_ENTRY_IN)
         trades++;
      pnl += HistoryDealGetDouble(deal, DEAL_COMMISSION);
      if(entry == DEAL_ENTRY_OUT)
         pnl += HistoryDealGetDouble(deal, DEAL_PROFIT) + HistoryDealGetDouble(deal, DEAL_SWAP);
     }
   for(int i = PositionsTotal() - 1; i >= 0; i--)
      if(PositionGetTicket(i) != 0 && IsOurs())
         pnl += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);

   if(InpMaxTradesPerDay > 0 && trades >= InpMaxTradesPerDay)
      return false;
   double limit = AccountInfoDouble(ACCOUNT_BALANCE) * InpMaxDailyLossPct / 100.0;
   return InpMaxDailyLossPct <= 0.0 || pnl > -limit;
  }
//+------------------------------------------------------------------+
