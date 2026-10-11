import numpy as np
import pandas as pd

from core import arena as A
from core.organism import BiologicalOrganism
from core.paper import CostModel
from tests.conftest import make_ohlcv


def setup(n=900, seed=21):
    df, F = A.feature_matrix(BiologicalOrganism().build_features(make_ohlcv(n, seed)))
    return df, F


def test_genomes_bounded():
    rng = np.random.default_rng(0)
    G = A.mutate(A.random_genomes(500, rng), 2000, rng, scale=1.0)
    assert (G[:, :5] >= -1).all() and (G[:, :5] <= 1).all()
    assert (G[:, 9] >= 0.02).all() and (G[:, 9] <= 1).all() and (G[:, 8] >= 4).all()


def test_20x_all_in_gets_liquidated_on_crash():
    idx = pd.date_range("2026-01-01", periods=6, freq="h", tz="America/New_York")
    df = pd.DataFrame({"Open": [100, 100, 100, 100, 100, 100], "High": [100.1] * 6,
                       "Low": [99.9, 99.9, 99.9, 94.0, 99.9, 99.9], "Close": [100] * 6, "ATR": [0.5] * 6}, index=idx)
    F = np.tile([1, 0, 0, 0, 0], (6, 1)).astype(float)
    g = np.array([[1, 0, 0, 0, 0, 0.1, 4.0, 3.0, 96, 1.0]])  # لانگ، استاپ دور (1.5$) ولی مارجین کامل
    r20 = A.simulate_population(g, F, df, 1, 6, CostModel(leverage=20))
    r1 = A.simulate_population(g, F, df, 1, 6, CostModel(leverage=1))
    assert r20["liquidated"][0] and not r20["alive"][0]
    assert not r1["liquidated"][0]


def test_evolution_uses_only_in_sample():
    df, F = setup(1200)
    is_end = 800
    cm = CostModel(leverage=20)
    G1, _, h1 = A.evolve(F, df, is_end, cm, pop=200, generations=3, seed=3, warmup=100)
    F2 = F.copy(); F2[is_end:] = np.random.default_rng(9).normal(size=F2[is_end:].shape)
    df2 = df.copy(); df2.iloc[is_end:, df2.columns.get_loc("Close")] *= 1.3
    G2, _, h2 = A.evolve(F2, df2, is_end, cm, pop=200, generations=3, seed=3, warmup=100)
    np.testing.assert_array_equal(G1, G2)
    assert len(h1) == 3 and h1["survival"].between(0, 1).all()


def test_deflation_runs():
    df, F = setup(1000)
    cm = CostModel(leverage=10)
    G, final, _ = A.evolve(F, df, 700, cm, pop=300, generations=2, seed=1, warmup=100)
    d, champs = A.deflation_test(G, final, F, df, 700, 1000, cm, k=10, n_random=200)
    assert 0 <= d["champ_pctile_vs_random"] <= 100 and d["champions"] <= 10
