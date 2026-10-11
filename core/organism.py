# core/organism.py
from core.brain import Brain
from core.config import OrganismConfig, DEFAULT_CONFIG
from core.immune_engine import ImmuneAndStressSystem
from core.motor_engine import MetabolicMotorSystem
from core.optical_engine import OpticalSystem
from core.respiration_engine import RespirationEngine


class BiologicalOrganism:
    """ارگانیسم طلا (نسخه ۲): ارگان‌ها → جریان خون → مغز تطبیقی."""

    def __init__(self, provider="yfinance", api_key=None, config: OrganismConfig = DEFAULT_CONFIG):
        self.cfg = config
        self.respiration = RespirationEngine(provider=provider, api_key=api_key, atr_period=config.atr_period)
        self.motor = MetabolicMotorSystem()
        self.optical = OpticalSystem()
        self.immune = ImmuneAndStressSystem()
        self.brain = None
        self.trades = []

    def build_features(self, raw):
        df = self.respiration.process_respiration(raw)
        if df is None or df.empty:
            return None
        df = self.motor.calculate_motor_drive(df)
        df = self.optical.calculate_optical_field(df)
        return self.immune.evaluate_toxicity_and_stress(df)

    def live_cycle(self, symbol=None, interval=None, lookback_days=None):
        c = self.cfg
        raw = self.respiration.fetch_raw_data(symbol or c.symbol, interval or c.interval, lookback_days or c.lookback_days)
        if raw is None or raw.empty:
            return None, "خطا: ارگانیسم نتوانست داده‌ای دریافت کند."
        df = self.build_features(raw)
        if df is None:
            return None, "خطا: داده کافی نیست."
        self.brain = Brain(c)
        df, self.trades = self.brain.run(df)
        return df, self.brain.explain()
