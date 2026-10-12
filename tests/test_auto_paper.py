import numpy as np
import pandas as pd
import pytest

from core.live_account import LivePaperAccount
from core.mind import MindConfig
from core.paper import CostModel, close_at, open_position


def _feat(prices, start="2026-10-06 10:00"):
    idx = pd.date_range(start, periods=len(prices), freq="h", tz="America/New_York")
    p = np.asarray(prices, float)
    return pd.DataFrame(dict(Open=p, High=p + 1, Low=p - 1, Close=p, ATR=10.0, Market_Open=True, Volume=1.0), index=idx)


def _journal(feat, actions):
    j = pd.DataFrame(dict(action=actions, P_bull=0.7, P_bear=0.2, P_range=0.1, doubt=0.2), index=feat.index)
    return j


def _acc(tmp_path, feat):
    cfg = MindConfig(start_equity=600, capital_cap=600, kill_equity=420, leverage=20.0)
    return LivePaperAccount("gold", 600, cfg, path=tmp_path / "a.json", now=feat.index[0] - pd.Timedelta(hours=1))


def test_long_opens_next_open_and_hits_tp(tmp_path):
    f = _feat([4000, 4000, 4000, 4100, 4100])
    acc = _acc(tmp_path, f)
    acc.update(f, _journal(f, ["LONG", "WAIT", "WAIT", "WAIT", "WAIT"]), awake=True)
    t = acc.trades_frame()
    assert len(t) == 1 and t.iloc[0].direction == "LONG" and t.iloc[0].reason == "target"
    assert pd.Timestamp(t.iloc[0].entry_time) == f.index[1]                       # Open of next bar, not the signal bar
    assert t.iloc[0].confidence == pytest.approx(0.7 * 0.8)
    assert t.iloc[0].stop < t.iloc[0].entry < t.iloc[0].target
    s = acc.stats(4100)
    assert s["n"] == 1 and s["wins"] == 1 and s["mood"] == "bull" and s["realized"] == pytest.approx(t.pnl.sum())
    assert acc.equity == pytest.approx(600 + t.pnl.sum(), abs=0.01)


def test_opposite_signal_closes_and_reverses(tmp_path):
    f = _feat([4000, 4000, 4002, 4001, 4001])
    acc = _acc(tmp_path, f)
    acc.update(f, _journal(f, ["LONG", "WAIT", "SHORT", "WAIT", "WAIT"]), awake=True)
    t = acc.trades_frame()
    assert t.iloc[0].reason == "opposite" and pd.Timestamp(t.iloc[0].exit_time) == f.index[3]
    assert acc.state["position"]["direction"] == -1                               # reversed into SHORT


def test_missed_bars_still_trade_but_last_bar_needs_awake(tmp_path):
    f = _feat([4000] * 6)
    acc = _acc(tmp_path, f)
    acc.update(f, _journal(f, ["WAIT", "LONG", "WAIT", "WAIT", "WAIT", "SHORT"]), awake=False)
    assert acc.state["position"] is not None and acc.state["position"]["direction"] == 1   # bar 1 signal used
    assert acc.state["pending"] is None                                           # last bar ignored while asleep


def test_closed_market_no_entry(tmp_path):
    f = _feat([4000] * 4); f["Market_Open"] = False
    acc = _acc(tmp_path, f)
    acc.update(f, _journal(f, ["LONG"] * 4), awake=True)
    assert acc.state["position"] is None and acc.trades_frame().empty


def test_floating_and_stats_drawdown(tmp_path):
    f = _feat([4000, 4000, 4000])
    acc = _acc(tmp_path, f)
    acc.update(f, _journal(f, ["SHORT", "WAIT", "WAIT"]), awake=True)
    pos = acc.state["position"]
    fl = acc.floating(3990)
    assert fl == pytest.approx(pos["qty"] * (3990 - pos["entry"]) * -1 - pos["fees"] - pos["funding"])
    acc.state["trades"] = [dict(entry_time="a", exit_time="b", direction="LONG", pnl=10.0),
                           dict(entry_time="c", exit_time="d", direction="LONG", pnl=-30.0),
                           dict(entry_time="e", exit_time="f", direction="SHORT", pnl=5.0)]
    s = acc.stats(None)
    assert s["n"] == 3 and s["wins"] == 2 and s["losses"] == 1 and s["win_rate"] == pytest.approx(2 / 3)
    assert s["avg_win"] == pytest.approx(7.5) and s["avg_loss"] == pytest.approx(-30)
    assert s["max_dd"] == pytest.approx(30 / 610)                                  # peak 610 → 580
    assert s["mood"] == "bear"


def test_csv_roundtrip_restore(tmp_path):
    f = _feat([4000, 4000, 4000, 4100, 4100])
    acc = _acc(tmp_path, f)
    acc.update(f, _journal(f, ["LONG", "WAIT", "WAIT", "WAIT", "WAIT"]), awake=True)
    data, eq = acc.to_csv(), acc.equity
    fresh = LivePaperAccount("gold", 600, acc.cfg, path=tmp_path / "b.json", now=f.index[0])
    assert fresh.import_csv(data) == 1 and fresh.equity == pytest.approx(eq, abs=0.01)
    assert fresh.import_csv(data) == 0                                            # no duplicates
    db = fresh.mirror_sqlite(tmp_path / "t.sqlite")
    import sqlite3
    assert sqlite3.connect(db).execute("select count(*) from trades").fetchone()[0] == 1


def test_close_at_costs():
    cm = CostModel(leverage=20.0)
    p = open_position(cm, 600, 1, 4000, 10, 15, 30, risk_frac=0.01)
    close_at(cm, p, 4000, 10, "opposite")
    assert p.pnl < 0 and p.reason == "opposite"                                   # flat price → costs only


def test_motor_normal_from_open_bars_only():
    """Regression (live account showed 0 trades): PAXG trades 24/7, quiet off-hours bars must not make normal
    open-market bars look stressful and pin ATP to its floor."""
    from core.motor_engine import MetabolicMotorSystem
    idx = pd.date_range("2026-10-05", periods=1000, freq="h", tz="America/New_York")
    op = (np.arange(1000) % 24) < 15                               # 15 open hours, 9 quiet hours
    rng = np.where(op, 4.0, 0.8)
    rnd = np.random.default_rng(1)
    vol = np.where(op, 1.0, 0.1) * rnd.lognormal(0, 1.5, 1000)      # heavy-tailed token volume
    df = pd.DataFrame(dict(Open=4000.0, High=4000 + rng / 2, Low=4000 - rng / 2, Close=4000 + rnd.normal(0, 1, 1000),
                           Volume=vol, Market_Open=op), index=idx)
    out = MetabolicMotorSystem().calculate_motor_drive(df)
    assert (out.ATP_Energy[op] < 30).mean() < 0.1
