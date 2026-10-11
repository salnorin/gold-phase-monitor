# core/legacy.py
"""منطق قدیمی (نسخه ۱) فقط برای مقایسه در بک‌تست. دارای نگاه به آینده است؛ استفاده‌ی زنده نشود."""
import numpy as np
import pandas as pd


def legacy_signals(df: pd.DataFrame) -> pd.DataFrame:
    """df باید ستون‌های موتور/اپتیک/ایمنی را داشته باشد. ورودی خام OHLCV + آن ستون‌ها."""
    df = df.copy()
    lr = np.log(df["Close"] / df["Close"].shift(1))
    vb = lr.rolling(10).std() * 100
    ent = np.where(df.index.hour < 8, 0.7, np.where(df.index.hour < 13, 1.2, 1.4))
    wb = vb / vb.mean() * ent                          # میانگین کل سری (آینده)
    theta = df["Close"].pct_change().cumsum() * 50
    base = wb.rolling(40, min_periods=1).mean()
    asleep = wb < base * 0.75
    vol_ma = df["Volume"].rolling(20, min_periods=1).mean()
    fever = (wb > wb.quantile(0.85)) & (df["Volume"] > vol_ma * 1.5) & (wb.shift(-1) < wb * 0.85)  # کندل بعدی!
    long_z = (asleep.shift(1) == True) & (wb > base) & (theta.diff() > 0)
    wb = wb.bfill().ffill()                            # نشت آینده
    atp, cort, opt = df["ATP_Energy"], df["Cortisol_Stress"], df["Optical_Pull"]
    d = np.zeros(len(df), dtype=int)
    for i in range(len(df)):
        if atp.iloc[i] < 30 or cort.iloc[i] > 75: continue
        if fever.iloc[i]: d[i] = -1
        elif long_z.iloc[i] and atp.iloc[i] > 35 and cort.iloc[i] < 60: d[i] = 1
        elif opt.iloc[i] > 0.4 and atp.iloc[i] > 40: d[i] = 1
        elif opt.iloc[i] < -0.4 and atp.iloc[i] > 40: d[i] = -1
    df["Legacy_Dir"] = d
    df["Legacy_Target"] = df["Close"] + d * wb * 1.5
    df["Legacy_Stop"] = np.where(d > 0, df["Low"] - df["Close"] * 0.003,
                                 np.where(d < 0, df["High"] + df["Close"] * 0.003, 0))
    return df
