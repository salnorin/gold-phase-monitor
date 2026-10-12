import sqlite3

import numpy as np
import pandas as pd
import pytest

from core.exec_prob import apply_exec_prob, live_action
from core.live_account import LivePaperAccount
from core.max_wait import WaitParams, step_wait, threshold
from core.mind import MindConfig


def _feat(prices):
    idx = pd.date_range("2026-10-06 10:00", periods=len(prices), freq="h", tz="America/New_York")
    p = np.asarray(prices, float)
    return pd.DataFrame(dict(Open=p, High=p + 1, Low=p - 1, Close=p, ATR=10.0, Market_Open=True, Volume=1.0), index=idx)


def _j(f, actions, pb=0.3, pr=0.2, reason="x"):
    return pd.DataFrame(dict(action=actions, P_bull=pb, P_bear=pr, P_range=0.5, doubt=0.2, reason=reason), index=f.index)


def _acc(tmp_path, f):
    cfg = MindConfig(start_equity=600, capital_cap=600, kill_equity=420, leverage=20.0)
    return LivePaperAccount("gold", 600, cfg, path=tmp_path / "a.json", now=f.index[0] - pd.Timedelta(hours=1))


def test_long_decision_auto_opens_with_sl_tp(tmp_path):
    f = _feat([4000] * 4)
    acc = _acc(tmp_path, f)
    acc.update(f, _j(f, ["LONG", "WAIT", "WAIT", "WAIT"]), True)
    p = acc.state["position"]
    assert p is not None and p["direction"] == 1
    assert p["stop"] == pytest.approx(p["entry"] - 15, abs=0.5) and p["target"] == pytest.approx(p["entry"] + 30, abs=0.5)  # ATR 10 × 1.5 / 3.0
    assert acc.state["last_event"]["kind"] == "opened" and acc.state["last_event"]["exec_by"] == "organism"


def test_every_closed_trade_records_sl_tp_and_tag(tmp_path):
    f = _feat([4000, 4000, 4000, 4100, 4100, 4100, 3900, 3900])
    acc = _acc(tmp_path, f)
    j = _j(f, ["LONG", "WAIT", "WAIT", "WAIT", "SHORT", "WAIT", "WAIT", "WAIT"])
    j["exec_by"] = ["prob", "", "", "", "forced", "", "", ""]
    acc.update(f, j, True)
    t = acc.trades_frame()
    assert len(t) >= 1 and t["stop"].notna().all() and t["target"].notna().all()
    assert t.iloc[0].exec_by == "prob"
    db = acc.mirror_sqlite()
    cols = [r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(trades)")]
    assert "exec_by" in cols
    assert "prob" in acc.stats(4000)["by_exec"]


def test_prob_threshold_executes_but_risk_veto_holds():
    idx = pd.date_range("2026-10-06", periods=3, freq="h", tz="UTC")
    j = pd.DataFrame(dict(action="WAIT", P_bull=[0.56, 0.56, 0.40], P_bear=[0.1, 0.1, 0.57], P_range=0.3, doubt=0.2,
                          reason=["احتیاط: ردپای نهنگ", "بازار بسته / اولین کندل پس از بازگشایی → خواب", "x"]), index=idx)
    out = apply_exec_prob(j, 0.55)
    assert list(out.action) == ["LONG", "WAIT", "SHORT"] and out.exec_by.iloc[0] == "prob"
    assert list(apply_exec_prob(j, 0).action) == ["WAIT"] * 3


class D:
    def __init__(self, **k):
        self.__dict__.update(dict(confirmed=None, asleep=False, action="WAIT", reason="x", P_bull=0.3, P_bear=0.2), **k)


def test_live_action():
    assert live_action(D(P_bull=0.55), 0.55) == ("LONG", "prob")
    assert live_action(D(P_bull=0.54), 0.55) == ("WAIT", "")
    assert live_action(D(P_bull=0.9, asleep=True), 0.55)[0] == "WAIT"
    assert live_action(D(P_bear=0.6, reason="توقف خودکار"), 0.55)[0] == "WAIT"


def test_max_wait_ramp_and_floor():
    wp = WaitParams(max_wait=23, step=0.01, floor=0.50, start=0.55)
    assert threshold(23, wp) is None and threshold(24, wp) == pytest.approx(0.54) and threshold(40, wp) == 0.50
    st = {}
    for _ in range(23):
        assert step_wait(st, "WAIT", 0.40, 0.30, True, True, "x", wp) == ("WAIT", None)
    a = None
    for _ in range(10):
        a = step_wait(st, "WAIT", 0.40, 0.30, True, True, "x", wp)
        if a[1]:
            break
    assert a == ("LONG", "forced") and st["wait_count"] == 0       # floor reached → higher side, counter reset


def test_max_wait_vetoes_and_reset():
    wp = WaitParams(max_wait=2)
    st = {"wait_count": 50}
    assert step_wait(st, "WAIT", 0.4, 0.3, False, True, "x", wp) == ("WAIT", None)          # market closed
    assert step_wait(st, "WAIT", 0.4, 0.3, True, True, "توقف خودکار", wp)[1] is None        # auto-stop
    assert step_wait(st, "WAIT", 0.4, 0.3, True, True, "x", wp, killed=True)[1] is None
    assert step_wait(st, "WAIT", 0.4, 0.3, True, False, "x", wp)[1] is None and st["wait_count"] == 0   # open position
    st["wait_count"] = 9
    step_wait(st, "LONG", 0.6, 0.1, True, True, "x", wp)
    assert st["wait_count"] == 0


def test_forced_never_reverses_open_position(tmp_path):
    f = _feat([4000, 4000, 4001, 4001])
    acc = _acc(tmp_path, f)
    j = _j(f, ["LONG", "WAIT", "SHORT", "WAIT"])
    j["exec_by"] = ["organism", "", "forced", ""]
    acc.update(f, j, True)
    assert acc.state["position"]["direction"] == 1 and len(acc.trades_frame()) == 0
