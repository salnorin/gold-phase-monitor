# core/backtest.py
"""بک‌تست walk-forward: منطق قدیم در برابر جدید، تفکیک in-sample / out-of-sample.
اجرا: python -m core.backtest [--days 720] [--csv data.csv]"""
import argparse
from dataclasses import replace
import numpy as np
import pandas as pd

from core.brain import Brain, Trade, check_exit
from core.config import DEFAULT_CONFIG
from core.organism import BiologicalOrganism
from core.legacy import legacy_signals


def simulate(df, dirs, targets, stops, max_hold):
    """شبیه‌ساز عمومی: سیگنال در Close کندل i، ورود Open کندل i+1. فاصله‌ی تارگت/استاپ حفظ می‌شود."""
    o, h, l, c = (df[k].values for k in ("Open", "High", "Low", "Close"))
    trades, i, n = [], 0, len(df)
    while i < n - 1:
        d = int(dirs[i])
        if d == 0 or targets[i] == 0 or stops[i] == 0:
            i += 1; continue
        entry = o[i + 1]
        t_dist, s_dist = (targets[i] - c[i]) * d, (c[i] - stops[i]) * d
        if t_dist <= 0 or s_dist <= 0:
            i += 1; continue
        tr = Trade(d, df.index[i], df.index[i + 1], entry, entry + d * t_dist, entry - d * s_dist, s_dist, {})
        j, held = i + 1, 0
        while j < n:
            held += 1
            px, why = check_exit(tr, o[j], h[j], l[j], c[j], held, max_hold)
            if px is not None:
                tr.exit, tr.exit_time, tr.reason = px, df.index[j], why; break
            j += 1
        if tr.exit is None:
            break  # تا انتهای داده باز ماند → شمرده نمی‌شود
        trades.append(tr); i = j + 1 if j > i + 1 else i + 1
        i = max(i, j)
    return trades


def metrics(trades):
    if not trades:
        return dict(trades=0, win_rate=0.0, avg_R=0.0, profit_factor=0.0, max_dd_R=0.0, total_R=0.0)
    r = np.array([t.r_multiple for t in trades])
    eq = np.cumsum(r); dd = np.max(np.maximum.accumulate(np.concatenate([[0], eq]))[1:] - eq)
    gains, losses = r[r > 0].sum(), -r[r <= 0].sum()
    return dict(trades=len(r), win_rate=round(100 * (r > 0).mean(), 1), avg_R=round(r.mean(), 3),
                profit_factor=round(gains / losses, 2) if losses > 0 else float("inf"),
                max_dd_R=round(max(dd, 0), 2), total_R=round(r.sum(), 2))


def split(trades, cut):
    return [t for t in trades if t.signal_time < cut], [t for t in trades if t.signal_time >= cut]


def run_backtest(raw, cfg=DEFAULT_CONFIG, is_frac=0.7):
    org = BiologicalOrganism(config=cfg)
    feat = org.build_features(raw)
    cut = feat.index[int(len(feat) * is_frac)]
    results = {}
    # منطق قدیم (با نگاه به آینده) – همان شبیه‌ساز
    leg = legacy_signals(feat)
    results["old (v1, look-ahead)"] = simulate(leg, leg["Legacy_Dir"].values, leg["Legacy_Target"].values,
                                               leg["Legacy_Stop"].values, cfg.max_hold_bars)
    # منطق قدیم + ATR (برای جداکردن اثر اندازه‌ی تارگت)
    atr = feat["ATR"].values; d = leg["Legacy_Dir"].values; c = feat["Close"].values
    results["old rules + ATR exits"] = simulate(feat, d, c + d * atr * cfg.target_atr_mult,
                                                np.where(d != 0, c - d * atr * cfg.stop_atr_mult, 0), cfg.max_hold_bars)
    # جدید بدون یادگیری / با یادگیری (walk-forward آنلاین، از ابتدا)
    _, t0 = Brain(replace(cfg, learning_rate=0.0, fatigue_per_loss=0.0, losses_to_sleep=10**9)).run(feat)
    results["new v2, no learning"] = t0
    _, t1 = Brain(cfg).run(feat)
    results["new v2, adaptive"] = t1
    rows = []
    for name, tr in results.items():
        a, b = split(tr, cut)
        rows.append({"logic": name, "set": "in-sample", **metrics(a)})
        rows.append({"logic": name, "set": "out-of-sample", **metrics(b)})
    return pd.DataFrame(rows), feat.index[0], cut, feat.index[-1]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=720)
    ap.add_argument("--csv")
    a = ap.parse_args()
    if a.csv:
        raw = pd.read_csv(a.csv, index_col=0)
        raw.index = pd.to_datetime(raw.index, utc=True).tz_convert("America/New_York")
    else:
        raw = BiologicalOrganism().respiration.fetch_raw_data(DEFAULT_CONFIG.symbol, "1h", a.days)
    table, start, cut, end = run_backtest(raw)
    print(f"bars={len(raw)}  IS: {start} → {cut}  OOS: {cut} → {end}")
    print(table.to_string(index=False))
