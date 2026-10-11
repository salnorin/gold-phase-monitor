import numpy as np
import pandas as pd

import core.research as R
from core.brain import Brain, Trade
from core.config import OrganismConfig
from core.organism import BiologicalOrganism
from tests.conftest import make_ohlcv


def feat(n=900, seed=5):
    return BiologicalOrganism().build_features(make_ohlcv(n, seed))


def test_cross_signal_no_lookahead():
    f = feat()
    cross = make_ohlcv(900, seed=9)
    a = R.add_cross(f.iloc[:600], cross.iloc[:600])["Cross_Drive"]
    b = R.add_cross(f, cross)["Cross_Drive"].iloc[:600]
    np.testing.assert_allclose(a.values, b.values)
    assert a.abs().max() <= 1


def test_cross_weight_zero_is_ignored():
    f = R.add_cross(feat(), make_ohlcv(900, seed=9))
    cfg = OrganismConfig(min_score=0.1, min_confidence=0.05, atp_floor=10)
    a, _ = Brain(cfg).run(f)
    b, _ = Brain(cfg).run(f.drop(columns="Cross_Drive"))
    pd.testing.assert_series_equal(a["Signal_Dir"], b["Signal_Dir"])
    assert (a["Weight_cross"] == 0).all()


def test_cost_reduces_r():
    t = Trade(1, None, None, 100, 102, 99, 1, {}, cost=0.1); t.exit = 102
    assert abs(t.r_multiple - 1.9) < 1e-9


def test_search_uses_only_given_data(monkeypatch):
    monkeypatch.setattr(R, "GRID", {"min_score": [0.1, 0.3], "min_confidence": [0.05], "target_atr_mult": [1.5],
                                    "stop_atr_mult": [1.0], "max_hold_bars": [12],
                                    "require_respiration": [False], "cross_weight": [0.0]})
    f = feat(1200)
    best, table = R.search(f.iloc[:800], OrganismConfig(atp_floor=10), min_trades_per_fold=1, workers=1)
    assert len(table) == 2 and best["min_score"] in (0.1, 0.3)
    # همان جستجو روی IS با آینده‌ی متفاوت → همان نتیجه
    f2 = BiologicalOrganism().build_features(pd.concat([make_ohlcv(1200, 5).iloc[:800], make_ohlcv(400, 77)
                                             .set_axis(make_ohlcv(1200, 5).index[800:])]))
    best2, _ = R.search(f2.iloc[:800], OrganismConfig(atp_floor=10), min_trades_per_fold=1, workers=1)
    assert best == best2


def test_random_baseline_shape():
    f = feat()
    tot, avg = R.random_baseline(f, 5, OrganismConfig(), f.index[600], n_runs=20)
    assert len(tot) == 20 and np.isfinite(tot).all()
