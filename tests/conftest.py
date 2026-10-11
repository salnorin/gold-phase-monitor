import sys, pathlib
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def make_ohlcv(n=600, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n, freq="h", tz="America/New_York")
    close = 4000 * np.exp(np.cumsum(rng.normal(0, 0.003, n) * rng.choice([0.5, 1, 2.5], n)))
    op = np.r_[close[0], close[:-1]]
    hi = np.maximum(op, close) * (1 + rng.uniform(0, 0.003, n))
    lo = np.minimum(op, close) * (1 - rng.uniform(0, 0.003, n))
    vol = rng.integers(500, 5000, n).astype(float) * rng.choice([1, 1, 1, 3], n)
    return pd.DataFrame({"Open": op, "High": hi, "Low": lo, "Close": close, "Volume": vol}, index=idx)


@pytest.fixture
def ohlcv():
    return make_ohlcv()
