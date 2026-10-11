import numpy as np
import pandas as pd


class OpticalSystem:
  """
  سیستم اپتیکی (بینایی نوری ارگانیسم):
  نقدینگی‌های بازار را به صورت منابع نوری (فوتون‌های نقدینگی) در تاریکی می‌بیند.
  ارگانیسم به سمت این نورها کشش دارد (Phototaxis)، اما حرکت به سمت نور
  مستلزم داشتن انرژی کافی (ATP) و توان تنفسی است.
  """

  def __init__(self, vision_range=20):
    self.vision_range = vision_range

  def calculate_optical_field(self, df):
    n = len(df)
    light_intensity = np.zeros(n)
    optical_pull = np.zeros(
        n
    )  # بردار کشش نوری (مثبت به سمت نور بالا، منفی به سمت نور پایین)

    highs = df["High"].values
    lows = df["Low"].values
    volumes = df["Volume"].values
    closes = df["Close"].values
    atps = df.get(
        "ATP_Energy", pd.Series(100, index=df.index)
    ).values  # انرژی متصل از موتور

    for i in range(self.vision_range, n):
      # شناسایی نقاط نقدینگی (سقف‌ها و کف‌های حجمی به عنوان منابع نور در تاریکی)
      window_high = highs[i - self.vision_range : i]
      window_low = lows[i - self.vision_range : i]

      peak_resistance = np.max(window_high)  # منبع نور بالا (نقدینگی سقف)
      peak_support = np.min(window_low)  # منبع نور پایین (نقدینگی کف)

      current_price = closes[i]

      dist_to_res = peak_resistance - current_price
      dist_to_sup = current_price - peak_support

      # ضریب انرژی (ATP) ارگانیسم برای شنا کردن به سمت نور
      atps_val = atps[i] if i < len(atps) else 100.0
      atp_factor = atps_val / 100.0

      if atp_factor > 0.35:  # انرژی کافی برای شنا کردن به سمت نور وجود دارد
        if abs(dist_to_res) < abs(dist_to_sup):
          # کشش نوری به سمت نورِ بالا (نقدینگی سقف)
          optical_pull[i] = 1.0 * atp_factor
          light_intensity[i] = peak_resistance
        else:
          # کشش نوری به سمت نورِ پایین (نقدینگی کف)
          optical_pull[i] = -1.0 * atp_factor
          light_intensity[i] = peak_support
      else:
        # خستگی مفرط و کمبود ATP: ارگانیسم نمی‌تواند به سمت نورهای دور شنا کند (توقف نوری / استراحت)
        optical_pull[i] = 0.0
        light_intensity[i] = current_price

    df["Optical_Light_Source"] = light_intensity
    df["Optical_Pull"] = optical_pull
    return df
    
