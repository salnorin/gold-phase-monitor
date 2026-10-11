"""Native Rust hot loop must match the numpy reference (skipped when gpm_native is not built)."""
import numpy as np
import pandas as pd
import pytest

from core import arena as A
from core.paper import CostModel
from tests.conftest import make_ohlcv

nat = pytest.importorskip("gpm_native")


@pytest.fixture(scope="module")
def setup():
    from core.organism import BiologicalOrganism
    feat = BiologicalOrganism().build_features(make_ohlcv(1500, 4))
    df, F = A.feature_matrix(feat)
    return df, F


@pytest.mark.parametrize("lev,mode,rc,use_cf", [(20.0, "margin", None, True), (10.0, "notional", 0.01, False),
                                                 (1.0, "margin", 0.01, True)])
def test_native_equals_numpy(setup, lev, mode, rc, use_cf):
    df, F = setup
    cm = CostModel(leverage=lev, energy_mode=mode)
    G = A.random_genomes(3000, np.random.default_rng(int(lev)), A.bounds_for(lev))
    cf = A.counterfactual_table(df, cm) if use_cf else None
    kw = dict(risk_cap=rc, kill_equity=3000.0 if rc else None, cf=cf)
    rn = A.simulate_population(G, F, df, 10, len(df), cm, backend="numpy", **kw)
    rr = A.simulate_population(G, F, df, 10, len(df), cm, backend="native", **kw)
    # float summation order (BLAS vs scalar loop) can in principle flip a threshold tie; demand ≥ 99.9 % exact genomes
    same = np.isclose(rn["equity"], rr["equity"], rtol=1e-9, atol=1e-6) & (rn["trades"] == rr["trades"])
    assert same.mean() >= 0.999, same.mean()
    for k in ("liquidated", "alive"):
        assert (rn[k] == rr[k]).mean() >= 0.999
    for k in ("maxdd", "energy", "credit", "declined", "win_rate"):
        assert np.isclose(rn[k], rr[k], rtol=1e-9, atol=1e-6)[same].all(), k


def test_env_switch_falls_back(monkeypatch, setup):
    df, F = setup
    monkeypatch.setenv("GPM_NATIVE", "0")
    G = A.random_genomes(50, np.random.default_rng(0))
    r = A.simulate_population(G, F, df, 10, 200, CostModel())
    assert len(r["equity"]) == 50
