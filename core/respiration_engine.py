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
        """محاسبه تنفس، بازه‌ها، سیگنال‌ها و هموستاتیک نوسانات بازار"""
        if df is None or df.empty:
            return None

        df = df.copy()

        # محاسبه بازدهی و نوسان
        df["Returns"] = df["Close"].pct_change()
        df["Log_Return"] = np.log(df["Close"] / df["Close"].shift(1))
        df["Volatility_Breath"] = df["Log_Return"].rolling(window=10).std() * 100

        # Breath_Radius (نسخه ساده‌شده بر اساس نوسان)
        base_volatility = (df["High"] - df["Low"]) / df["Close"]
        df["Breath_Radius"] = base_volatility * 1000

        # Session Entropy
        df["Hour"] = df.index.hour
        df["Session_Entropy"] = np.where(
            (df["Hour"] >= 0) & (df["Hour"] < 8),
            0.7,
            np.where((df["Hour"] >= 8) & (df["Hour"] < 13), 1.2, 1.4),
        )

        # Weighted Breath
        mean_vol = df["Volatility_Breath"].mean()
        if pd.isna(mean_vol) or mean_vol == 0:
            df["Weighted_Breath"] = 1.0
        else:
            df["Weighted_Breath"] = (df["Volatility_Breath"] / mean_vol) * df["Session_Entropy"]

        # Theta momentum
        df["Theta"] = df["Returns"].cumsum() * 50

        # Sleep / Recovery
        baseline = df["Weighted_Breath"].rolling(window=40, min_periods=1).mean()
        df["Is_Asleep"] = df["Weighted_Breath"] < (baseline * 0.75)
        df["Sleep_Streak"] = (
            df["Is_Asleep"].groupby((~df["Is_Asleep"]).cumsum()).cumsum()
        )

        # Viral Fever / Slaughter Zone (Short)
        vol_ma = df["Volume"].rolling(window=20, min_periods=1).mean()
        high_th = df["Weighted_Breath"].quantile(0.85)

        df["Viral_Fever"] = (
            (df["Weighted_Breath"] > high_th)
            & (df["Volume"] > vol_ma * 1.5)
            & (df["Weighted_Breath"].shift(-1) < df["Weighted_Breath"] * 0.85)
        )
        df["Slaughter_Zone"] = df["Viral_Fever"].fillna(False)

        # Long Zone
        df["Long_Zone"] = (
            (df["Is_Asleep"].shift(1) == True)
            & (df["Weighted_Breath"] > baseline)
            & (df["Theta"].diff() > 0)
        ).fillna(False)

        # Signal tracking
        df["Signal_Attempted"] = np.where(df["Slaughter_Zone"] | df["Long_Zone"], 1, 0)

        # Target & Stop
        df["Target_Price"] = np.where(
            df["Slaughter_Zone"],
            df["Close"] - (df["Weighted_Breath"] * 1.5),
            np.where(df["Long_Zone"], df["Close"] + (df["Weighted_Breath"] * 1.5), 0),
        )
        df["Stop_Loss"] = np.where(
            df["Slaughter_Zone"],
            df["High"] + (df["Close"] * 0.003),
            np.where(df["Long_Zone"], df["Low"] - (df["Close"] * 0.003), 0),
        )

        # Simple success approximation
        df["Future_Return_5C"] = df["Close"].shift(-5) - df["Close"]
        df["Signal_Success"] = np.where(
            (df["Slaughter_Zone"] & (df["Future_Return_5C"] < 0))
            | (df["Long_Zone"] & (df["Future_Return_5C"] > 0)),
            1,
            0,
        )

        df = df.bfill()
        df = df.fillna(0)
        df.dropna(subset=["Close"], inplace=True)
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
        
