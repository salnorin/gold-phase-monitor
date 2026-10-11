# core/organism.py

from typing import Optional, Tuple
import pandas as pd

from core.motor_engine import MetabolicMotorSystem
from core.optical_engine import OpticalSystem
from core.immune_engine import ImmuneAndStressSystem
from core.respiration_engine import RespirationEngine
from core.ai_analyst import BiologicalAIAnalyst
from core.morphogenesis import MorphogenesisManager


class BiologicalOrganism:
    """ارگانیسم زنده و خودتکامل‌یابنده طلا"""

    def __init__(self):
        # ارگان‌های اصلی
        self.motor = MetabolicMotorSystem()
        self.optical = OpticalSystem()
        self.immune = ImmuneAndStressSystem()
        self.respiration = RespirationEngine()
        self.morphogenesis = MorphogenesisManager()

        # وضعیت حیاتی
        self.generation = 1
        self.performance_history = []
        self.memory = []

    def perceive_and_process(self) -> Optional[pd.DataFrame]:
        """
        چرخه کامل ادراک و پردازش:
        داده خام → موتور → بینایی → ایمنی → تنفس و سیگنال → ارگان‌های تکامل‌یافته
        """

        # ۱. دریافت داده خام
        df = self.respiration.fetch_raw_data()
        if df is None or df.empty:
            return None

        # ۲. سیستم حرکتی و انرژی (ATP)
        df = self.motor.calculate_motor_drive(df)

        # ۳. سیستم بینایی نوری
        df = self.optical.calculate_optical_field(df)

        # ۴. سیستم ایمنی و استرس
        df = self.immune.evaluate_toxicity_and_stress(df)

        # ۵. تنفس + تولید سیگنال‌ها (Long / Short)
        df = self.respiration.calculate_breathing_and_signals(df)

        # ۶. اجرای ارگان‌هایی که قبلاً متولد شدن
        organ_results = self.morphogenesis.run_all_organs(df)
        for name, result in organ_results.items():
            if isinstance(result, dict):
                for col, values in result.items():
                    df[col] = values

        return df

    def think(self, latest_row: pd.Series) -> str:
        """تصمیم‌گیری توسط مغز"""
        return BiologicalAIAnalyst.generate_diagnostic(latest_row)

    def evaluate_performance(self, df: pd.DataFrame) -> float:
        """محاسبه نرخ موفقیت سیگنال‌های اخیر"""
        if "Signal_Success" not in df.columns or "Signal_Attempted" not in df.columns:
            return 0.5

        recent = df[df["Signal_Attempted"] == 1].tail(20)
        if recent.empty:
            return 0.5

        win_rate = recent["Signal_Success"].mean()
        self.performance_history.append(float(win_rate))
        return float(win_rate)

    def evolve_if_needed(self, win_rate: float) -> None:
        """اگر عملکرد ضعیف بود، تکامل پیدا کن"""
        if len(self.performance_history) < 5:
            return

        recent_avg = sum(self.performance_history[-5:]) / 5

        if recent_avg < 0.40:
            self.generation += 1
            print(f"🧬 نسل {self.generation} | عملکرد اخیر: {recent_avg:.1%} → شروع تکامل")

            organ_code = '''
from core.base_organ import BaseOrgan
import pandas as pd

class MomentumFilterOrgan(BaseOrgan):
    def __init__(self):
        super().__init__("MomentumFilterOrgan")

    def process(self, market_data):
        df = market_data.copy()
        df["Momentum_Score"] = df["Close"].pct_change(5)
        df["Strong_Momentum"] = df["Momentum_Score"].abs() > 0.008
        return {
            "Momentum_Score": df["Momentum_Score"],
            "Strong_Momentum": df["Strong_Momentum"]
        }
'''
            try:
                self.morphogenesis.spawn_new_organ("MomentumFilterOrgan", organ_code)
                print("✅ ارگان جدید با موفقیت متولد شد.")
            except Exception as e:
                print(f"❌ خطا در تکامل: {e}")

    def live_cycle(self) -> Tuple[Optional[pd.DataFrame], str]:
        """یک چرخه کامل زندگی ارگانیسم"""
        df = self.perceive_and_process()

        if df is None or df.empty:
            return None, "داده‌ای دریافت نشد."

        latest = df.iloc[-1]
        decision = self.think(latest)
        win_rate = self.evaluate_performance(df)
        self.evolve_if_needed(win_rate)

        return df, decision
