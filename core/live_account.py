# core/live_account.py
"""
حساب کاغذی خودکار «زنده» — جدا از بازپخش تاریخی. فقط شبیه‌سازی؛ هیچ سفارش واقعی.
  - هر LONG/SHORT تصمیم یگانه روی هر کندل بسته‌شده‌ی جدید (حتی اگر اپ در آن لحظه باز نبوده) یک معامله‌ی کاغذی
    در Open کندل بعدی با قیمت PAXG باز می‌کند (ورود، SL، TP، زمان، اطمینان).
  - بستن: TP / SL / لیکوئید / زمان / سیگنال مخالف (در Open کندل بعد).
  - فقط وقتی بازار CME باز است؛ آخرین کندل فقط وقتی ارگانیسم بیدار است.
  - ذخیره: JSON محلی (+ آینه‌ی SQLite). روی Streamlit Cloud دیسک موقت است → خروجی/ورودی CSV یا core.recorder.
"""
import json
import os
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from core.paper import CostModel, Position, close_at, open_position, step_position

DATA_DIR = Path(os.getenv("GPM_DATA_DIR", Path.home() / ".local" / "share" / "gold-phase-monitor"))
TRADE_COLS = ["entry_time", "exit_time", "direction", "entry", "exit", "stop", "target", "confidence", "reason",
              "pnl", "R", "energy"]


def _pos_dict(p):
    return {k: (str(v) if k in ("open_time", "exit_time") else v) for k, v in p.__dict__.items() if k != "context"}


def _conf(jrow):
    try:
        return float(max(jrow["P_bull"], jrow["P_bear"], jrow["P_range"]) * (1 - jrow["doubt"]))
    except Exception:
        return float("nan")


class LivePaperAccount:
    def __init__(self, asset="gold", start_equity=None, cfg=None, path=None, now=None, fixed_risk_usd=None, rr=None):
        """fixed_risk_usd/rr: پیش‌تنظیم آزمون دستی (ریسک ثابت دلاری تا استاپ، تارگت = rr × فاصله‌ی استاپ)؛ فایل جدا."""
        suffix = "_manual" if fixed_risk_usd else ""
        self.path = Path(path) if path else DATA_DIR / f"live_account_{asset}{suffix}.json"
        self.cfg = cfg
        self.fixed_risk_usd, self.rr = fixed_risk_usd, rr
        if self.path.exists():
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
            self.state = dict(asset=asset, created=str(now), start_equity=float(start_equity), equity=float(start_equity),
                              last_bar=str(now), position=None, pending=None, pending_close=False, trades=[])
            self.save()
        self.state.setdefault("pending_close", False)

    # ---------- ذخیره ----------
    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        tmp.replace(self.path)

    def mirror_sqlite(self, db=None):
        """آینه‌ی معاملات بسته در SQLite (برای core.recorder)؛ تکراری‌ها نادیده."""
        db = Path(db) if db else self.path.with_suffix(".sqlite")
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE IF NOT EXISTS trades (entry_time TEXT, exit_time TEXT, direction TEXT, entry REAL, exit REAL,"
                    " stop REAL, target REAL, confidence REAL, reason TEXT, pnl REAL, R REAL, energy REAL,"
                    " PRIMARY KEY (entry_time, direction))")
        for t in self.state["trades"]:
            con.execute("INSERT OR IGNORE INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [t.get(k) for k in TRADE_COLS])
        con.commit(); con.close()
        return db

    def to_csv(self) -> bytes:
        return self.trades_frame().to_csv(index=False).encode("utf-8")

    def import_csv(self, data) -> int:
        """بازگردانی تاریخچه از CSV (پس از ری‌استارت Streamlit Cloud). معاملات تکراری اضافه نمی‌شوند؛ equity بازسازی می‌شود."""
        import io
        df = pd.read_csv(io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data)
        have = {(t["entry_time"], t["direction"]) for t in self.state["trades"]}
        add = [{k: (None if pd.isna(r.get(k)) else r.get(k)) for k in TRADE_COLS} for r in df.to_dict("records")
               if (str(r["entry_time"]), r["direction"]) not in have]
        for a in add:
            a["entry_time"], a["exit_time"] = str(a["entry_time"]), str(a["exit_time"])
        self.state["trades"] = sorted(self.state["trades"] + add, key=lambda t: t["entry_time"])
        self.state["equity"] = max(0.0, self.state["start_equity"] + sum(float(t["pnl"]) for t in self.state["trades"]))
        if self.state["trades"]:
            last_exit = max(pd.Timestamp(t["exit_time"]) for t in self.state["trades"])
            if last_exit > pd.Timestamp(self.state["last_bar"]):
                self.state["last_bar"] = str(last_exit)
        self.save()
        return len(add)

    # ---------- خواندن ----------
    @property
    def equity(self):
        return self.state["equity"]

    def trades_frame(self):
        df = pd.DataFrame(self.state["trades"])
        return df.reindex(columns=TRADE_COLS) if not df.empty else pd.DataFrame(columns=TRADE_COLS)

    def floating(self, price):
        """P&L شناور پوزیشن باز در قیمت زنده‌ی PAXG (پس از کارمزد ورود و فاندینگ)."""
        pos = self.state["position"]
        if not pos or price is None:
            return 0.0
        return pos["qty"] * (price - pos["entry"]) * pos["direction"] - pos["fees"] - pos["funding"]

    def stats(self, price=None, start_eur=None, rate=None):
        """کارت موفقیت — فقط از معاملات خودکار زنده (نه بازپخش)."""
        t = self.trades_frame()
        pnl = t["pnl"].astype(float) if not t.empty else pd.Series(dtype=float)
        s0 = self.state["start_equity"]
        realized = float(pnl.sum())
        fl = self.floating(price)
        eq = self.state["equity"] + fl
        curve = s0 + pnl.cumsum()
        peak = np.maximum.accumulate(np.r_[s0, curve.values])
        dd = float(np.max(1 - np.r_[s0, curve.values] / peak)) if len(peak) else 0.0
        wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
        n = int(len(pnl))
        mood = "neutral" if n == 0 else ("bull" if realized > 0 else "bear")
        return dict(start_usd=s0, start_eur=start_eur, rate=rate, equity=eq, realized=realized, floating=fl,
                    change=eq - s0, change_pct=(eq / s0 - 1) if s0 else 0.0, n=n, wins=int(len(wins)), losses=int(len(losses)),
                    win_rate=(len(wins) / n) if n else None, avg_win=float(wins.mean()) if len(wins) else None,
                    avg_loss=float(losses.mean()) if len(losses) else None, max_dd=dd, mood=mood,
                    open=bool(self.state["position"]))

    # ---------- چرخه ----------
    def _record(self, P, t):
        self.state["equity"] = max(0.0, self.state["equity"] + P.pnl)
        meta = self.state.get("open_meta", {})
        self.state["trades"].append(dict(entry_time=str(P.open_time), exit_time=str(t), direction="LONG" if P.direction > 0 else "SHORT",
                                         entry=round(P.entry, 2), exit=round(P.exit, 2), stop=round(P.stop, 2),
                                         target=round(P.target, 2), confidence=meta.get("confidence"), reason=P.reason,
                                         pnl=round(P.pnl, 2), R=round(P.r_multiple, 2), energy=round(P.energy, 4)))
        self.state["last_event"] = dict(kind="closed", reason=P.reason, time=str(t), pnl=round(P.pnl, 2))

    def update(self, feat: pd.DataFrame, journal: pd.DataFrame, awake: bool, signal=None):
        """feat/journal: خروجی Mind روی کندل‌های بسته‌شده (همان اجرای تصمیم یگانه).
        signal: اقدام تأییدشده‌ی Decision برای آخرین کندل (core.decision.live_signal) — بر journal مقدم است.
        awake: فقط برای آخرین کندل (کندل‌های قبلی را وتوهای خود journal — بازار بسته/کهنه — پوشش می‌دهند)."""
        c = self.cfg
        cm = CostModel(leverage=c.leverage, bar_hours=c.bar_hours)
        oc = c.organism
        last = pd.Timestamp(self.state["last_bar"])
        new = feat.index[feat.index > last]
        if len(new) == 0:
            return 0
        pos = self.state["position"]
        atr_prev = feat["ATR"].shift(1)
        for t in new:
            row = feat.loc[t]
            mopen = bool(row.get("Market_Open", True))
            # ۰) بستن به‌خاطر سیگنال مخالف کندل قبل، در Open همین کندل
            if pos is not None and self.state["pending_close"] and mopen:
                P = close_at(cm, Position(**pos), float(row["Open"]), float(atr_prev.loc[t]), "opposite", 0, t)
                self._record(P, t)
                pos = None
            self.state["pending_close"] = False
            # ۱) ورود در Open این کندل
            if self.state["pending"] and pos is None and mopen:
                d, risk, conf = (self.state["pending"] + [None])[:3]
                atr = float(atr_prev.loc[t])
                usable = min(self.state["equity"], c.capital_cap) if c.capital_cap > 0 else self.state["equity"]
                stop_d = atr * oc.stop_atr_mult
                tgt_d = stop_d * self.rr if self.fixed_risk_usd else atr * oc.target_atr_mult
                if self.fixed_risk_usd:
                    risk = self.fixed_risk_usd / usable if usable > 0 else 0.0
                p = open_position(cm, usable, d, float(row["Open"]), atr, stop_d, tgt_d, risk_frac=risk, index=0, time=t)
                if p is not None:
                    pos = _pos_dict(p)
                    self.state["open_meta"] = dict(confidence=conf)
                    self.state["last_event"] = dict(kind="opened", direction=d, time=str(t), entry=round(p.entry, 2),
                                                    stop=round(p.stop, 2), target=round(p.target, 2), confidence=conf)
            self.state["pending"] = None
            # ۲) گام پوزیشن باز روی همین کندل بسته‌شده
            if pos is not None:
                P = Position(**pos)
                if step_position(cm, P, float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]),
                                 float(row["ATR"]), oc.max_hold_bars, 0, t):
                    self._record(P, t)
                    pos = None
                else:
                    pos = _pos_dict(P)
            # ۳) سیگنال این کندل → ورود (یا بستن مخالف + ورود) در Open کندل بعد
            if t not in journal.index or not mopen or self.state["equity"] <= c.kill_equity:
                continue
            if t == new[-1]:
                if not awake:
                    continue
                a = signal if signal is not None else journal.loc[t, "action"]
            else:
                a = journal.loc[t, "action"]
            if a not in ("LONG", "SHORT"):
                continue
            d = 1 if a == "LONG" else -1
            conf = _conf(journal.loc[t])
            if pos is None:
                self.state["pending"] = [d, float(min(c.max_risk, c.base_risk)), conf]
            elif pos["direction"] != d:
                self.state["pending_close"] = True
                self.state["pending"] = [d, float(min(c.max_risk, c.base_risk)), conf]
        self.state["position"] = pos
        self.state["last_bar"] = str(new[-1])
        self.save()
        return len(new)
