# core/organism.py
from core.ai_analyst import BiologicalAIAnalyst
from core.immune_engine import ImmuneAndStressSystem
from core.morphogenesis import MorphogenesisManager
from core.motor_engine import MetabolicMotorSystem
from core.optical_engine import OpticalSystem
from core.respiration_engine import RespirationEngine
import pandas as pd


class BiologicalOrganism:
  """ارگانیسم زنده و خودتکامل‌یابنده طلا"""

  def __init__(self):
    self.motor = MetabolicMotorSystem()
    self.optical = OpticalSystem()
    self.respiration = RespirationEngine()
    self.immune = ImmuneAndStressSystem()
    self.morphogenesis = MorphogenesisManager()
    self.memory = []  # حافظه تجربیات
    self.generation = 1  # نسل فعلی
    self.performance_history = []

  def perceive_and_process(self) -> pd.DataFrame:
    """چرخه کامل زندگی: ادراک → پردازش → تصمیم"""
    # ۱. تنفس و دریافت داده خام
    df = self.respiration.fetch_and_process()
    if df is None or df.empty:
      return None

    # ۲. موتور و انرژی
    df = self.motor.calculate_motor_drive(df)

    # ۳. بینایی نوری
    df = self.optical.calculate_optical_field(df)

    # ۴. سیستم ایمنی و کورتیزول
    df = self.immune.evaluate_toxicity_and_stress(df)

    # ۵. اجرای ارگان‌های تکامل‌یافته (اگر وجود داشته باشن)
    organ_results = self.morphogenesis.run_all_organs(df)
    for name, result in organ_results.items():
      if isinstance(result, dict):
        for col, values in result.items():
          df[col] = values

    return df

  def think(self, latest_row) -> str:
    """تصمیم‌گیری توسط مغز"""
    return BiologicalAIAnalyst.generate_diagnostic(latest_row)

  def evaluate_performance(self, df: pd.DataFrame):
    """ارزیابی عملکرد برای تصمیم‌گیری در مورد تکامل"""
    if "Signal_Success" not in df.columns:
      return 0.5

    recent = df[df["Signal_Attempted"] == 1].tail(20)
    if recent.empty:
      return 0.5

    win_rate = recent["Signal_Success"].mean()
    self.performance_history.append(win_rate)
    return win_rate

  def evolve_if_needed(self, win_rate: float):
    """اگر عملکرد ضعیف بود، ارگان جدید متولد کن"""
    if len(self.performance_history) < 5:
      return

    recent_avg = sum(self.performance_history[-5:]) / 5

    # شرط تکامل: اگر عملکرد کمتر از ۴۰٪ بود
    if recent_avg < 0.40:
      self.generation += 1
      print(
          f"🧬 نسل {self.generation}: عملکرد ضعیف بود ({recent_avg:.1%}). شروع"
          " تکامل..."
      )

      # تولد یک ارگان جدید (فیلتر مومنتوم)
      organ_code = """
from core.base_organ import BaseOrgan
import pandas as pd

class MomentumFilterOrgan(BaseOrgan):
    def __init__(self):
        super().__init__("MomentumFilterOrgan")
    
    def process(self, market_data):
        df = market_data.copy()
        df["Momentum_Score"] = df["Close"].pct_change(5)
        df["Strong_Momentum"] = df["Momentum_Score"].abs() > 0.008
        return {"Momentum_Score": df["Momentum_Score"], "Strong_Momentum": df["Strong_Momentum"]}
"""
      try:
        self.morphogenesis.spawn_new_organ("MomentumFilterOrgan", organ_code)
        print("✅ ارگان جدید با موفقیت متولد و متصل شد.")
      except Exception as e:
        print(f"❌ خطا در تکامل: {e}")

  def live_cycle(self):
    """یک چرخه کامل زندگی ارگانیسم"""
    df = self.perceive_and_process()
    if df is None:
      return None, "داده‌ای دریافت نشد."

    latest = df.iloc[-1]
    decision = self.think(latest)
    win_rate = self.evaluate_performance(df)
    self.evolve_if_needed(win_rate)

    return df, decision
