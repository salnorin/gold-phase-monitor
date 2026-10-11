import numpy as np
import pandas as pd

class MetabolicMotorSystem:
    def __init__(self):
        self.base_atp = 100.0

    def calculate_motor_drive(self, df: pd.DataFrame) -> pd.DataFrame:
        n = len(df)
        atp = np.full(n, self.base_atp, dtype=float)
        motor_drive = np.zeros(n)

        closes = df["Close"].values
        highs = df["High"].values
        lows = df["Low"].values
        volumes = df["Volume"].values

        vol_ma = pd.Series(volumes).rolling(20, min_periods=1).mean().values
        returns = pd.Series(closes).pct_change().fillna(0).values

        current_atp = self.base_atp

        for i in range(1, n):
            volatility = (highs[i] - lows[i]) / (closes[i] + 1e-9)
            volume_factor = volumes[i] / (vol_ma[i] + 1e-9)

            energy_cost = (volatility * 70) + (min(volume_factor, 5) * 2.5)
            current_atp = max(8.0, current_atp - energy_cost)

            if volatility < 0.0028 and volume_factor < 1.3:
                current_atp = min(100.0, current_atp + 3.8)

            atp[i] = current_atp
            momentum = returns[i] * 80
            motor_drive[i] = np.tanh(momentum) * (current_atp / 100.0)

        df = df.copy()
        df["ATP_Energy"] = atp
        df["Motor_Drive"] = motor_drive
        return df
