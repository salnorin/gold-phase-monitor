# core/ledger.py
"""
دفتر تصمیم (Decision Ledger) — فقط کاغذی.
در هر کندل تصمیم، هر سه گزینه ثبت می‌شود: LONG، SHORT، NO_TRADE (با پرچم انتخاب‌شده، اطمینان، عکس ویژگی‌ها،
شناسه‌ی مدل/ژنوم، tier و تایم‌فریم). نتیجه‌ی خلاف‌واقع (counterfactual) گزینه‌های انتخاب‌نشده با همان قواعد
TP/SL/حداکثر نگهداری حل می‌شود: زمان خروج، دلیل خروج (TP/SL/LIQ/timeout)، درصد سود/زیان و «آب‌میوه» (با اهرم).

بدون نگاه به آینده: هر ردیف یک `resolved_index` دارد (کندلی که نتیجه در Close آن معلوم شد).
مصرف‌کننده‌ها (یادگیری ذهن، fitness آرنا) فقط ردیف‌هایی را می‌بینند که resolved_index ≤ کندل فعلی.
"""
from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3
import numpy as np
import pandas as pd

from core.paper import CostModel

OPTIONS = ("LONG", "SHORT", "NO_TRADE")
SNAP_KEYS = ("P_bull", "P_bear", "P_range", "Oxygen", "Vol_Ratio", "Whale", "doubt", "intuition", "evidence")


@dataclass
class ExitRules:
    target_atr: float = 3.0
    stop_atr: float = 1.5
    max_hold: int = 48


# ۲۰x: حد سود/ضرر تنگ و نگهداری کوتاه تا سود و زیان سریع بسته شوند (آرنا داخل همین کران‌ها تکامل می‌یابد)
TIER_RULES = {20.0: ExitRules(1.2, 0.6, 6), 10.0: ExitRules(2.0, 1.0, 16), 1.0: ExitRules(3.0, 1.5, 48)}


def tier_rules(leverage):
    return TIER_RULES[min(TIER_RULES, key=lambda k: abs(k - leverage))]


def resolve(o, h, l, c, atr, i, direction, rules: ExitRules, cm: CostModel):
    """سیگنال در Close کندل i، ورود Open کندل i+1. خروجی: (exit_index, reason, pct, juice) یا None اگر هنوز حل نشده."""
    n = len(c)
    if direction == 0:
        return (i, "NO_TRADE", 0.0, 0.0, 0.0)              # عدم معامله انرژی نمی‌خورد
    if i + 1 >= n:
        return None
    a = atr[i]
    slip = lambda px, at: px * cm.base_spread + at * cm.vol_slippage
    e = o[i + 1] + direction * slip(o[i + 1], a)
    stop, tgt = e - direction * rules.stop_atr * a, e + direction * rules.target_atr * a
    liq = e * (1 - direction * cm.liq_move)
    worst = max(stop, liq) if direction > 0 else min(stop, liq)
    worst_is_liq = (liq >= stop) if direction > 0 else (liq <= stop)
    hit = lambda lvl, px: px <= lvl if direction > 0 else px >= lvl
    hours = 0.0
    for j in range(i + 1, n):
        hours += cm.bar_hours
        adv, fav = (l[j], h[j]) if direction > 0 else (h[j], l[j])
        if j > i + 1 and hit(worst, o[j]):                 # گپ از استاپ/لیکوئید عبور کرد
            px, why = o[j], "LIQ" if (worst_is_liq or hit(liq, o[j])) else "SL"
        elif hit(worst, adv):
            px, why = worst, "LIQ" if worst_is_liq else "SL"
        elif (fav >= tgt) if direction > 0 else (fav <= tgt):
            px, why = tgt, "TP"
        elif j - i >= rules.max_hold:
            px, why = c[j], "TIMEOUT"
        else:
            continue
        fill = px - direction * slip(px, atr[j])
        pct = direction * (fill - e) / e - 2 * cm.fee_rate - cm.funding_rate_8h * hours / 8
        energy = 2 * cm.energy_frac_side                   # باز + بستن، سهم از مارجین
        juice = -1.0 - energy if why == "LIQ" else max(-1.0, pct * cm.leverage) - energy
        return (j, why, float(pct), float(juice), float(energy))
    return None


class DecisionLedger:
    """ردیف‌ها در حافظه؛ ذخیره در SQLite (پیش‌فرض) یا Parquet."""

    def __init__(self):
        self.rows, self._open = [], []   # _open: ردیف‌هایی که هنوز نتیجه ندارند
        self._reveal = {}                # resolved_index → ردیف‌ها (نتیجه فقط در آن کندل «دیده» می‌شود)

    def log(self, i, time, chosen, confidence, snapshot, model, tier, timeframe, df_arrays, rules, cm, suggested=0):
        """در Close کندل i فراخوانی می‌شود. suggested: جهتی که استراتژی پیشنهاد داد (برای سنجش وتوها)."""
        for opt, d in (("LONG", 1), ("SHORT", -1), ("NO_TRADE", 0)):
            r = dict(index=i, time=str(time), option=opt, chosen=opt == chosen, suggested=d == suggested and d != 0,
                     confidence=float(confidence), model=model, tier=float(tier), timeframe=timeframe,
                     features=json.dumps({k: (float(v) if isinstance(v, (int, float, np.floating, bool, np.bool_)) else str(v))
                                          for k, v in snapshot.items() if k in SNAP_KEYS}),
                     resolved_index=None, exit_time=None, exit_reason=None, pct=None, juice=None, energy=None, _d=d)
            self.rows.append(r)
            # نتیجه فقط تابع کندل‌های i+1..exit است و تا Close کندل exit به هیچ مصرف‌کننده‌ای نشان داده نمی‌شود
            o, h, l, c, atr, idx = df_arrays
            res = resolve(o, h, l, c, atr, i, d, rules, cm)
            if res is None:
                continue
            j, why, pct, juice, energy = res
            r["_res"] = dict(resolved_index=int(j), exit_time=str(idx[j]), exit_reason=why, pct=pct, juice=juice, energy=energy)
            self._reveal.setdefault(int(j), []).append(r)

    def reveal(self, now_i):
        """ردیف‌هایی که نتیجه‌شان دقیقاً در Close کندل now_i معلوم می‌شود (برای یادگیری آنلاین)."""
        got = self._reveal.pop(now_i, [])
        for r in got:
            r.update(r.pop("_res"))
        return got

    def advance(self, now_i, df_arrays, rules, cm, index=None):
        """حل ردیف‌هایی که نتیجه‌شان تا Close کندل now_i معلوم است (فقط داده‌ی تا now_i)."""
        o, h, l, c, atr, idx = df_arrays
        lim = now_i + 1
        still = []
        for r in self._open:
            res = resolve(o[:lim], h[:lim], l[:lim], c[:lim], atr[:lim], r["index"], r["_d"], rules, cm)
            if res is None:
                still.append(r); continue
            j, why, pct, juice, energy = res
            r.update(resolved_index=int(j), exit_time=str(idx[j]), exit_reason=why, pct=pct, juice=juice, energy=energy)
        self._open = still

    def resolved(self, now_i):
        """فقط نتایج گذشته — برای یادگیری."""
        return [r for r in self.rows if r["resolved_index"] is not None and r["resolved_index"] <= now_i]

    def frame(self):
        if not self.rows:
            return pd.DataFrame(columns=["time", "option", "chosen", "confidence", "model", "tier", "timeframe",
                                         "exit_time", "exit_reason", "pct", "juice", "energy"])
        return pd.DataFrame(self.rows).drop(columns=["_d", "_res"], errors="ignore")

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df = self.frame()
        if path.suffix == ".parquet":
            df.to_parquet(path)
        else:
            with sqlite3.connect(path) as con:
                df.to_sql("ledger", con, if_exists="replace", index=False)
        return path

    @staticmethod
    def load(path):
        path = Path(path)
        if path.suffix == ".parquet":
            return pd.read_parquet(path)
        with sqlite3.connect(path) as con:
            return pd.read_sql("select * from ledger", con)


def summarize(df):
    """برای هر مدل: تعداد خروج به تفکیک دلیل، میانگین آب‌میوه‌ی انتخاب‌ها و خلاف‌واقع، و اعتبار NO_TRADE."""
    d = df.dropna(subset=["exit_reason"])
    if d.empty:
        return pd.DataFrame()
    out = []
    for m, g in d.groupby("model"):
        ch = g[g.chosen]
        trades = ch[ch.option != "NO_TRADE"]
        bars = g.pivot_table(index="index", columns="option", values="juice", aggfunc="first")
        chosen_nt = set(ch[ch.option == "NO_TRADE"]["index"])
        nt = bars.loc[bars.index.isin(chosen_nt)].dropna(subset=["LONG", "SHORT"], how="any") if {"LONG", "SHORT"} <= set(bars) else bars.iloc[:0]
        row = dict(model=m, decisions=int(g["index"].nunique()), trades=len(trades),
                   chosen_juice=float(trades.juice.sum()), energy_spent=float(trades.energy.sum()), chosen_mean_pct=float(trades.pct.mean()) if len(trades) else 0.0,
                   no_trade=len(chosen_nt),
                   correct_no_trade=float(((nt.LONG <= 0) & (nt.SHORT <= 0)).mean()) if len(nt) else np.nan,
                   avoided_juice=float(np.minimum(nt.get("LONG", 0), 0).sum() + np.minimum(nt.get("SHORT", 0), 0).sum()) * -1 if len(nt) else 0.0)
        for why in ("TP", "SL", "LIQ", "TIMEOUT"):
            row[f"exit_{why}"] = int((trades.exit_reason == why).sum())
        out.append(row)
    return pd.DataFrame(out).set_index("model")
