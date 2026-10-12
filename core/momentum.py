# core/momentum.py
"""پروفایل active: حالت مومنتوم ساده (فقط کاغذی).
LONG اگر بازده N کندل بسته‌ی اخیر > +x٪، SHORT اگر < −x٪، وگرنه WAIT.
اجرا با همان LivePaperAccount (SL/TP بر اساس ATR، کارمزد، ریسک ۱٪)."""
import numpy as np
import pandas as pd


def momentum_return(raw, bars):
    c = raw["Close"].astype(float)
    return float(c.iloc[-1] / c.iloc[-1 - bars] - 1) if len(c) > bars else float("nan")


def momentum_journal(feat, bars, pct):
    """journal سازگار با LivePaperAccount.update: ستون‌های action, P_bull, P_bear, P_range, doubt."""
    r = feat["Close"].astype(float).pct_change(bars)
    thr = pct / 100.0
    act = np.where(r > thr, "LONG", np.where(r < -thr, "SHORT", "WAIT"))
    strength = (r.abs() / max(thr, 1e-9)).clip(0, 2).fillna(0) / 2
    return pd.DataFrame(dict(action=act, P_bull=np.where(r > 0, strength, 0.0), P_bear=np.where(r < 0, strength, 0.0),
                             P_range=0.0, doubt=0.0, ret=r), index=feat.index)
