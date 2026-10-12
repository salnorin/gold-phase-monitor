# core/recorder.py
"""
ضبط‌کنندهٔ پس‌زمینه برای معاملات کاغذی خودکار — روی کامپیوتر/VPS/Termux (نه Streamlit Cloud).
همان مسیر تصمیم یگانه (core.decision.organism_decision) + همان LivePaperAccount، هر N ثانیه؛ معاملات در SQLite دائمی.
فقط کاغذی؛ هیچ سفارش واقعی و هیچ کلیدی.
    python -m core.recorder                 # هر ۶۰ ثانیه، تا Ctrl+C
    python -m core.recorder --once          # یک دور (برای cron)
    python -m core.recorder --export trades.csv
    python -m core.recorder --data-dir ~/.local/share/gold-phase-monitor/gold-a   # نسخه‌ی مستقل
"""
import argparse
import sys
import time

import pandas as pd


def log_tick(db, now, price, action, asleep, s):
    """یک ردیف وضعیت در هر دور (برای داشبورد سبک)؛ جدول جدا، جدول trades دست نمی‌خورد."""
    import sqlite3
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS ticks (time TEXT PRIMARY KEY, price REAL, decision TEXT, asleep INTEGER,"
                " equity REAL, change_pct REAL, open INTEGER)")
    con.execute("INSERT OR REPLACE INTO ticks VALUES (?,?,?,?,?,?,?)",
                [str(now), price, str(action), int(bool(asleep)), float(s["equity"]), float(s["change_pct"]), int(bool(s["open"]))])
    con.commit(); con.close()


def _acc_kw(data_dir=None):
    from pathlib import Path
    return dict(path=Path(data_dir).expanduser() / "live_account_gold.json") if data_dir else {}


def cycle(acc_kw=None, interval="1h", leverage=20.0, db=None):
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
    db = acc.mirror_sqlite(db)
    price = gold_price.ticker()
    s = acc.stats(price, cap.eur, cap.rate)
    try:
        log_tick(db, now, price, dec.action, dec.asleep, s)
    except Exception as e:
        print("tick log error:", e, flush=True)
    print(f"{now.tz_convert('Europe/Berlin'):%Y-%m-%d %H:%M:%S} Berlin | PAXG {price} | decision {dec.action}"
          f"{' (asleep)' if dec.asleep else ''} | new bars {n} | equity {s['equity']:.2f}$ ({s['change_pct']:+.2%}) | "
          f"trades {s['n']} win {s['win_rate'] if s['win_rate'] is not None else '—'} | open {s['open']} | {db}", flush=True)
    return acc


def main(argv=None):
    ap = argparse.ArgumentParser(description="Paper-only auto trade recorder (SQLite)")
    ap.add_argument("--every", type=float, default=60)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--export")
    ap.add_argument("--data-dir", default=None, help="پوشه‌ی دیتای این نسخه (پیش‌فرض: GPM_DATA_DIR یا ~/.local/share/gold-phase-monitor)")
    ap.add_argument("--db", default=None, help="مسیر فایل SQLite (پیش‌فرض: کنار فایل JSON حساب)")
    a = ap.parse_args(argv)
    kw = _acc_kw(a.data_dir)
    if a.export:
        from core.fx import paper_capital
        from core.live_account import LivePaperAccount
        from core.mind import capital_mind_config
        cap = paper_capital()
        acc = LivePaperAccount("gold", cap.usd, capital_mind_config(cap, leverage=20.0), **kw)
        open(a.export, "wb").write(acc.to_csv()); print(a.export); return 0
    while True:
        try:
            cycle(kw, db=a.db)
        except Exception as e:                       # شبکه قطع شد → دور بعد
            print("error:", type(e).__name__, e, flush=True)
        if a.once:
            return 0
        time.sleep(a.every)


if __name__ == "__main__":
    sys.exit(main())
