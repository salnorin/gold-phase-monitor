# core/max_wait.py
"""
انقضای انتظار (تصمیم کاربر، فقط کاغذی).
هر دور ضبط‌کننده (۱ دقیقه) که بازار باز، پوزیشنی باز نیست و تصمیم نهایی WAIT است، شمارنده +۱.
بعد از max_wait دور (GOLD_MAX_WAIT / --max-wait، پیش‌فرض 23): آستانه‌ی احتمال از exec_prob (۵۵٪) هر دور اضافه step (۱٪)
پایین می‌آید تا floor (GOLD_WAIT_FLOOR / --wait-floor، پیش‌فرض ۵۰٪). اگر احتمال صعود/نزول ≥ آستانه‌ی پایین‌آمده → اجرا؛
در کف، طرفی که احتمالش بیشتر است گرفته می‌شود. چنین معامله‌ای «forced» علامت می‌خورد.
بعد از هر سیگنال/معامله شمارنده صفر می‌شود. وتوهای سخت همیشه: بازار بسته/خواب/کهنه، توقف خودکار، استراحت اجباری،
حداکثر یک پوزیشن باز (forced هرگز پوزیشن را برنمی‌گرداند)، لیکوئیدیشن و SL/TP مبتنی بر ATR در core.paper.
"""
import os
from dataclasses import dataclass

from core.exec_prob import is_risk_veto


@dataclass
class WaitParams:
    max_wait: int = 23
    step: float = 0.01
    floor: float = 0.50
    start: float = 0.55

    @classmethod
    def from_env(cls, max_wait=None, floor=None, start=None, step=None):
        return cls(max_wait=int(max_wait if max_wait is not None else os.getenv("GOLD_MAX_WAIT", 23)),
                   floor=float(floor if floor is not None else os.getenv("GOLD_WAIT_FLOOR", 0.50)),
                   start=float(start if start is not None else os.getenv("GOLD_EXEC_PROB", 0.55)),
                   step=float(step if step is not None else os.getenv("GOLD_WAIT_STEP", 0.01)))


def threshold(count, wp):
    extra = count - wp.max_wait
    if extra <= 0:
        return None
    return max(wp.floor, wp.start - wp.step * extra)


def step_wait(state, action, P_bull, P_bear, market_open, flat, reason, wp, cycles=1, killed=False):
    """state: dict با کلید wait_count (درجا به‌روز). برمی‌گرداند (action, tag) — tag='forced' اگر انقضا عمل کرد."""
    if wp.max_wait <= 0:
        return action, None
    if action in ("LONG", "SHORT"):
        state["wait_count"] = 0
        return action, None
    if not market_open or is_risk_veto(reason) or killed:
        return action, None                       # شمارنده فقط در بازار باز جلو می‌رود
    if not flat:
        state["wait_count"] = 0                   # پوزیشن باز = معامله؛ شمارش از نو
        return action, None
    state["wait_count"] = int(state.get("wait_count", 0)) + int(cycles)
    thr = threshold(state["wait_count"], wp)
    if thr is None:
        return action, None
    side = "LONG" if P_bull >= P_bear else "SHORT"
    p = max(P_bull, P_bear)
    if p >= thr or thr <= wp.floor:
        state["wait_count"] = 0
        return side, "forced"
    return action, None
