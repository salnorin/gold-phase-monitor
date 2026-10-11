import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional
import os


class DataFeeder:
    def __init__(self, provider: str = "yfinance", api_key: Optional[str] = None):
        self.provider = provider.lower()
        self.api_key = api_key or os.getenv("GOLD_API_KEY")

        if self.provider not in ["yfinance", "goldprice"]:
            raise ValueError(f"Provider '{self.provider}' پشتیبانی نمی‌شود")

    def fetch(self, symbol: str = "GC=F", interval: str = "1h", lookback_days: int = 60) -> Optional[pd.DataFrame]:
        if self.provider == "yfinance":
            return self._fetch_yfinance(symbol, interval, lookback_days)
        elif self.provider == "goldprice":
            return self._fetch_goldprice(symbol, interval, lookback_days)
        return None

    def _fetch_yfinance(self, symbol: str, interval: str, lookback_days: int) -> Optional[pd.DataFrame]:
        try:
            end = datetime.now()
            start = end - timedelta(days=lookback_days)

            df = yf.download(
                symbol,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                interval=interval,
                progress=False,
                auto_adjust=True
            )

            if df.empty:
                return None

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.dropna(inplace=True)
            return df

        except Exception as e:
            print(f"[DataFeeder - yfinance Error] {e}")
            return None

    def _fetch_goldprice(self, symbol: str, interval: str, lookback_days: int) -> Optional[pd.DataFrame]:
        if not self.api_key:
            print("[DataFeeder] برای goldprice به API Key نیاز دارید.")
            return None

        print("[DataFeeder] goldprice هنوز کامل پیاده‌سازی نشده. از yfinance استفاده می‌شود.")
        return self._fetch_yfinance(symbol, interval, lookback_days)
