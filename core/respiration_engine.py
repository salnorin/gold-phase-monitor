# core/respiration_engine.py
"""سیستم تنفسی: فقط از داده‌های تا کندل بسته‌شده‌ی فعلی استفاده می‌کند (بدون نگاه به آینده)."""
from core.data_feeder import DataFeeder
import numpy as np
import pandas as pd


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=1).mean()


class RespirationEngine:
    def __init__(self, provider: str = "yfinance", api_key: str = None, atr_period: int = 14):
        self.feeder = DataFeeder(provider=provider, api_key=api_key)
        self.atr_period = atr_period

    def fetch_raw_data(self, symbol="GC=F", interval="1h", lookback_days=60):
        return self.feeder.fetch(symbol=symbol, interval=interval, lookback_days=lookback_days)

    @staticmethod
    def _causal_fill(df: pd.DataFrame) -> pd.DataFrame:
        """فقط ffill (گذشته → حال)؛ bfill حذف شد چون آینده را به گذشته نشت می‌داد."""
        df = df.copy()
        for col in df.columns:
            s = df[col]
            if s.dtype == bool:
                df[col] = s.fillna(False)
            else:
                df[col] = s.ffill().fillna(0)
        return df

    def process_respiration(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return None
        df = df.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, utc=True).tz_convert("America/New_York")

        df["Returns"] = df["Close"].pct_change()
        df["Log_Return"] = np.log(df["Close"] / df["Close"].shift(1))
        df["Volatility_Breath"] = df["Log_Return"].rolling(10, min_periods=2).std() * 100
        df["Breath_Radius"] = (df["High"] - df["Low"]) / df["Close"].replace(0, np.nan) * 1000
        df["ATR"] = compute_atr(df, self.atr_period)

        hour = df.index.hour
        df["Session_Entropy"] = np.where(hour < 8, 0.7, np.where(hour < 13, 1.2, 1.4))

        # میانگین «در حال گسترش» به‌جای میانگین کل سری (که آینده را می‌دید)
        mean_vol = df["Volatility_Breath"].expanding(min_periods=2).mean().replace(0, np.nan)
        df["Weighted_Breath"] = (df["Volatility_Breath"] / mean_vol * df["Session_Entropy"]).fillna(1.0)

        df["Theta"] = df["Returns"].fillna(0).cumsum() * 50

        baseline = df["Weighted_Breath"].rolling(40, min_periods=1).mean()
        df["Is_Asleep"] = df["Weighted_Breath"] < baseline * 0.75
        df["Sleep_Streak"] = df["Is_Asleep"].astype(int).groupby((~df["Is_Asleep"]).cumsum()).cumsum()

        # تب ویروسی: کندل قبلی اوج تنفس + حجم بالا بود و کندل فعلی (بسته‌شده) فروکش کرد.
        # قبلاً از shift(-1) یعنی کندل بعدی استفاده می‌شد = نگاه به آینده.
        vol_ma = df["Volume"].rolling(20, min_periods=1).mean()
        high_th = df["Weighted_Breath"].rolling(200, min_periods=20).quantile(0.85)
        prev_breath = df["Weighted_Breath"].shift(1)
        spike_prev = (prev_breath > high_th.shift(1)) & (df["Volume"].shift(1) > vol_ma.shift(1) * 1.5)
        df["Viral_Fever"] = (spike_prev & (df["Weighted_Breath"] < prev_breath * 0.85)).fillna(False)
        df["Slaughter_Zone"] = df["Viral_Fever"]

        df["Long_Zone"] = (
            df["Is_Asleep"].shift(1, fill_value=False)
            & (df["Weighted_Breath"] > baseline)
            & (df["Theta"].diff() > 0)
        ).fillna(False)

        df = self._causal_fill(df)
        return df.dropna(subset=["Close"])

    def fetch_and_process(self, symbol="GC=F", interval="1h", lookback_days=60):
        df = self.fetch_raw_data(symbol=symbol, interval=interval, lookback_days=lookback_days)
        return None if df is None else self.process_respiration(df)
