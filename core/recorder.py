# core/recorder.py
"""
ضبط‌کنندهٔ پس‌زمینه برای معاملات کاغذی خودکار — روی کامپیوتر/VPS/Termux (نه Streamlit Cloud).
همان مسیر تصمیم یگانه (core.decision.organism_decision) + همان LivePaperAccount، هر N ثانیه؛ معاملات در SQLite دائمی.
فقط کاغذی؛ هیچ سفارش واقعی و هیچ کلیدی.
    python -m core.recorder                 # هر ۶۰ ثانیه، تا Ctrl+C
    python -m core.recorder --once          # یک دور (برای cron)
    python -m core.recorder --export trades.csv
    python -m core.recorder --data-dir ~/.local/share/gold-phase-monitor/gold-a   # نسخه‌ی مستقل
    python -m core.recorder --profile active --mom-bars 4 --mom-pct 0.3      # strict | normal | active
"""
import argparse
import sys
import time

import pandas as pd


def log_tick(db, now, price, action, asleep, s, reason=None):
    """یک ردیف وضعیت در هر دور (برای داشبورد سبک)؛ جدول جدا، جدول trades دست نمی‌خورد. reason: JSON دروازه‌ها."""
    import json
    import sqlite3
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS ticks (time TEXT PRIMARY KEY, price REAL, decision TEXT, asleep INTEGER,"
                " equity REAL, change_pct REAL, open INTEGER)")
    if "reason" not in [r[1] for r in con.execute("PRAGMA table_info(ticks)")]:
        con.execute("ALTER TABLE ticks ADD COLUMN reason TEXT")          # سازگار با فایل‌های قدیمی
    con.execute("INSERT OR REPLACE INTO ticks (time, price, decision, asleep, equity, change_pct, open, reason)"
                " VALUES (?,?,?,?,?,?,?,?)",
                [str(now), price, str(action), int(bool(asleep)), float(s["equity"]), float(s["change_pct"]),
                 int(bool(s["open"])), json.dumps(reason, ensure_ascii=False, default=str) if reason else None])
    con.commit(); con.close()


def _acc_kw(data_dir=None):
    from pathlib import Path
    return dict(path=Path(data_dir).expanduser() / "live_account_gold.json") if data_dir else {}


def cycle(acc_kw=None, interval="1h", leverage=20.0, db=None, profile=None, mom=None):
    """profile: normal (پیش‌فرض، ارگانیسم بدون تغییر) | strict | active (مومنتوم). env GOLD_PROFILE."""
    import os
    from core import gold_price
    from core.config import momentum_params, profile_overrides
    from core.decision import live_signal, organism_decision
    from core.explain import gate_breakdown, momentum_breakdown
    from core.fx import paper_capital
    from core.live_account import LivePaperAccount
    from core.mind import capital_mind_config
    profile = profile or os.getenv("GOLD_PROFILE", "normal")
    cap = paper_capital()
    cfg = capital_mind_config(cap, leverage=float(leverage), bar_hours=1.0, **profile_overrides(profile))
    raw = gold_price.candles(interval, 2000)
    now = pd.Timestamp.now(tz="UTC")
    dec, ctx = organism_decision(raw, cfg, now)
    acc = LivePaperAccount("gold", cap.usd, cfg, **(acc_kw or {}))
    if profile == "active":
        from core.momentum import momentum_journal
        mp = mom or momentum_params()
        journal = momentum_journal(ctx["feat"], mp.bars, mp.pct)
        action = "WAIT" if dec.asleep else str(journal["action"].iloc[-1])
        n = acc.update(ctx["feat"], journal, not dec.asleep, signal=action)
        why = momentum_breakdown(raw, mp, action)
        why["items"].insert(0, dict(k="market", ok=not dec.asleep, v=dec.market_state))
    else:
        action = live_signal(dec)
        n = acc.update(ctx["feat"], ctx["journal"], not dec.asleep, signal=action)
        why = gate_breakdown(dec, ctx, cfg, raw, profile)
    db = acc.mirror_sqlite(db)
    price = gold_price.ticker()
    s = acc.stats(price, cap.eur, cap.rate)
    try:
        log_tick(db, now, price, action, dec.asleep, s, why)
    except Exception as e:
        print("tick log error:", e, flush=True)
    blocked = ", ".join(i["k"] for i in why["items"] if not i.get("ok", True)) or "-"
    print(f"{now.tz_convert('Europe/Berlin'):%Y-%m-%d %H:%M:%S} Berlin | {profile} | PAXG {price} | decision {action}"
          f"{' (asleep)' if dec.asleep else ''} | blocked: {blocked} | new bars {n} | equity {s['equity']:.2f}$ ({s['change_pct']:+.2%}) | "
          f"trades {s['n']} win {s['win_rate'] if s['win_rate'] is not None else '—'} | open {s['open']} | {db}", flush=True)
    if os.getenv("GOLD_EXPLAIN"):
        print(why, flush=True)
    return acc


def main(argv=None):
    ap = argparse.ArgumentParser(description="Paper-only auto trade recorder (SQLite)")
    ap.add_argument("--every", type=float, default=60)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--export")
    ap.add_argument("--data-dir", default=None, help="پوشه‌ی دیتای این نسخه (پیش‌فرض: GPM_DATA_DIR یا ~/.local/share/gold-phase-monitor)")
    ap.add_argument("--db", default=None, help="مسیر فایل SQLite (پیش‌فرض: کنار فایل JSON حساب)")
    ap.add_argument("--profile", choices=["normal", "strict", "active"], default=None,
                    help="normal (پیش‌فرض) | strict | active=مومنتوم؛ env GOLD_PROFILE")
    ap.add_argument("--mom-bars", type=int, default=None, help="active: N کندل (env GOLD_MOM_BARS، پیش‌فرض 4)")
    ap.add_argument("--mom-pct", type=float, default=None, help="active: x درصد (env GOLD_MOM_PCT، پیش‌فرض 0.30)")
    ap.add_argument("--explain", action="store_true", help="چاپ کامل دروازه‌ها در هر دور")
    a = ap.parse_args(argv)
    if a.explain:
        import os
        os.environ["GOLD_EXPLAIN"] = "1"
    kw = _acc_kw(a.data_dir)
    from core.config import momentum_params
    mom = momentum_params(a.mom_bars, a.mom_pct)
    if a.export:
        from core.fx import paper_capital
        from core.live_account import LivePaperAccount
        from core.mind import capital_mind_config
        cap = paper_capital()
        acc = LivePaperAccount("gold", cap.usd, capital_mind_config(cap, leverage=20.0), **kw)
        open(a.export, "wb").write(acc.to_csv()); print(a.export); return 0
    while True:
        try:
            cycle(kw, db=a.db, profile=a.profile, mom=mom)
        except Exception as e:                       # شبکه قطع شد → دور بعد
            print("error:", type(e).__name__, e, flush=True)
        if a.once:
            return 0
        time.sleep(a.every)


if __name__ == "__main__":
    sys.exit(main())
