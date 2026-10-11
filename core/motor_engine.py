import numpy as np
import pandas as pd


class MetabolicMotorSystem:
  """موتور حرکتی و مدیریت انرژی ATP و درایو حرکتی ارگانیسم"""

  @staticmethod
  def compute_motor_drive(df):
    closes = df["Close"].values
    n = len(df)
    atp_arr = np.zeros(n)
    drive_arr = np.zeros(n)

    curr_atp = 100.0

    for i in range(1, n):
      price_diff = closes[i] - closes[i - 1]
      volatility = abs(price_diff) / closes[i - 1]

      # مصرف انرژی بر اساس نوسان بازار
      curr_atp = max(10.0, curr_atp - (volatility * 500) + 2.0)

      atp_arr[i] = curr_atp
      drive_arr[i] = np.tanh(price_diff * 100) * (curr_atp / 100.0)

    df["ATP_Energy"] = atp_arr
    df["Motor_Drive"] = drive_arr
    return df
    
