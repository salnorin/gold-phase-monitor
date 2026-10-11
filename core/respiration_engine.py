# core/respiration_engine.py
from core.data_feeder import DataFeeder
import numpy as np
import pandas as pd


class RespirationEngine:
  """سیستم تنفسی ارگانیسم (تنظیم نوسان، ریتم بازار و دریافت داده)"""

  def __init__(self, provider: str = "yfinance", api_key: str = None):
    self.feeder = DataFeeder(provider=provider, api_key=api_key)

  def fetch_raw_data(
      self, symbol: str = "GC=F", interval: str = "1h", lookback_days: int = 60
  ) -> pd.DataFrame:
    """دریافت داده‌های خام از لایه DataFeeder"""
    return self.feeder.fetch(
        symbol=symbol, interval=interval, lookback_days=lookback_days
    )

  def process_respiration(self, df: pd.DataFrame) -> pd.DataFrame:
    """محاسبه تنفس، بازه‌ها و هموستاتیک نوسانات بازار"""
    if df is None or df.empty:
      return None

    df = df.copy()
    # محاسبه بازدهی لگاریتمی و نوسان ریتمیک (تنفس ارگانیسم)
    df["Log_Return"] = np.log(df["Close"] / df["Close"].shift(1))
    df["Volatility_Breath"] = df["Log_Return"].rolling(window=10).std() * 100

    # میانگین موزون تنفس (Weighted Breath)
    mean_vol = df["Volatility_Breath"].mean()
    if pd.isna(mean_vol) or mean_vol == 0:
      df["Weighted_Breath"] = 1.0
    else:
      df["Weighted_Breath"] = df["Volatility_Breath"] / mean_vol

    df.fillna(method="bfill", inplace=True)
    df.fillna(0, inplace=True)
    return df

  def fetch_and_process(
      self, symbol: str = "GC=F", interval: str = "1h", lookback_days: int = 60
  ) -> pd.DataFrame:
    """متد ترکیبی برای دریافت و تنفس هم‌زمان"""
    df = self.fetch_raw_data(
        symbol=symbol, interval=interval, lookback_days=lookback_days
    )
    if df is None:
      return None
    return self.process_respiration(df)
