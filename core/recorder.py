# core/recorder.py
"""
ضبط‌کنندهٔ پس‌زمینه برای معاملات کاغذی خودکار — روی کامپیوتر/VPS/Termux (نه Streamlit Cloud).
همان مسیر تصمیم یگانه (core.decision.organism_decision) + همان LivePaperAccount، هر N ثانیه؛ معاملات در SQLite دائمی.
فقط کاغذی؛ هیچ سفارش واقعی و هیچ کلیدی.
    python -m core.recorder                 # هر ۶۰ ثانیه، تا Ctrl+C
    python -m core.recorder --once          # یک دور (برای cron)
    python -m core.recorder --export trades.csv
"""
import argparse
import sys
import time

import pandas as pd


def cycle(acc_kw=None, interval="1h", leverage=20.0):
    from core import gold_price
    from core.decision import live_signal, organism_decision
    from core.fx import paper_capital
    from core.live_account import LivePaperAccount
    from core.mind import capital_mind_config
    cap = paper_capital()
    cfg = capital_mind_config(cap, leverage=float(leverage), bar_hours=1.0)
    raw = gold_price.candles(interval, 2000)
    now = pd.Timestamp.now(tz="UTC")
    dec, ctx = organism_decision(raw, cfg, now)
    acc = LivePaperAccount("gold", cap.usd, cfg, **(acc_kw or {}))
    n = acc.update(ctx["feat"], ctx["journal"], not dec.asleep, signal=live_signal(dec))
    db = acc.mirror_sqlite()
    price = gold_price.ticker()
    s = acc.stats(price, cap.eur, cap.rate)
    print(f"{now.tz_convert('Europe/Berlin'):%Y-%m-%d %H:%M:%S} Berlin | PAXG {price} | decision {dec.action}"
          f"{' (asleep)' if dec.asleep else ''} | new bars {n} | equity {s['equity']:.2f}$ ({s['change_pct']:+.2%}) | "
          f"trades {s['n']} win {s['win_rate'] if s['win_rate'] is not None else '—'} | open {s['open']} | {db}", flush=True)
    return acc


def main(argv=None):
    ap = argparse.ArgumentParser(description="Paper-only auto trade recorder (SQLite)")
    ap.add_argument("--every", type=float, default=60)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--export")
    a = ap.parse_args(argv)
    if a.export:
        from core.fx import paper_capital
        from core.live_account import LivePaperAccount
        from core.mind import capital_mind_config
        cap = paper_capital()
        acc = LivePaperAccount("gold", cap.usd, capital_mind_config(cap, leverage=20.0))
        open(a.export, "wb").write(acc.to_csv()); print(a.export); return 0
    while True:
        try:
            cycle()
        except Exception as e:                       # شبکه قطع شد → دور بعد
            print("error:", type(e).__name__, e, flush=True)
        if a.once:
            return 0
        time.sleep(a.every)


if __name__ == "__main__":
    sys.exit(main())
