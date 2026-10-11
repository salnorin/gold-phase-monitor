# core/bloodstream.py
"""جریان خون: حالت داخلی مشترکی که ارگان‌ها در هر کندل در آن می‌نویسند و از آن می‌خوانند."""
from dataclasses import dataclass, field, asdict


@dataclass
class Bloodstream:
    atp: float = 100.0
    cortisol: float = 10.0
    effective_atp: float = 100.0
    effective_cortisol: float = 10.0
    fatigue: float = 0.0
    sleeping_bars: int = 0
    consecutive_losses: int = 0
    votes: dict = field(default_factory=dict)      # رأی جهت‌دار هر ارگان در [-1, 1]
    weights: dict = field(default_factory=dict)    # وزن یادگرفته‌شده هر ارگان
    performance: dict = field(default_factory=dict)  # EWMA عملکرد (بر حسب R)
    score: float = 0.0
    confidence: float = 0.0
    signal: str = "FLAT"
    reason: str = ""

    def snapshot(self) -> dict:
        d = asdict(self)
        d["votes"] = dict(self.votes); d["weights"] = dict(self.weights)
        d["performance"] = dict(self.performance)
        return d
