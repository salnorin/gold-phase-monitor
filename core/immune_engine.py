import numpy as np
import pandas as pd


class ImmuneAndStressSystem:
  """
  سیستم ایمنی و استرس (Immune & Cortisol Stress System):
  وظیفه شناسایی پاتوژن‌ها (نویزهای مخرب، فیک‌بریک‌اوت‌ها) و تنظیم هورمون بقا (کورتیزول)
  در مواجهه با سنتیمنت سنگین و شوک‌های کلان بازار طلا را بر عهده دارد.
  """

  def __init__(self):
    self.cortisol_level = 10.0  # هورمون استرس و بقا (پایگاه آرامش)
    self.antibody_defense = 0.0  # سطح دفاعی سیستم ایمنی در برابر فریب نهنگ

  def evaluate_toxicity_and_stress(self, df):
    n = len(df)
    cortisol_arr = np.zeros(n)
    antibody_arr = np.zeros(n)
    stress_state_arr = np.array(
        ["CALM"] * n, dtype=object
    )

    closes = df["Close"].values
    volumes = df["Volume"].values
    vol_ma = df["Volume"].rolling(20).mean().fillna(1).values

    curr_cortisol = 10.0

    for i in range(20, n):
      # سنجش سميت و نویز حاد (تضاد حجم بالا با حرکت ناچیز قیمت = سموم پاتوژن)
      price_change = abs(closes[i] - closes[i - 1]) / closes[i - 1]
      volume_spike = volumes[i] / vol_ma[i]

      # اگر حجم منفجر شود اما قیمت حرکت درستی نکند یا برعکس (دستکاری و تله)
      is_pathogen_attack = (volume_spike > 2.0) and (price_change < 0.001)

      if is_pathogen_attack:
        # ترشح آنتی‌بادی و افزایش شدید کورتیزول (استرس و هشدار بقا)
        curr_cortisol = min(100.0, curr_cortisol + 35.0)
        antibody_defense = 1.0
        state = "PATHOGEN_ALERT"
      elif volume_spike > 3.0:
        # شوک کلان یا اخبار مهم
        curr_cortisol = min(100.0, curr_cortisol + 20.0)
        antibody_defense = 0.5
        state = "MACRO_SHOCK"
      else:
        # تخلیه تدریجی کورتیزول و آرامش سیستم
        curr_cortisol = max(5.0, curr_cortisol - 4.0)
        antibody_defense = 0.0
        state = "CALM"

      cortisol_arr[i] = curr_cortisol
      antibody_arr[i] = antibody_defense
      stress_state_arr[i] = state

    df["Cortisol_Stress"] = cortisol_arr
    df["Antibody_Defense"] = antibody_arr
    df["Stress_State"] = stress_state_arr
    return df
