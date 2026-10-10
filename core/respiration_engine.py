from core.motor_engine import MetabolicMotorSystem
from core.optical_engine import OpticalSystem
import numpy as np
import pandas as pd
import yfinance as yf


class HomeostaticReceptorNetwork:

  def __init__(self):
    self.homeostatic_bias = 0.0
    self.error_memory = []

  def receive_feedback(self, success):
    self.error_memory.append(0 if success == 1 else 1)
    if len(self.error_memory) > 10:
      self.error_memory.pop(0)
    error_rate = (
        sum(self.error_memory) / len(self.error_memory)
        if self.error_memory
        else 0.0
    )
    self.homeostatic_bias = error_rate * 0.2


class RespirationEngine:

  def __init__(self, ticker="GC=F", period="60d", interval="1h"):
    self.ticker = ticker
    self.period = period
    self.interval = interval
    self.motor_system = MetabolicMotorSystem()
    self.optical_system = OpticalSystem()
    self.receptor_network = HomeostaticReceptorNetwork()

  def fetch_and_process(self):
    try:
      raw = yf.download(
          self.ticker,
          period=self.period,
          interval=self.interval,
          progress=False,
      )
      if raw.empty:
        return None

      df = pd.DataFrame()
      df["Open"] = raw["Open"].iloc[:, 0]
      df["High"] = raw["High"].iloc[:, 0]
      df["Low"] = raw["Low"].iloc[:, 0]
      df["Close"] = raw["Close"].iloc[:, 0]
      df["Volume"] = (
          raw.get("Volume", pd.Series(0, index=raw.index))
          .iloc[:, 0]
      )

      # ۱. اجرای سیستم حرکتی (موتور و انرژی ATP)
      df = self.motor_system.calculate_motor_drive(df)

      # ۲. اجرای سیستم اپتیکی (دیدن نقدینگی به شکل نور و کشش نوری بر اساس ATP)
      df = self.optical_system.calculate_optical_field(df)

      # ۳. ریه و تنفس (تحت تاثیر موتور، کشش نوری و اکسیژن)
      base_volatility = (df["High"] - df["Low"]) / df["Close"]
      df["Breath_Radius"] = (
          base_volatility * 1000
          + (df["Motor_Drive"] * 5.0)
          + (abs(df["Optical_Pull"]) * 3.0)
      )

      # ۴. آنتروپی سشن‌ها
      df["Hour"] = df.index.hour
      df["Session_Entropy"] = np.where(
          (df["Hour"] >= 0) & (df["Hour"] < 8),
          0.7,
          np.where((df["Hour"] >= 8) & (df["Hour"] < 13), 1.2, 1.4),
      )

      df["Weighted_Breath"] = (
          df["Breath_Radius"] * df["Session_Entropy"]
      ) * (1.0 - self.receptor_network.homeostatic_bias)

      # ۵. مومنتوم تتا
      df["Returns"] = df["Close"].pct_change()
      df["Theta"] = df["Returns"].cumsum() * 50

      # ۶. فاز خواب و ریکاوری ATP
      baseline = df["Weighted_Breath"].rolling(window=40).mean()
      df["Is_Asleep"] = df["Weighted_Breath"] < (baseline * 0.75)
      df["Sleep_Streak"] = (
          df["Is_Asleep"]
          .groupby((~df["Is_Asleep"]).cumsum())
          .cumsum()
      )

      # ۷. تب ویروسی و مناطق عملیاتی
      vol_ma = df["Volume"].rolling(window=20).mean()
      high_th = df["Weighted_Breath"].quantile(0.85)

      df["Viral_Fever"] = (
          (df["Weighted_Breath"] > high_th)
          & (df["Volume"] > vol_ma * 1.5)
          & (df["Weighted_Breath"].shift(-1)
             < df["Weighted_Breath"] * 0.85)
      )

      df["Slaughter_Zone"] = df["Viral_Fever"]
      df["Long_Zone"] = (df["Is_Asleep"].shift(1) == True) & (
          df["Weighted_Breath"] > baseline
      ) & (df["Theta"].diff() > 0)

      df["Signal_Attempted"] = np.where(
          df["Slaughter_Zone"] | df["Long_Zone"], 1, 0
      )

      # ۸. سطوح قیمت و هدف‌گذاری
      df["Target_Price"] = np.where(
          df["Slaughter_Zone"],
          df["Close"] - (df["Weighted_Breath"] * 1.5),
          np.where(
              df["Long_Zone"], df["Close"] + (df["Weighted_Breath"] * 1.5), 0
          ),
      )
      df["Stop_Loss"] = np.where(
          df["Slaughter_Zone"],
          df["High"] + (df["Close"] * 0.003),
          np.where(df["Long_Zone"], df["Low"] - (df["Close"] * 0.003), 0),
      )

      # ۹. فیدبک منفی
      df["Future_Return_5C"] = df["Close"].shift(-5) - df["Close"]
      df["Signal_Success"] = np.where(
          (df["Slaughter_Zone"] & (df["Future_Return_5C"] < 0))
          | (df["Long_Zone"] & (df["Future_Return_5C"] > 0)),
          1,
          0,
      )

      valid_df = df[df["Signal_Attempted"] == 1]
      if not valid_df.empty:
        self.receptor_network.receive_feedback(
            valid_df["Signal_Success"].iloc[-1]
        )

      df.dropna(subset=["Close"], inplace=True)
      return df
    except Exception:
      return None

  def is_market_open(self, latest_time):
    now_utc = pd.Timestamp.now(tz="UTC")
    latest_dt = (
        pd.Timestamp(latest_time).tz_localize("UTC")
        if latest_time.tzinfo is None
        else pd.Timestamp(latest_time).tz_convert("UTC")
    )
    return ((now_utc - latest_dt).total_seconds() / 3600) < 4
    
