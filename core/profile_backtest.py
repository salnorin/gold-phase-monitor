# core/profile_backtest.py
"""
بک‌تست پروفایل‌ها (normal / strict / active) روی تاریخچه‌ی PAXG-USD ۱ ساعته — فقط کاغذی.
همان موتور حساب زنده (LivePaperAccount: ورود در Open کندل بعد، SL/TP بر اساس ATR، کارمزد/فاندینگ، ساعات بازار)،
یک‌جا روی کل تاریخچه پس از گرم شدن. بدون نگاه به آینده (ذهن فقط کندل‌های بسته‌شده را می‌بیند).
    python -m core.profile_backtest [--bars 5000] [--warmup 300] [--csv paxg.csv] [--mom-bars 4 --mom-pct 0.3]
"""
import argparse
import tempfile
from pathlib import Path

import pandas as pd

from core.config import momentum_params, profile_overrides


def run_profile(raw, profile, cap, warmup=300, mp=None, leverage=20.0):
    from core.decision import _features
    from core.live_account import LivePaperAccount
    from core.mind import Mind, capital_mind_config
    from core.momentum import momentum_journal
    cfg = capital_mind_config(cap, leverage=leverage, bar_hours=1.0, **profile_overrides(profile))
    feat = _features(raw, None)
    if profile == "active":
        mp = mp or momentum_params()
        journal = momentum_journal(feat, mp.bars, mp.pct)
    else:
        journal = Mind(cfg).run(feat)
    start = feat.index[min(warmup, len(feat) - 2)]
    with tempfile.TemporaryDirectory() as d:
        acc = LivePaperAccount("gold", cap.usd, cfg, path=Path(d) / "bt.json", now=start)
        sig = journal["action"].iloc[-1]
        acc.update(feat, journal, True, signal=sig)
        st = acc.stats(float(raw["Close"].iloc[-1]))
        signals = int((journal.loc[journal.index > start, "action"] != "WAIT").sum())
        t = acc.trades_frame()
    return dict(profile=profile, signals=signals, trades=st["n"], wins=st["wins"],
                win_rate=st["win_rate"], pnl_usd=round(st["realized"], 2), change_pct=st["change_pct"],
                max_dd=st["max_dd"], avg_R=float(t["R"].astype(float).mean()) if len(t) else None,
                bars=int((feat.index > start).sum()), start=str(start), end=str(feat.index[-1]))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", type=int, default=5000)
    ap.add_argument("--warmup", type=int, default=300)
    ap.add_argument("--csv")
    ap.add_argument("--mom-bars", type=int)
    ap.add_argument("--mom-pct", type=float)
    ap.add_argument("--profiles", default="normal,strict,active")
    a = ap.parse_args(argv)
    from core.fx import paper_capital
    if a.csv:
        raw = pd.read_csv(a.csv, index_col=0, parse_dates=True)
    else:
        from core import gold_price
        raw = gold_price.candles("1h", a.bars)
    cap = paper_capital()
    mp = momentum_params(a.mom_bars, a.mom_pct)
    rows = [run_profile(raw, p, cap, a.warmup, mp) for p in a.profiles.split(",")]
    df = pd.DataFrame(rows).set_index("profile")
    print(df.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
