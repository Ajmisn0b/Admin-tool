//+------------------------------------------------------------------+
//| Strategies.mqh                                                   |
//| Pluggable entry signals. A strategy only answers "buy, sell or   |
//| nothing" on the last closed bar; exits, sizing and filters live  |
//| in the EA so every strategy is tested under the same rules.      |
//+------------------------------------------------------------------+
#define SIGNAL_NONE  0
#define SIGNAL_BUY   1
#define SIGNAL_SELL -1

class CStrategy
  {
protected:
   string            m_symbol;
   ENUM_TIMEFRAMES   m_tf;
public:
   virtual          ~CStrategy(void) {}
   virtual bool      Init(const string symbol, const ENUM_TIMEFRAMES tf) { m_symbol = symbol; m_tf = tf; return true; }
   virtual int       Signal(void) = 0;
   virtual string    Name(void) = 0;
  };

//+------------------------------------------------------------------+
//| Close crosses outside a Bollinger band -> fade back to the mean. |
//+------------------------------------------------------------------+
class CBollingerRevert : public CStrategy
  {
private:
   int               m_handle;
   int               m_period;
   double            m_dev;
public:
                     CBollingerRevert(const int period, const double dev) : m_handle(INVALID_HANDLE), m_period(period), m_dev(dev) {}
                    ~CBollingerRevert(void) { if(m_handle != INVALID_HANDLE) IndicatorRelease(m_handle); }

   virtual bool      Init(const string symbol, const ENUM_TIMEFRAMES tf) override
     {
      CStrategy::Init(symbol, tf);
      m_handle = iBands(symbol, tf, m_period, 0, m_dev, PRICE_CLOSE);
      return m_handle != INVALID_HANDLE;
     }

   virtual int       Signal(void) override
     {
      double upper[], lower[], close[];
      // two closed bars, oldest first: [0] = bar 2, [1] = bar 1
      if(CopyBuffer(m_handle, 1, 1, 2, upper) != 2 ||
         CopyBuffer(m_handle, 2, 1, 2, lower) != 2 ||
         CopyClose(m_symbol, m_tf, 1, 2, close) != 2)
         return SIGNAL_NONE;
      if(close[1] < lower[1] && close[0] >= lower[0])
         return SIGNAL_BUY;
      if(close[1] > upper[1] && close[0] <= upper[0])
         return SIGNAL_SELL;
      return SIGNAL_NONE;
     }

   virtual string    Name(void) override { return StringFormat("BollingerRevert(%d, %.1f)", m_period, m_dev); }
  };

//+------------------------------------------------------------------+
//| RSI closes into oversold/overbought -> fade it. Optional trend   |
//| filter: only buy above the trend EMA and only sell below it.     |
//| Best result of the one-year M1 gold backtest (see backtest/).    |
//+------------------------------------------------------------------+
class CRsiRevert : public CStrategy
  {
private:
   int               m_rsiHandle;
   int               m_trendHandle;
   int               m_period;
   double            m_low;
   int               m_trend;
public:
                     CRsiRevert(const int period, const double low, const int trend) : m_rsiHandle(INVALID_HANDLE), m_trendHandle(INVALID_HANDLE), m_period(period), m_low(low), m_trend(trend) {}
                    ~CRsiRevert(void)
     {
      if(m_rsiHandle != INVALID_HANDLE) IndicatorRelease(m_rsiHandle);
      if(m_trendHandle != INVALID_HANDLE) IndicatorRelease(m_trendHandle);
     }

   virtual bool      Init(const string symbol, const ENUM_TIMEFRAMES tf) override
     {
      CStrategy::Init(symbol, tf);
      if(m_low <= 0.0 || m_low >= 50.0)
         return false;
      m_rsiHandle = iRSI(symbol, tf, m_period, PRICE_CLOSE);
      if(m_trend > 0)
         m_trendHandle = iMA(symbol, tf, m_trend, 0, MODE_EMA, PRICE_CLOSE);
      return m_rsiHandle != INVALID_HANDLE && (m_trend <= 0 || m_trendHandle != INVALID_HANDLE);
     }

   virtual int       Signal(void) override
     {
      double rsi[];
      if(CopyBuffer(m_rsiHandle, 0, 1, 2, rsi) != 2)
         return SIGNAL_NONE;
      // fire only on the bar RSI enters the zone: [0] = bar 2, [1] = bar 1
      int signal = SIGNAL_NONE;
      if(rsi[1] < m_low && rsi[0] >= m_low)
         signal = SIGNAL_BUY;
      else if(rsi[1] > 100.0 - m_low && rsi[0] <= 100.0 - m_low)
         signal = SIGNAL_SELL;
      if(signal == SIGNAL_NONE || m_trend <= 0)
         return signal;

      double trend[], close[];
      if(CopyBuffer(m_trendHandle, 0, 1, 1, trend) != 1 || CopyClose(m_symbol, m_tf, 1, 1, close) != 1)
         return SIGNAL_NONE;
      bool up = close[0] > trend[0];
      return (signal == SIGNAL_BUY) == up ? signal : SIGNAL_NONE;
     }

   virtual string    Name(void) override { return StringFormat("RsiRevert(%d, %.0f, %d)", m_period, m_low, m_trend); }
  };

//+------------------------------------------------------------------+
//| Fast EMA crosses slow EMA -> trade in the cross direction.       |
//+------------------------------------------------------------------+
class CEmaCross : public CStrategy
  {
private:
   int               m_fastHandle;
   int               m_slowHandle;
   int               m_fast;
   int               m_slow;
public:
                     CEmaCross(const int fast, const int slow) : m_fastHandle(INVALID_HANDLE), m_slowHandle(INVALID_HANDLE), m_fast(fast), m_slow(slow) {}
                    ~CEmaCross(void)
     {
      if(m_fastHandle != INVALID_HANDLE) IndicatorRelease(m_fastHandle);
      if(m_slowHandle != INVALID_HANDLE) IndicatorRelease(m_slowHandle);
     }

   virtual bool      Init(const string symbol, const ENUM_TIMEFRAMES tf) override
     {
      CStrategy::Init(symbol, tf);
      if(m_fast >= m_slow)
         return false;
      m_fastHandle = iMA(symbol, tf, m_fast, 0, MODE_EMA, PRICE_CLOSE);
      m_slowHandle = iMA(symbol, tf, m_slow, 0, MODE_EMA, PRICE_CLOSE);
      return m_fastHandle != INVALID_HANDLE && m_slowHandle != INVALID_HANDLE;
     }

   virtual int       Signal(void) override
     {
      double fast[], slow[];
      if(CopyBuffer(m_fastHandle, 0, 1, 2, fast) != 2 || CopyBuffer(m_slowHandle, 0, 1, 2, slow) != 2)
         return SIGNAL_NONE;
      if(fast[1] > slow[1] && fast[0] <= slow[0])
         return SIGNAL_BUY;
      if(fast[1] < slow[1] && fast[0] >= slow[0])
         return SIGNAL_SELL;
      return SIGNAL_NONE;
     }

   virtual string    Name(void) override { return StringFormat("EmaCross(%d, %d)", m_fast, m_slow); }
  };
//+------------------------------------------------------------------+
