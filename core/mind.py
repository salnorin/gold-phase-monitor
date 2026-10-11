# core/mind.py
"""
لایه‌ی «ذهن» ارگانیسم — فقط معامله‌ی کاغذی/شبیه‌سازی (بدون سفارش واقعی).
هر کندل به ترتیب و فقط با داده‌ی تا همان کندل بسته‌شده پردازش می‌شود.
اجزا: آب‌میوه (equity)، مقیاس ریسک، نهنگ، اکسیژن، انگیزه‌ی بقا، جعبه‌سیاه اشتباهات،
استخر استراتژی‌ها، شهود و تردید، احتمال حالت‌ها (الهام‌گرفته از کوانتوم)، دفتر روزنامه.
"""
from dataclasses import dataclass, field
import sqlite3
import numpy as np
import pandas as pd

from core.brain import Brain, Trade
from core.config import OrganismConfig
from core.paper import CostModel, open_position, step_position

STATES = ("bull", "bear", "range")
STRATEGIES = ("organism", "trend", "reversion")
FA = {"bull": "صعودی", "bear": "نزولی", "range": "خنثی"}


@dataclass
class MindConfig:
    organism: OrganismConfig = field(default_factory=lambda: OrganismConfig(
        min_score=0.35, min_confidence=0.2, target_atr_mult=3.0, stop_atr_mult=1.5,
        max_hold_bars=48, require_respiration=False))
    start_equity: float = 10_000.0
    leverage: float = 20.0
    bar_hours: float = 1.0
    base_risk: float = 0.01
    min_risk: float = 0.0025
    max_risk: float = 0.015
    win_streak_step: float = 0.05
    max_consec_losses: int = 4
    loss_rest_bars: int = 24
    max_drawdown: float = 0.10
    dd_rest_bars: int = 96
    vol_rest_ratio: float = 2.0
    whale_volume: float = 3.0
    whale_range_atr: float = 3.0
    whale_caution_bars: int = 6
    low_oxygen: float = 0.5
    dominance: float = 0.55
    state_smoothing: float = 0.7
    intuition_horizon: int = 4
    trust_lr: float = 0.05
    max_doubt: float = 0.6
    bb_distance: float = 0.30
    bb_ttl_bars: int = 400
    strat_lr: float = 0.2
    demote_below: float = -0.25
    demote_bars: int = 300
    min_trades_promote: int = 3
    purpose_max_effect: float = 0.05


def mind_features(feat: pd.DataFrame, cfg: MindConfig) -> pd.DataFrame:
    """ویژگی‌های علّی ذهن (فقط گذشته و کندل فعلی بسته‌شده)."""
    f = feat.copy()
    vol_norm = f["Volume"].shift(1).rolling(50, min_periods=5).median()
    f["Oxygen"] = (f["Volume"] / vol_norm.replace(0, np.nan)).fillna(1.0).clip(0, 10)
    atr_norm = f["ATR"].shift(1).rolling(200, min_periods=20).median()
    f["Vol_Ratio"] = (f["ATR"] / atr_norm).fillna(1.0)
    prev_atr = f["ATR"].shift(1).fillna(f["ATR"])
    f["Whale"] = (f["Oxygen"] > cfg.whale_volume) | ((f["High"] - f["Low"]) > cfg.whale_range_atr * prev_atr)
    ema = f["Close"].ewm(span=20, adjust=False).mean()
    slope = ((ema - ema.shift(5)) / f["ATR"].replace(0, np.nan)).fillna(0).clip(-5, 5).values
    logits = np.stack([2 * slope, -2 * slope, 1.0 - 2 * np.abs(slope)], axis=1)
    raw = np.exp(logits - logits.max(axis=1, keepdims=True)); raw /= raw.sum(axis=1, keepdims=True)
    p = np.zeros_like(raw); p[0] = raw[0]
    a = cfg.state_smoothing
    for i in range(1, len(p)):     # برهم‌نهی: باور قبلی با شواهد تازه ترکیب می‌شود
        p[i] = a * p[i - 1] + (1 - a) * raw[i]
    for k, s in enumerate(STATES):
        f[f"P_{s}"] = p[:, k]
    f["Intuition"] = np.tanh(2 * f["Motor_Drive"] + 0.5 * np.sign(f["Close"] - f["Open"]))
    return f


class BlackBox:
    """جعبه‌سیاه اشتباهات: زمینه + برچسب دلیل هر ضرر؛ ورود در زمینه‌ی مشابه تا تغییر شرایط مسدود است."""

    def __init__(self, distance=0.3, ttl=400):
        self.distance, self.ttl, self.entries = distance, ttl, []

    @staticmethod
    def vector(ctx):
        return np.array([ctx["P_bull"], ctx["P_bear"], ctx["P_range"], min(ctx["Oxygen"], 3) / 3,
                         min(ctx["Vol_Ratio"], 3) / 3, float(ctx["Whale"]),
                         np.sin(2 * np.pi * ctx["hour"] / 24) / 2, np.cos(2 * np.pi * ctx["hour"] / 24) / 2])

    @staticmethod
    def tags(ctx, pos):
        t = []
        if ctx["Whale"]: t.append("whale")
        if ctx["Oxygen"] < 0.7: t.append("low_oxygen")
        if ctx["Vol_Ratio"] > 1.5: t.append("high_volatility")
        dom = STATES[int(np.argmax([ctx["P_bull"], ctx["P_bear"], ctx["P_range"]]))]
        if (dom == "bull" and pos.direction < 0) or (dom == "bear" and pos.direction > 0): t.append("against_state")
        if pos.reason == "liquidation": t.append("liquidated")
        if pos.bars <= 2: t.append("stopped_fast")
        if ctx.get("doubt", 0) > 0.4: t.append("ignored_doubt")
        return t or ["unknown"]

    def record(self, ctx, pos, strategy, index, time):
        self.entries.append(dict(vec=self.vector(ctx), dir=pos.direction, strategy=strategy, index=index,
                                 time=str(time), tags=self.tags(ctx, pos), r=round(pos.r_multiple, 2)))

    def blocked(self, ctx, direction, strategy, index):
        v = self.vector(ctx)
        self.entries = [e for e in self.entries if index - e["index"] <= self.ttl]
        for e in self.entries:
            if e["dir"] == direction and e["strategy"] == strategy and np.linalg.norm(v - e["vec"]) < self.distance:
                return e
        return None


class Mind:
    def __init__(self, cfg: MindConfig = None):
        self.cfg = cfg or MindConfig()
        self.cm = CostModel(leverage=self.cfg.leverage, bar_hours=self.cfg.bar_hours)
        self.brain = Brain(self.cfg.organism)
        self.blackbox = BlackBox(self.cfg.bb_distance, self.cfg.bb_ttl_bars)
        self.trust = {s: 0.5 for s in STATES}
        self.strat = {s: dict(score=0.0, n=0, demoted_until=-1) for s in STRATEGIES}
        self.active = "organism"
        self.equity = self.peak = self.cfg.start_equity
        self.journal, self.trades, self.events, self.trust_history = [], [], [], []

    def strategy_dirs(self, row, brain_dir):
        dom = max(STATES, key=lambda s: row[f"P_{s}"])
        trend = 1 if dom == "bull" and row["Motor_Drive"] > 0 else (-1 if dom == "bear" and row["Motor_Drive"] < 0 else 0)
        rev = 0
        if dom == "range":
            rev = -1 if row["Optical_Pull"] > 0.5 else (1 if row["Optical_Pull"] < -0.5 else 0)
        return {"organism": brain_dir, "trend": trend, "reversion": rev}

    def update_strategy(self, name, r, i):
        s, c = self.strat[name], self.cfg
        s["n"] += 1
        s["score"] = (1 - c.strat_lr) * s["score"] + c.strat_lr * r
        if s["n"] >= 5 and s["score"] < c.demote_below and s["demoted_until"] < i:
            s["demoted_until"] = i + c.demote_bars
            self.events.append((i, f"تنزل استراتژی {name}"))
        elig = [k for k, v in self.strat.items() if v["demoted_until"] < i and
                (k == "organism" or (v["n"] >= c.min_trades_promote and v["score"] > 0))]
        best = max(elig, key=lambda k: self.strat[k]["score"]) if elig else "organism"
        if best != self.active:
            self.events.append((i, f"ارتقای {best} به‌جای {self.active}"))
            self.active = best

    def risk_fraction(self, wins_streak=0, recovery=0):
        c = self.cfg
        dd = 1 - self.equity / self.peak
        juice_factor = float(np.clip(1 - dd / c.max_drawdown, 0.25, 1.0))
        streak = min(1 + c.win_streak_step * max(0, wins_streak - 2), 1.5)
        r = c.base_risk * juice_factor * streak * (0.5 if recovery > 0 else 1.0)
        return float(np.clip(r, c.min_risk, c.max_risk))

    def update_trust(self, regime, intuition, evidence, move):
        """تردید: اگر شهود و شواهد اختلاف داشتند، هر کدام درست بود اعتمادش بالا می‌رود."""
        if move == 0 or np.sign(intuition) == np.sign(evidence):
            return None
        right = bool(np.sign(intuition) == move)
        step = self.cfg.trust_lr if right else -self.cfg.trust_lr
        self.trust[regime] = float(np.clip(self.trust[regime] + step, 0.1, 0.9))
        return right

    def run(self, feat: pd.DataFrame):
        c, oc = self.cfg, self.cfg.organism
        f = mind_features(feat, c)
        rows = f.to_dict("records")
        o, h, l, cl, atr = (f[k].values for k in ("Open", "High", "Low", "Close", "ATR"))
        n = len(f)
        pos, pending = None, None
        shadow = {s: None for s in STRATEGIES}
        shadow_pending = {s: None for s in STRATEGIES}
        rest_until = caution_until = -1
        consec = wins = recovery = last_trade = 0
        pend = []
        out = []
        for i in range(n):
            row, t = rows[i], f.index[i]
            ctx = {k: row[k] for k in ("P_bull", "P_bear", "P_range", "Oxygen", "Vol_Ratio", "Whale")}
            ctx["hour"] = t.hour
            # ۱) ورود در Open این کندل
            for s in STRATEGIES:
                if shadow_pending[s] and shadow[s] is None:
                    shadow[s] = open_position(self.cm, 10_000, shadow_pending[s], o[i], atr[i - 1],
                                              atr[i - 1] * oc.stop_atr_mult, atr[i - 1] * oc.target_atr_mult,
                                              risk_frac=c.base_risk, index=i, time=t)
                shadow_pending[s] = None
            if pending is not None and pos is None:
                d, strat, pctx, risk = pending
                pos = open_position(self.cm, self.equity, d, o[i], atr[i - 1], atr[i - 1] * oc.stop_atr_mult,
                                    atr[i - 1] * oc.target_atr_mult, risk_frac=risk, index=i, time=t,
                                    context={**pctx, "strategy": strat})
                last_trade = i
            pending = None
            # ۲) خروج‌ها؛ یادگیری فقط از معاملات بسته‌شده
            for s in STRATEGIES:
                sp = shadow[s]
                if sp is not None and step_position(self.cm, sp, o[i], h[i], l[i], cl[i], atr[i], oc.max_hold_bars, i, t):
                    self.update_strategy(s, sp.r_multiple, i)
                    shadow[s] = None
            if pos is not None and step_position(self.cm, pos, o[i], h[i], l[i], cl[i], atr[i], oc.max_hold_bars, i, t):
                self.equity = max(0.0, self.equity + pos.pnl)
                self.peak = max(self.peak, self.equity)
                self.trades.append(pos)
                strat = pos.context["strategy"]
                if strat == "organism" and pos.qty > 0:
                    risk_px = pos.risk_cash / pos.qty
                    bt = Trade(pos.direction, None, None, pos.entry, pos.target, pos.stop, risk_px, pos.context.get("votes", {}))
                    bt.exit = pos.entry + pos.direction * pos.r_multiple * risk_px
                    self.brain.learn(bt)
                if pos.pnl <= 0:
                    consec += 1; wins = 0
                    self.blackbox.record(pos.context, pos, strat, i, t)
                else:
                    consec = 0; wins += 1
                recovery = max(0, recovery - 1)
                if consec >= c.max_consec_losses:
                    rest_until, consec = i + c.loss_rest_bars, 0
                    self.events.append((i, "استراحت پس از ضررهای پیاپی"))
                if 1 - self.equity / self.peak >= c.max_drawdown:
                    rest_until = i + c.dd_rest_bars
                    self.peak, recovery = self.equity, 5
                    self.events.append((i, "افت ۱۰٪ آب‌میوه → استراحت طولانی، ریسک نصف"))
                pos = None
            # ۳) اعتماد به شهود وقتی نتیجه‌ی لحظه‌ی گذشته معلوم شد
            while pend and pend[0][0] + c.intuition_horizon <= i:
                j, reg, intu, evid = pend.pop(0)
                right = self.update_trust(reg, intu, evid, np.sign(cl[i] - cl[j]))
                if right is not None:
                    out[j]["intuition_right"] = right
            # ۴) مغز، حالت‌ها، شهود و تردید
            self.brain.homeostasis(row)
            brain_dir = self.brain.decide(row)
            evidence = float(self.brain.blood.score)
            probs = {s: float(row[f"P_{s}"]) for s in STATES}
            regime = max(probs, key=probs.get)
            intuition = float(row["Intuition"])
            w = self.trust[regime]
            doubt = abs(intuition - evidence) / 2
            if row["Whale"]:
                caution_until = i + c.whale_caution_bars
            purpose = 0.5 * float(np.clip((i - last_trade) / 200, 0, 1)) + \
                0.5 * float(np.clip(1 - self.equity / c.start_equity, 0, 1))
            dirs = self.strategy_dirs(row, brain_dir)
            for s, sd in dirs.items():
                if sd and shadow[s] is None and i < n - 1:
                    shadow_pending[s] = sd
            d = dirs[self.active]
            dom_thr, doubt_thr = c.dominance, c.max_doubt
            hard = None
            if self.equity <= 0: hard = "آب‌میوه تمام شد"
            elif i < rest_until: hard = "استراحت اجباری (حد ضرر/افت سرمایه)"
            elif row["Vol_Ratio"] > c.vol_rest_ratio: hard = "نوسان بیش از ۲ برابر عادی → استراحت"
            elif i < caution_until: hard = "احتیاط: ردپای نهنگ"
            elif row["Oxygen"] < c.low_oxygen: hard = "اکسیژن (نقدینگی) کم"
            else:   # انگیزه فقط وقتی هیچ حدی فعال نیست، و حداکثر ۰٫۰۵ آستانه را نرم می‌کند
                dom_thr -= c.purpose_max_effect * purpose
                doubt_thr += c.purpose_max_effect * purpose
            combined = w * intuition + (1 - w) * evidence
            action = "WAIT"
            if hard: reason = hard
            elif d == 0: reason = f"استراتژی فعال ({self.active}) سیگنالی ندارد"
            elif pos is not None: reason = "در پوزیشن (بدون افزودن یا میانگین‌گیری)"
            elif self.active != "reversion" and probs["bull" if d > 0 else "bear"] < dom_thr:
                reason = f"هیچ حالتی غالب نیست ({FA[regime]} {probs[regime]:.0%})"
            elif self.active == "reversion" and probs["range"] < dom_thr:
                reason = "حالت خنثی غالب نیست"
            elif doubt > doubt_thr:
                reason = f"تردید بالا ({doubt:.2f}) → احترام به تردید"
            elif self.active != "reversion" and np.sign(combined) != d:
                reason = "شهود+شواهد هم‌جهت سیگنال نیستند"
            else:
                blk = self.blackbox.blocked(ctx, d, self.active, i)
                if blk:
                    reason = f"جعبه‌سیاه: شبیه ضرر {blk['time'][:16]} ({', '.join(blk['tags'])})"
                else:
                    risk = self.risk_fraction(wins, recovery)
                    action = "LONG" if d > 0 else "SHORT"
                    reason = f"{self.active}: {FA[regime]} {probs[regime]:.0%}، تردید {doubt:.2f}، ریسک {risk:.2%}"
                    if i < n - 1:
                        pending = (d, self.active, {**ctx, "doubt": doubt, "votes": dict(self.brain.blood.votes)}, risk)
            pend.append((i, regime, intuition, evidence))
            out.append(dict(time=t, close=float(cl[i]), P_bull=probs["bull"], P_bear=probs["bear"], P_range=probs["range"],
                            regime=regime, oxygen=float(row["Oxygen"]), vol_ratio=float(row["Vol_Ratio"]),
                            whale=bool(row["Whale"]), intuition=intuition, evidence=evidence, doubt=doubt, trust=w,
                            purpose=purpose, strategy=self.active, action=action, reason=reason, juice=self.equity,
                            drawdown=1 - self.equity / self.peak, in_position=pos is not None, intuition_right=None))
        self.journal = out
        return pd.DataFrame(out).set_index("time")

    def trades_frame(self):
        return pd.DataFrame([dict(entry_time=p.open_time, exit_time=p.exit_time, direction="LONG" if p.direction > 0 else "SHORT",
                                  strategy=p.context.get("strategy"), entry=round(p.entry, 2), exit=round(p.exit, 2),
                                  reason=p.reason, pnl=round(p.pnl, 2), R=round(p.r_multiple, 2)) for p in self.trades])

    def blackbox_frame(self):
        return pd.DataFrame([dict(time=e["time"], direction=e["dir"], strategy=e["strategy"], tags=", ".join(e["tags"]),
                                  R=e["r"]) for e in self.blackbox.entries])

    def save_journal(self, path):
        df = pd.DataFrame(self.journal)
        if path.endswith(".csv"):
            df.to_csv(path, index=False)
        else:
            with sqlite3.connect(path) as con:
                df.assign(time=df["time"].astype(str)).to_sql("decisions", con, if_exists="replace", index=False)
                bb = self.blackbox_frame()
                if bb.empty:
                    bb = pd.DataFrame(columns=["time", "direction", "strategy", "tags", "R"])
                bb.to_sql("blackbox", con, if_exists="replace", index=False)
        return path

    def explain(self):
        if not self.journal:
            return ""
        j = self.journal[-1]
        return (f"**اقدام:** {j['action']} — {j['reason']}\n\n"
                f"**آب‌میوه:** {j['juice']:,.0f} | **افت از اوج:** {j['drawdown']:.1%} | **استراتژی فعال:** {j['strategy']}\n\n"
                f"**احتمال حالت‌ها:** صعودی {j['P_bull']:.0%} · نزولی {j['P_bear']:.0%} · خنثی {j['P_range']:.0%}\n\n"
                f"**شهود:** {j['intuition']:+.2f} | **شواهد:** {j['evidence']:+.2f} | **تردید:** {j['doubt']:.2f} | "
                f"**اعتماد به شهود:** {j['trust']:.2f} | **انگیزه:** {j['purpose']:.2f}")
