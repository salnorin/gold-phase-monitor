import numpy as np
import pandas as pd


class MetabolicMotorSystem:
    """
    موتور متابولیک. ATP مقیاس‌مستقل است: هزینه‌ی انرژی نسبت به نوسان «عادی» گذشته
    (میانه‌ی ۱۰۰ کندل قبلی) سنجیده می‌شود، و بدن همیشه کمی به سمت تعادل ریکاوری می‌کند.
    (نسخه‌ی قبلی با قیمت ~۴۰۰۰ دلار تقریباً همیشه در کف ۸٪ گیر می‌کرد.)
    """

    def __init__(self, base_atp=100.0, recovery=4.0, vol_cost=3.0, volume_cost=1.0):
        self.base_atp, self.recovery, self.vol_cost, self.volume_cost = base_atp, recovery, vol_cost, volume_cost

    def calculate_motor_drive(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        rng = (df["High"] - df["Low"]) / df["Close"]
        normal = rng.shift(1).rolling(100, min_periods=10).median()
        rel_vol = (rng / normal).fillna(1.0).clip(0, 6).values
        volf = (df["Volume"] / df["Volume"].shift(1).rolling(20, min_periods=1).mean()).fillna(1.0).clip(0, 5).values
        ret = df["Close"].pct_change().fillna(0)
        ret_sd = ret.shift(1).rolling(50, min_periods=10).std().replace(0, np.nan)
        z = (ret / ret_sd).fillna(0).values

        n = len(df)
        atp = np.full(n, self.base_atp)
        drive = np.zeros(n)
        cur = self.base_atp
        for i in range(1, n):
            cur += self.recovery - self.vol_cost * rel_vol[i] - self.volume_cost * max(0.0, volf[i] - 1)
            cur = float(np.clip(cur, 8.0, 100.0))
            atp[i] = cur
            drive[i] = np.tanh(z[i] / 2) * (cur / 100.0)
        df["ATP_Energy"] = atp
        df["Motor_Drive"] = drive
        return df
