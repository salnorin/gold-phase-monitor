from datetime import datetime
import numpy as np
import pandas as pd
import yfinance as yf


class RespirationEngine:

  def __init__(self, ticker='GC=F', period='60d', interval='1h'):
    self.ticker = ticker
    self.period = period
    self.interval = interval

  def fetch_and_process(self):
    try:
      raw = yf.download(
          self.ticker,
          period=self.period,
          interval=self.interval,
          progress=False,
      )
      if raw.empty:
        return None

      df = pd.DataFrame()
      df['Open'] = raw['Open'].iloc[:, 0]
      df['High'] = raw['High'].iloc[:, 0]
      df['Low'] = raw['Low'].iloc[:, 0]
      df['Close'] = raw['Close'].iloc[:, 0]
      df['Volume'] = raw['Volume'].iloc[:, 0]

      # ۱. شعاع تنفسی (Breath Radius)
      df['Volatility'] = (df['High'] - df['Low']) / df['Close']
      df['Breath_Radius'] = df['Volatility'].rolling(window=12).mean() * 1000

      # ۲. مومنتوم زاویه‌ای (Theta)
      df['Returns'] = df['Close'].pct_change()
      df['Theta'] = df['Returns'].cumsum() * 50
      df['Z_Time'] = np.arange(len(df))

      # ۳. فاز خواب ارگانیسم
      radius_baseline = df['Breath_Radius'].rolling(window=40).mean()
      df['Is_Asleep'] = df['Breath_Radius'] < (radius_baseline * 0.75)

      # ۴. منطقه کشتار نهنگ‌ها (Short) و جهش انباشت (Long)
      high_radius = df['Breath_Radius'].quantile(0.85)
      avg_vol = df['Volume'].rolling(window=20).mean()

      df['Slaughter_Zone'] = (
          (df['Breath_Radius'] > high_radius)
          & (df['Volume'] > avg_vol * 1.3)
          & (df['Close'] > df['Open'])
      )

      df['Long_Zone'] = (df['Is_Asleep'].shift(1) == True) & (
          df['Breath_Radius'] > radius_baseline
      ) & (df['Theta'].diff() > 0)

      # ۵. سطوح هدف و حد ضرر
      df['Target_Price'] = np.where(
          df['Slaughter_Zone'],
          df['Close'] - (df['Breath_Radius'] * 1.8),
          np.where(
              df['Long_Zone'], df['Close'] + (df['Breath_Radius'] * 1.8), 0
          ),
      )
      df['Stop_Loss'] = np.where(
          df['Slaughter_Zone'],
          df['High'] + (df['Close'] * 0.0035),
          np.where(df['Long_Zone'], df['Low'] - (df['Close'] * 0.0035), 0),
      )

      # ۶. اعتبارسنجی سودآوری
      df['Future_Return_5C'] = df['Close'].shift(-5) - df['Close']
      df['Signal_Success'] = np.where(
          (df['Slaughter_Zone'] & (df['Future_Return_5C'] < 0))
          | (df['Long_Zone'] & (df["Future_Return_5C"] > 0)),
          1,
          0,
      )
      df['Signal_Attempted'] = np.where(
          df['Slaughter_Zone'] | df['Long_Zone'], 1, 0
      )

      df.dropna(subset=['Close', 'Volume'], inplace=True)
      return df
    except Exception:
      return None

  def is_market_open(self, latest_time):
    now_utc = pd.Timestamp.now(tz='UTC')
    latest_dt = (
        pd.Timestamp(latest_time).tz_localize('UTC')
        if latest_time.tzinfo is None
        else pd.Timestamp(latest_time).tz_convert('UTC')
    )
    return ((now_utc - latest_dt).total_seconds() / 3600) < 4
