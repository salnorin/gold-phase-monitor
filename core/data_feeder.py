import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os

class DataFeeder:
    """لایه دریافت داده - الان yfinance، بعداً راحت عوض می‌شه"""

    def __init__(self, symbol="GC=F", interval="1h", lookback_days=60):
        self.symbol = symbol
        self.interval = interval
        self.lookback_days = lookback_days

    def fetch(self) -> pd.DataFrame | None:
        try:
            end = datetime.now()
            start = end - timedelta(days=self.lookback_days)
            
            df = yf.download(
                self.symbol,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                interval=self.interval,
                progress=False,
                auto_adjust=True
            )

            if df.empty:
                return None

            # استانداردسازی ستون‌ها
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
            df.dropna(inplace=True)
            return df

        except Exception as e:
            print(f"[DataFeeder Error] {e}")
            return None
