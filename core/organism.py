# core/organism.py
from core.ai_analyst import BiologicalAIAnalyst
from core.immune_engine import ImmuneAndStressSystem
from core.morphogenesis import MorphogenesisManager
from core.motor_engine import MetabolicMotorSystem
from core.optical_engine import OpticalSystem
from core.respiration_engine import RespirationEngine
import pandas as pd
from typing import Optional, Tuple


class BiologicalOrganism:
    """ارگانیسم زنده و خودتکامل‌یابنده طلا (نسخه‌ی یکپارچه)"""

    def __init__(self, provider: str = "yfinance", api_key: str = None):
        self.respiration = RespirationEngine(provider=provider, api_key=api_key)
        self.motor = MetabolicMotorSystem()
        self.optical = OpticalSystem()
        self.immune = ImmuneAndStressSystem()
        self.morphogenesis = MorphogenesisManager()
        self.generation = 1
        self.performance_history = []

    def update_provider(self, provider: str, api_key: str = None):
        """بروزرسانی منبع داده"""
        self.respiration = RespirationEngine(provider=provider, api_key=api_key)

    def perceive_and_process(
        self, symbol: str = "GC=F", interval: str = "1h", lookback_days: int = 60
    ) -> Optional[pd.DataFrame]:
        """چرخه حیاتی کامل: تنفس → موتور → بینایی → ایمنی → ارگان‌های تکامل‌یافته"""
        # ۱. تنفس و دریافت داده
        df = self.respiration.fetch_and_process(
            symbol=symbol, interval=interval, lookback_days=lookback_days
        )
        if df is None or df.empty:
            return None

        # ۲. موتور و انرژی ATP
        df = self.motor.calculate_motor_drive(df)

        # ۳. بینایی نوری (Optical Field)
        df = self.optical.calculate_optical_field(df)

        # ۴. سیستم ایمنی و کورتیزول
        df = self.immune.evaluate_toxicity_and_stress(df)

        # ۵. اجرای ارگان‌های دینامیک (اگر وجود داشته باشن)
        organ_results = self.morphogenesis.run_all_organs(df)
        for name, result in organ_results.items():
            if isinstance(result, dict):
                for col, values in result.items():
                    df[col] = values

        return df

    def think(self, latest_row) -> str:
        """تصمیم‌گیری مغز مرکزی"""
        return BiologicalAIAnalyst.generate_diagnostic(latest_row)

    def live_cycle(
        self, symbol: str = "GC=F", interval: str = "1h", lookback_days: int = 60
    ) -> Tuple[Optional[pd.DataFrame], str]:
        """اجرای یک دور کامل زندگی ارگانیسم"""
        df = self.perceive_and_process(
            symbol=symbol, interval=interval, lookback_days=lookback_days
        )
        if df is None or df.empty:
            return None, "خطا: ارگانیسم نتوانست داده‌ای دریافت کند."

        latest = df.iloc[-1]
        decision = self.think(latest)
        return df, decision
