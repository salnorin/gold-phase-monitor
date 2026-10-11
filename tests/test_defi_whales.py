import numpy as np
import pandas as pd
import pytest

from core import defi as D
from core import whales as W
from core.crypto import CRYPTO_SIM, crypto_features, run_crypto_arena
from tests.conftest import make_ohlcv


def daily(n=60, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"tvl": 1e11 * np.exp(np.cumsum(rng.normal(0, .01, n))),
                         "stables": 3e11 * np.exp(np.cumsum(rng.normal(0, .002, n))),
                         "dex": 5e9 * rng.uniform(.5, 1.5, n)}, index=idx)


def test_parsers():
    assert D.parse_tvl([{"date": 1791676800, "tvl": 5.0}]).iloc[0] == 5.0
    assert D.parse_stables([{"date": "1791676800", "totalCirculating": {"peggedUSD": 7.0}}]).iloc[0] == 7.0
    assert D.parse_dex({"totalDataChart": [[1791676800, 3.0]]}).iloc[0] == 3.0


def test_defi_lagged_one_day_no_lookahead():
    d = daily()
    sig = D.defi_signals(d)
    assert sig.index[0] == d.index[0] + pd.Timedelta(days=1)
    feat = pd.DataFrame({"x": 0}, index=pd.date_range("2026-01-20", periods=24 * 10, freq="h", tz="UTC"))
    a = D.attach_defi(feat, D.defi_signals(d.iloc[:25]))
    b = D.attach_defi(feat, sig)
    cut = d.index[24] + pd.Timedelta(days=1)          # آخرین روز موجود در نسخه‌ی کوتاه
    m = feat.index < cut
    pd.testing.assert_frame_equal(a[m], b[m])
    assert b["DeFi_Oxygen"].between(-1, 1).all()


def test_candle_proxy_and_arkham_disabled(monkeypatch):
    c = make_ohlcv(300, 1)
    c.iloc[200, c.columns.get_loc("Volume")] *= 20
    ev = W.CandleWhaleProxy().events(c)
    assert ev.iloc[200] and ev.dtype == bool
    monkeypatch.delenv("ARKHAM_API_KEY", raising=False)
    assert not W.ArkhamWhaleFeed().available()
    assert [f.name for f in W.active_feeds()] == ["candle_proxy"]
    with pytest.raises(RuntimeError):
        W.ArkhamWhaleFeed().events(c, "BTC-USD")


def test_arkham_adapter_with_key(monkeypatch):
    monkeypatch.setenv("ARKHAM_API_KEY", "test")
    c = make_ohlcv(50, 2).tz_convert("UTC")

    class R:
        def raise_for_status(self): pass
        def json(self): return {"transfers": [{"blockTimestamp": str(c.index[10] + pd.Timedelta(minutes=5))}]}

    class S:
        def get(self, url, **kw):
            assert url.endswith("/transfers") and kw["headers"]["API-Key"] == "test"
            return R()
    ev = W.ArkhamWhaleFeed(session=S()).events(c, "BTC-USD")
    assert ev.iloc[10] and ev.sum() == 1
    out, used = W.combined_whale(c, "BTC-USD", [W.CandleWhaleProxy(), W.ArkhamWhaleFeed(session=S())])
    assert out.iloc[10] and used == ["candle_proxy", "arkham"]


def test_crypto_arena_rules():
    f = crypto_features(make_ohlcv(900, 3).tz_convert("UTC"), "BTC-USD", D.defi_signals(daily(80)))
    res, _ = run_crypto_arena(f, pop=200, generations=2, tiers=(20.0,))
    assert set(res) == {20.0}
    from core import arena as A
    from core.paper import CostModel
    df, F = A.feature_matrix(f)
    r = A.simulate_population(A.random_genomes(300, np.random.default_rng(0)), F, df, 50, len(df),
                              CostModel(leverage=20), **CRYPTO_SIM)
    assert (r["equity"][r["alive"]] > 7.0).all()
