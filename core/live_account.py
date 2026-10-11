# core/live_account.py
"""
حساب کاغذی «زنده» — جدا از بازپخش تاریخی (backtest replay).
  - از لحظه‌ی ایجاد شروع می‌شود و روی دیسک ذخیره می‌شود (pathlib، بین‌سکویی)
  - فقط کندل‌های بسته‌شده‌ی بعد از ایجاد پردازش می‌شوند
  - فقط وقتی بازار باز و ارگانیسم بیدار است پوزیشن جدید باز می‌کند؛ ورود در Open کندل بعدی
  - روی داده‌ی کهنه/بازار بسته هیچ چیزی تغییر نمی‌کند (نه ورود، نه ارزش‌گذاری)
فقط شبیه‌سازی؛ هیچ سفارش واقعی.
"""
import json
import os
from pathlib import Path

import pandas as pd

from core.paper import CostModel, open_position, step_position

DATA_DIR = Path(os.getenv("GPM_DATA_DIR", Path.home() / ".local" / "share" / "gold-phase-monitor"))


class LivePaperAccount:
    def __init__(self, asset="gold", start_equity=None, cfg=None, path=None, now=None):
        self.path = Path(path) if path else DATA_DIR / f"live_account_{asset}.json"
        self.cfg = cfg
        if self.path.exists():
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
            self.state = dict(asset=asset, created=str(now), start_equity=float(start_equity), equity=float(start_equity),
                              last_bar=str(now), position=None, pending=None, trades=[])
            self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        tmp.replace(self.path)

    @property
    def equity(self):
        return self.state["equity"]

    def trades_frame(self):
        return pd.DataFrame(self.state["trades"])

    def update(self, feat: pd.DataFrame, journal: pd.DataFrame, awake: bool):
        """feat/journal: خروجی Mind روی کندل‌های بسته‌شده. awake: بازار باز و داده‌ی تازه."""
        c = self.cfg
        cm = CostModel(leverage=c.leverage, bar_hours=c.bar_hours)
        oc = c.organism
        last = pd.Timestamp(self.state["last_bar"])
        new = feat.index[feat.index > last]
        if len(new) == 0:
            return 0
        pos = self.state["position"]
        for t in new:
            row = feat.loc[t]
            # ۱) ورود در Open این کندل (اگر سیگنال کندل قبل و این کندل مجاز است)
            if self.state["pending"] and pos is None and bool(row.get("Market_Open", True)):
                d, risk = self.state["pending"]
                atr = float(feat["ATR"].shift(1).loc[t])
                usable = min(self.state["equity"], c.capital_cap) if c.capital_cap > 0 else self.state["equity"]
                p = open_position(cm, usable, d, float(row["Open"]), atr, atr * oc.stop_atr_mult, atr * oc.target_atr_mult,
                                  risk_frac=risk, index=0, time=t)
                pos = {k: (str(v) if k == "open_time" else v) for k, v in p.__dict__.items() if k != "context"}
            self.state["pending"] = None
            # ۲) گام پوزیشن باز روی همین کندل بسته‌شده
            if pos is not None:
                from core.paper import Position
                P = Position(**{k: v for k, v in pos.items()})
                closed = step_position(cm, P, float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]),
                                       float(row["ATR"]), oc.max_hold_bars, 0, t)
                if closed:
                    self.state["equity"] = max(0.0, self.state["equity"] + P.pnl)
                    self.state["trades"].append(dict(entry_time=P.open_time, exit_time=str(t), direction="LONG" if P.direction > 0 else "SHORT",
                                                     entry=round(P.entry, 2), exit=round(P.exit, 2), reason=P.reason,
                                                     pnl=round(P.pnl, 2), R=round(P.r_multiple, 2)))
                    pos = None
                else:
                    pos = {k: (str(v) if k == "open_time" else v) for k, v in P.__dict__.items() if k != "context"}
            # ۳) سیگنال جدید فقط روی آخرین کندل، فقط بیدار و بازار باز، فقط اگر حساب بالای حد توقف است
            if t == new[-1] and awake and pos is None and t in journal.index and self.state["equity"] > c.kill_equity:
                a = journal.loc[t, "action"]
                if a in ("LONG", "SHORT") and bool(row.get("Market_Open", True)):
                    self.state["pending"] = [1 if a == "LONG" else -1, float(min(c.max_risk, c.base_risk))]
        self.state["position"] = pos
        self.state["last_bar"] = str(new[-1])
        self.save()
        return len(new)
