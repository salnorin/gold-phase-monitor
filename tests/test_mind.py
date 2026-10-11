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
    pd.testing.assert_frame_equal(a[DECISION_COLS].iloc[:k - 1], b[DECISION_COLS].iloc[:k - 1])
    assert (a["action"].iloc[-1] == b["action"].iloc[k - 1])


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
    assert abs(base - 0.01) < 1e-12
    m.equity = m.peak * 0.95                       # آب‌میوه افت کرد → ریسک کمتر
    assert m.risk_fraction() < base
    m.equity = m.peak * 0.85
    assert m.risk_fraction() == m.cfg.min_risk * 1.0 or m.risk_fraction() <= 0.0025 + 1e-12
    m.equity = m.peak
    assert m.risk_fraction(wins_streak=3) == 0.0105   # رشد آهسته
    assert m.risk_fraction(wins_streak=100) <= m.cfg.max_risk
    assert m.risk_fraction(recovery=3) == 0.005        # پس از افت ۱۰٪


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
        assert con.execute("select count(*) from decisions").fetchone()[0] == 600


def test_mind_trades_synthetic():
    m = Mind(MindConfig(whale_volume=99, whale_range_atr=99, low_oxygen=0.0))
    m.run(feats(2000, 7))
    assert all(p.margin <= p.notional / 20 + 1e-6 for p in m.trades)
