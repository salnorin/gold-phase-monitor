import pytest
import numpy as np
import pandas as pd

from core.mind import BlackBox, Mind, MindConfig, mind_features
from core.organism import BiologicalOrganism
from core.paper import Position
from tests.conftest import make_ohlcv

DECISION_COLS = ["P_bull", "P_bear", "P_range", "oxygen", "whale", "intuition", "evidence", "doubt",
                 "trust", "strategy", "action", "reason", "juice", "in_position"]


def feats(n, seed):
    return BiologicalOrganism().build_features(make_ohlcv(n, seed))


def test_mind_no_lookahead():
    raw = make_ohlcv(1000, seed=11)
    k = 700
    a = Mind().run(BiologicalOrganism().build_features(raw.iloc[:k]))
    b = Mind().run(BiologicalOrganism().build_features(raw))
    # کندل آخر پیشوند: سیگنال ممکن است «در کندل آخر» باشد ولی اقدام یکسان است؛ ستون‌ها تا k-1 کاملاً برابرند
    pd.testing.assert_frame_equal(a[DECISION_COLS].iloc[:-1], b.loc[a.index[:-1], DECISION_COLS])
    assert a["action"].iloc[-1] == b.loc[a.index[-1], "action"]


def test_state_probabilities_sum_to_one():
    f = mind_features(feats(500, 3), MindConfig())
    np.testing.assert_allclose(f[["P_bull", "P_bear", "P_range"]].sum(axis=1), 1.0)


def _ctx(**kw):
    c = dict(P_bull=0.7, P_bear=0.1, P_range=0.2, Oxygen=1.0, Vol_Ratio=1.0, Whale=False, hour=10)
    c.update(kw); return c


def test_blackbox_blocks_similar_context_and_releases():
    bb = BlackBox(distance=0.3, ttl=100)
    pos = Position(1, 100, 1, 5, 99, 103, 95, 0, reason="stop", bars=1, pnl=-1, risk_cash=1)
    bb.record(_ctx(), pos, "trend", index=10, time="t")
    assert bb.blocked(_ctx(P_bull=0.68, P_bear=0.12), 1, "trend", 20)          # مشابه → مسدود
    assert bb.blocked(_ctx(), -1, "trend", 20) is None                           # جهت دیگر
    assert bb.blocked(_ctx(), 1, "reversion", 20) is None                        # استراتژی دیگر
    assert bb.blocked(_ctx(P_bull=0.1, P_bear=0.2, P_range=0.7, Vol_Ratio=2.5), 1, "trend", 20) is None  # شرایط فرق کرد
    assert bb.blocked(_ctx(), 1, "trend", 200) is None                           # منقضی شد
    assert "stopped_fast" in BlackBox.tags(_ctx(), pos)


def test_risk_scaling():
    m = Mind()
    base = m.risk_fraction()
    assert abs(base - 0.0075) < 1e-12 and m.cfg.max_risk == 0.01
    m.equity = m.peak * 0.95                       # آب‌میوه افت کرد → ریسک کمتر
    assert m.risk_fraction() < base
    m.equity = m.peak * 0.85
    assert m.risk_fraction() == m.cfg.min_risk * 1.0 or m.risk_fraction() <= 0.0025 + 1e-12
    m.equity = m.peak
    assert abs(m.risk_fraction(wins_streak=3) - 0.007875) < 1e-12   # رشد آهسته
    assert m.risk_fraction(wins_streak=100) == m.cfg.max_risk == 0.01
    assert abs(m.risk_fraction(recovery=3) - 0.00375) < 1e-12        # پس از افت ۱۰٪


def test_doubt_trust_update():
    m = Mind()
    t0 = m.trust["bull"]
    assert m.update_trust("bull", +0.8, -0.5, move=+1) is True and m.trust["bull"] > t0
    assert m.update_trust("bull", +0.8, -0.5, move=-1) is False and abs(m.trust["bull"] - t0) < 1e-12
    assert m.update_trust("bull", +0.8, +0.5, move=-1) is None      # هم‌نظر بودند → تغییری نیست
    for _ in range(50):
        m.update_trust("range", -0.5, 0.5, move=1)
    assert m.trust["range"] == 0.1                                      # کران پایین


def test_hard_limits_and_journal(tmp_path):
    m = Mind(MindConfig(vol_rest_ratio=0.0))      # همیشه «نوسان زیاد» → هرگز معامله نمی‌کند
    j = m.run(feats(600, 4))
    assert (j["action"] == "WAIT").all() and not m.trades
    p = m.save_journal(str(tmp_path / "j.sqlite"))
    import sqlite3
    with sqlite3.connect(p) as con:
        assert con.execute("select count(*) from decisions").fetchone()[0] == len(j)


def test_mind_trades_synthetic():
    m = Mind(MindConfig(whale_volume=99, whale_range_atr=99, low_oxygen=0.0))
    m.run(feats(2000, 7))
    assert all(p.margin <= p.notional / 20 + 1e-6 for p in m.trades)


def test_market_hours_and_stale():
    from core.market_hours import is_market_open, is_stale, market_status
    B = "Europe/Berlin"
    ts = lambda s: pd.Timestamp(s, tz=B)
    assert is_market_open(ts("2026-10-07 15:00"))          # چهارشنبه
    assert not is_market_open(ts("2026-10-07 23:30"))      # وقفه‌ی روزانه
    assert not is_market_open(ts("2026-10-09 23:30"))      # جمعه شب
    assert not is_market_open(ts("2026-10-10 12:00"))      # شنبه
    assert not is_market_open(ts("2026-10-11 22:00"))      # یکشنبه قبل از باز شدن
    assert is_market_open(ts("2026-10-12 00:30"))          # دوشنبه 00:30 برلین = یکشنبه 17:30 CT
    assert is_stale(ts("2026-10-07 10:00"), ts("2026-10-07 14:00"), 1.0)
    assert not is_stale(ts("2026-10-07 12:00"), ts("2026-10-07 13:30"), 1.0)
    assert market_status(ts("2026-10-07 12:00"), ts("2026-10-07 13:30"), 1.0)[0]


def test_no_signal_when_closed_or_stale():
    f = feats(800, 7)
    j = Mind(MindConfig(whale_volume=99, whale_range_atr=99, low_oxygen=0.0)).run(f, now=f.index[-1] + pd.Timedelta(days=3))
    assert j["action"].iloc[-1] == "WAIT" and "خواب" in j["reason"].iloc[-1] and not j["market_open"].iloc[-1]
    from core.market_hours import is_market_open
    closed = [not is_market_open(t) for t in j.index]
    assert (j.loc[closed, "action"] == "WAIT").all()


def test_forming_candle_holiday_and_reopen():
    from core.market_hours import drop_forming_candle, is_market_open, open_mask
    idx = pd.date_range("2026-10-07 10:00", periods=3, freq="h", tz="UTC")
    df = pd.DataFrame({"Close": [1, 2, 3]}, index=idx)
    assert len(drop_forming_candle(df, 1.0, now=pd.Timestamp("2026-10-07 12:30", tz="UTC"))) == 2
    assert len(drop_forming_candle(df, 1.0, now=pd.Timestamp("2026-10-07 13:00", tz="UTC"))) == 3
    assert not is_market_open(pd.Timestamp("2026-12-25 15:00", tz="Europe/Berlin"))   # کریسمس
    # یکشنبه 17:00 CT بازگشایی → اولین کندل مسدود، دومی آزاد
    reopen = pd.date_range("2026-10-11 17:00", periods=3, freq="h", tz="America/Chicago")
    fri = pd.DatetimeIndex([pd.Timestamp("2026-10-09 14:00", tz="America/Chicago")])
    m = open_mask(fri.append(reopen), 1.0)
    assert list(m) == [True, False, True, True]


def test_capital_from_mocked_rate(tmp_path, monkeypatch):
    import core.fx as fx
    from core.config import PAPER_CAPITAL_EUR
    from core.mind import capital_mind_config
    monkeypatch.setattr(fx, "CACHE_DIR", str(tmp_path))
    q = fx.FxQuote(1.10, pd.Timestamp("2026-10-10", tz="UTC"), "mock")
    good = lambda: q
    assert fx.eur_usd(use_cache=False, providers=[good]).rate == 1.10
    cap = fx.paper_capital(fx.eur_usd(use_cache=False, providers=[good]))
    assert PAPER_CAPITAL_EUR == 540.16 and cap.usd == 594.18 and cap.risk_usd == 5.94 and cap.stop_usd == 415.93
    c = capital_mind_config(cap)
    assert c.start_equity == c.capital_cap == 594.18 and c.kill_equity == 415.93 and c.max_risk == 0.01
    # هر دو منبع شکست → آخرین نرخ معتبر با هشدار
    def bad(): raise ConnectionError("down")
    lk = fx.eur_usd(use_cache=False, providers=[bad, bad])
    assert lk.rate == 1.10 and lk.warning and "last known good" in lk.source
    # کش ۱۰ دقیقه‌ای: بدون فراخوانی منبع
    assert fx.eur_usd(use_cache=True, providers=[bad]).rate == 1.10
    # هیچ نرخی هرگز → خطا (نرخ ثابت در کد نیست)
    monkeypatch.setattr(fx, "CACHE_DIR", str(tmp_path / "empty"))
    with pytest.raises(RuntimeError):
        fx.eur_usd(use_cache=False, providers=[bad])
    with pytest.raises(RuntimeError):     # نرخ غیرمنطقی رد می‌شود
        fx.eur_usd(use_cache=False, providers=[lambda: fx.FxQuote(9.0, q.timestamp, "x")])


def test_status_detail_states():
    from core.market_hours import status_detail
    B = lambda s: pd.Timestamp(s, tz="Europe/Berlin")
    fri_last = B("2026-10-09 22:00")                       # آخرین کندل جمعه
    assert status_detail(fri_last, B("2026-10-10 12:00"), 1.0)[0] == "closed"
    assert status_detail(fri_last, B("2026-10-12 00:20"), 1.0)[0] == "awaiting"   # پس از بازگشایی یکشنبه
    assert status_detail(B("2026-10-07 10:00"), B("2026-10-07 15:00"), 1.0)[0] == "stale"
    assert status_detail(B("2026-10-07 13:00"), B("2026-10-07 14:30"), 1.0)[0] == "open"


def test_awake_with_fresh_minute_bar_and_feed_delay():
    from core.market_hours import status_detail
    now = pd.Timestamp("2026-10-12 00:25", tz="Europe/Berlin")            # دوشنبه بامداد، بازار باز
    assert status_detail(now - pd.Timedelta(minutes=2), now, 1 / 60)[0] == "open"
    assert status_detail(now - pd.Timedelta(minutes=11), now, 1 / 60, feed_delay_min=15)[0] == "open"
    assert status_detail(now - pd.Timedelta(minutes=11), now, 1 / 60)[0] != "open"
    assert status_detail(pd.Timestamp("2026-10-11 22:15", tz="UTC"), pd.Timestamp("2026-10-11 22:25", tz="UTC"), 1 / 60, 15)[0] == "open"


def test_paxg_does_not_open_gold_market():
    from core.market_hours import status_detail
    sat = pd.Timestamp("2026-10-10 12:00", tz="Europe/Berlin")   # PAXG معامله می‌شود، ولی بازار طلا بسته است
    assert status_detail(sat - pd.Timedelta(minutes=1), sat, 1 / 60)[0] == "closed"
