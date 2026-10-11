import os
import numpy as np
import pandas as pd
import pytest

from core.brain import Brain, Trade, check_exit
from core.config import OrganismConfig
from core.organism import BiologicalOrganism
from core.morphogenesis import MorphogenesisManager
from core.backtest import metrics, simulate
from tests.conftest import make_ohlcv

COLS = ["Weighted_Breath", "Long_Zone", "Slaughter_Zone", "ATR", "ATP_Energy",
        "Cortisol_Stress", "Optical_Pull", "Motor_Drive"]


def features(raw):
    return BiologicalOrganism().build_features(raw)


def test_features_no_lookahead():
    """ویژگی‌های کندل t نباید با اضافه شدن داده‌ی آینده تغییر کنند."""
    raw = make_ohlcv(800, seed=1)
    k = 500
    short, full = features(raw.iloc[:k]), features(raw)
    idx = short.index.intersection(full.index)
    assert len(idx) > 200
    pd.testing.assert_frame_equal(short.loc[idx, COLS], full.loc[idx, COLS], check_dtype=False)


def test_brain_signals_no_lookahead():
    """سیگنال‌ها و حالت جریان خون در t با الحاق آینده عوض نمی‌شوند (یادگیری فقط از گذشته)."""
    raw = make_ohlcv(900, seed=2)
    cfg = OrganismConfig(min_score=0.1, min_confidence=0.05, atp_floor=10)
    k = 600
    a, _ = Brain(cfg).run(features(raw.iloc[:k]))
    b, _ = Brain(cfg).run(features(raw))
    cols = ["Signal_Dir", "score", "confidence", "fatigue", "Weight_respiration", "Target_Price"]
    pd.testing.assert_frame_equal(a[cols], b.loc[a.index, cols])


def test_signals_exist_on_synthetic():
    cfg = OrganismConfig(min_score=0.1, min_confidence=0.05, atp_floor=10)
    out, trades = Brain(cfg).run(features(make_ohlcv(1500, seed=3)))
    assert (out["Signal_Dir"] != 0).sum() > 0


def test_atr_targets_in_dollars(ohlcv):
    cfg = OrganismConfig(min_score=0.1, min_confidence=0.05, atp_floor=10, target_atr_mult=2.0, stop_atr_mult=1.0)
    out, _ = Brain(cfg).run(features(ohlcv))
    s = out[out.Signal_Dir != 0]
    if len(s):
        np.testing.assert_allclose((s.Target_Price - s.Close).abs(), 2.0 * s.ATR)
        np.testing.assert_allclose((s.Close - s.Stop_Loss).abs(), 1.0 * s.ATR)


def test_check_exit_stop_first_when_both_hit():
    t = Trade(1, None, None, 100, 102, 99, 1, {})
    assert check_exit(t, 100, 103, 98, 101, 1, 24) == (99, "stop")
    assert check_exit(t, 100, 102.5, 99.5, 101, 1, 24) == (102, "target")
    assert check_exit(t, 100, 101, 99.5, 100.5, 24, 24) == (100.5, "time")


def test_learning_and_fatigue():
    cfg = OrganismConfig()
    b = Brain(cfg)
    for _ in range(3):
        t = Trade(1, None, None, 100, 102, 99, 1, {"respiration": 1.0, "optical": -1.0, "motor": 0.0})
        t.exit = 99
        b.learn(t)
    assert b.blood.weights["respiration"] < cfg.initial_weights["respiration"]
    assert b.blood.weights["optical"] > cfg.initial_weights["optical"]
    assert b.blood.weights["motor"] == cfg.initial_weights["motor"]
    assert b.blood.sleeping_bars == cfg.sleep_bars and b.blood.fatigue > 0


def test_metrics():
    ts = []
    for ex in (102, 99, 102):
        t = Trade(1, None, None, 100, 102, 99, 1, {}); t.exit = ex; ts.append(t)
    m = metrics(ts)
    assert m["trades"] == 3 and m["win_rate"] == 66.7 and m["profit_factor"] == 4.0 and m["max_dd_R"] == 1.0


def test_simulate_runs(ohlcv):
    f = features(ohlcv)
    d = np.zeros(len(f), int); d[100] = 1
    c, a = f.Close.values, f.ATR.values
    tr = simulate(f, d, c + 2 * a, c - a, 24)
    assert len(tr) == 1 and tr[0].entry == f.Open.iloc[101]


def test_spawn_disabled(monkeypatch, tmp_path):
    monkeypatch.delenv("GPM_ALLOW_DYNAMIC_ORGANS", raising=False)
    m = MorphogenesisManager(organs_dir=str(tmp_path))
    with pytest.raises(PermissionError):
        m.spawn_new_organ("Evil", "import os")
    assert not list(tmp_path.iterdir())
