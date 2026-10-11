# core/brain.py
"""
مغز ارگانیسم (نسخه ۲).
هر کندل به ترتیب پردازش می‌شود و فقط داده‌ی تا همان کندل بسته‌شده دیده می‌شود:
  ۱. ورود پوزیشنِ در انتظار در Open همین کندل
  ۲. بررسی خروج (تارگت/استاپ/زمان) → یادگیری فقط از معامله‌ی بسته‌شده
  ۳. ارگان‌ها رأی می‌دهند و در جریان خون می‌نویسند
  ۴. هموستاز (ATP ↔ کورتیزول) و خستگی، اطمینان را تنظیم می‌کنند
  ۵. تصمیم در Close کندل؛ ورود در Open کندل بعدی
"""
from dataclasses import dataclass
from typing import List, Optional
import numpy as np
import pandas as pd

from core.bloodstream import Bloodstream
from core.config import OrganismConfig, DEFAULT_CONFIG

ORGANS = ("respiration", "optical", "motor", "cross")


@dataclass
class Trade:
    direction: int          # +1 لانگ، -1 شورت
    signal_time: object
    entry_time: object
    entry: float
    target: float
    stop: float
    risk: float
    votes: dict
    cost: float = 0.0       # هزینه‌ی رفت‌وبرگشت (اسپرد/کارمزد) به دلار
    exit_time: object = None
    exit: float = None
    reason: str = ""

    @property
    def r_multiple(self) -> float:
        return ((self.exit - self.entry) * self.direction - self.cost) / self.risk if self.risk else 0.0


def check_exit(trade: Trade, o, h, l, c, bars_held: int, max_hold: int):
    """استاپ و تارگت در یک کندل؟ محافظه‌کارانه استاپ حساب می‌شود."""
    if trade.direction > 0:
        if o <= trade.stop: return o, "gap_stop"
        if l <= trade.stop: return trade.stop, "stop"
        if h >= trade.target: return trade.target, "target"
    else:
        if o >= trade.stop: return o, "gap_stop"
        if h >= trade.stop: return trade.stop, "stop"
        if l <= trade.target: return trade.target, "target"
    if bars_held >= max_hold:
        return c, "time"
    return None, None


class Brain:
    def __init__(self, config: OrganismConfig = DEFAULT_CONFIG):
        self.cfg = config
        self.blood = Bloodstream(
            weights=dict(config.initial_weights),
            performance={k: 0.0 for k in ORGANS},
        )

    # ---------- ارگان‌ها ----------
    @staticmethod
    def organ_votes(row) -> dict:
        resp = 1.0 if row["Long_Zone"] else (-1.0 if row["Slaughter_Zone"] else 0.0)
        return {
            "respiration": resp,
            "optical": float(np.clip(row.get("Optical_Pull", 0.0), -1, 1)),
            "motor": float(np.clip(row.get("Motor_Drive", 0.0), -1, 1)),
            # سیگنال متقاطع (مثلاً نقره SI=F): فقط اگر ستون Cross_Drive وجود داشته باشد
            "cross": float(np.clip(row.get("Cross_Drive", 0.0), -1, 1)),
        }

    # ---------- هموستاز ----------
    def homeostasis(self, row):
        b, c = self.blood, self.cfg
        b.atp = float(row.get("ATP_Energy", 100.0))
        b.cortisol = float(row.get("Cortisol_Stress", 10.0))
        # کمبود انرژی استرس را بالا می‌برد، استرس انرژی مؤثر را می‌سوزاند
        b.effective_cortisol = min(100.0, b.cortisol + max(0.0, c.atp_stress_point - b.atp) * c.atp_to_cortisol)
        b.effective_atp = max(0.0, b.atp * (1 - b.effective_cortisol * c.cortisol_to_atp))
        b.fatigue = max(0.0, b.fatigue - c.fatigue_recovery)
        if b.sleeping_bars > 0:
            b.sleeping_bars -= 1

    # ---------- یادگیری ----------
    def learn(self, trade: Trade):
        b, c = self.blood, self.cfg
        r = trade.r_multiple
        for organ, v in trade.votes.items():
            if abs(v) < 1e-9 or c.initial_weights.get(organ, 0) == 0:
                continue
            agreed = np.sign(v) == trade.direction
            credit = r if agreed else -r     # مخالفت درست هم پاداش می‌گیرد
            b.performance[organ] = (1 - c.learning_rate) * b.performance[organ] + c.learning_rate * credit
            b.weights[organ] = float(np.clip(c.initial_weights[organ] * (1 + b.performance[organ]),
                                             c.weight_min, c.weight_max))
        if r <= 0:
            b.consecutive_losses += 1
            b.fatigue = min(1.0, b.fatigue + c.fatigue_per_loss)
            if b.consecutive_losses >= c.losses_to_sleep:
                b.sleeping_bars = c.sleep_bars
                b.consecutive_losses = 0
        else:
            b.consecutive_losses = 0

    # ---------- تصمیم ----------
    def decide(self, row) -> int:
        b, c = self.blood, self.cfg
        b.votes = self.organ_votes(row)
        total_w = sum(b.weights.values()) or 1.0
        b.score = sum(b.weights[k] * b.votes[k] for k in ORGANS) / total_w
        b.confidence = abs(b.score) * (b.effective_atp / 100) * (1 - b.effective_cortisol / 100) * (1 - b.fatigue)
        direction = 0
        if not row.get("Market_Open", True):
            b.reason = "بازار بسته / اولین کندل پس از بازگشایی"
        elif b.sleeping_bars > 0:
            b.reason = f"خواب/ریکاوری پس از ضررهای پیاپی ({b.sleeping_bars} کندل مانده)"
        elif b.atp < c.atp_floor or b.cortisol > c.cortisol_ceiling:
            b.reason = "انرژی کم یا استرس بالا"
        elif c.require_respiration and b.votes["respiration"] == 0:
            b.reason = "ارگان تنفس منطقه‌ی فعالی نمی‌بیند"
        elif abs(b.score) < c.min_score:
            b.reason = "توافق ارگان‌ها کافی نیست"
        elif b.confidence < c.min_confidence:
            b.reason = "اطمینان پس از هموستاز کم است"
        else:
            direction = int(np.sign(b.score))
            b.reason = "توافق ارگان‌ها و هموستاز سالم"
        b.signal = {1: "LONG", -1: "SHORT", 0: "FLAT"}[direction]
        return direction

    # ---------- چرخه کامل (LEGACY) ----------
    def run(self, df: pd.DataFrame):
        """LEGACY — بک‌تستر فقط-مغز، فقط برای مقایسه (core/evaluate_v3). تصمیم زنده فقط از core.decision.organism_decision."""
        c = self.cfg
        n = len(df)
        o, h, l, cl = (df[k].values for k in ("Open", "High", "Low", "Close"))
        atr = df["ATR"].values
        records, trades = [], []
        open_trade: Optional[Trade] = None
        pending = None
        held = 0
        rows = df.to_dict("records")
        for i in range(n):
            row = rows[i]
            if pending is not None:
                d, sig_t, votes = pending
                entry = o[i]; risk = atr[i - 1] * c.stop_atr_mult
                open_trade = Trade(d, sig_t, df.index[i], entry,
                                   entry + d * atr[i - 1] * c.target_atr_mult,
                                   entry - d * risk, risk, votes, c.cost_frac * entry)
                pending, held = None, 0
            if open_trade is not None:
                held += 1
                px, why = check_exit(open_trade, o[i], h[i], l[i], cl[i], held, c.max_hold_bars)
                if px is not None:
                    open_trade.exit, open_trade.exit_time, open_trade.reason = px, df.index[i], why
                    trades.append(open_trade)
                    self.learn(open_trade)
                    open_trade = None
            self.homeostasis(row)
            d = self.decide(row)
            target = stop = 0.0
            if d != 0:
                target = cl[i] + d * atr[i] * c.target_atr_mult
                stop = cl[i] - d * atr[i] * c.stop_atr_mult
                if open_trade is None and i < n - 1:
                    pending = (d, df.index[i], dict(self.blood.votes))
            rec = self.blood.snapshot()
            rec.update(Signal_Dir=d, Target_Price=target, Stop_Loss=stop, In_Trade=open_trade is not None)
            records.append(rec)
        out = df.copy()
        flat = pd.DataFrame([{k: v for k, v in r.items() if not isinstance(v, dict)} for r in records], index=df.index)
        for organ in ORGANS:
            flat[f"Vote_{organ}"] = [r["votes"][organ] for r in records]
            flat[f"Weight_{organ}"] = [r["weights"][organ] for r in records]
        out = out.join(flat.rename(columns={"atp": "Brain_ATP", "cortisol": "Brain_Cortisol"}))
        return out, trades

    def explain(self) -> str:
        b = self.blood
        lines = [f"**تصمیم:** {b.signal} — {b.reason}",
                 f"**امتیاز وزن‌دار:** {b.score:+.2f} | **اطمینان:** {b.confidence:.2f}",
                 f"**ATP مؤثر:** {b.effective_atp:.1f} | **کورتیزول مؤثر:** {b.effective_cortisol:.1f} | **خستگی:** {b.fatigue:.2f}"]
        for k in ORGANS:
            lines.append(f"- {k}: رأی {b.votes.get(k, 0):+.2f} × وزن {b.weights[k]:.2f} (عملکرد {b.performance[k]:+.2f}R)")
        return "\n".join(lines)
