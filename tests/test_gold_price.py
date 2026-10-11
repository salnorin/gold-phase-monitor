import pandas as pd
from core import gold_price


def test_single_source_is_paxg_and_kraken_fallback(monkeypatch):
    import core.crypto as C
    def boom(*a, **k): raise RuntimeError("coinbase down")
    monkeypatch.setattr(C, "fetch_candles", boom)
    idx = pd.date_range("2026-10-12", periods=3, freq="h", tz="UTC")
    fake = pd.DataFrame(dict(Open=1.0, High=1.0, Low=1.0, Close=1.0, Volume=1.0), index=idx)
    monkeypatch.setattr(gold_price, "_kraken_candles", lambda iv, n: fake.copy())
    d = gold_price.candles("1h", 10)
    assert d.attrs["source"].startswith("Kraken") and str(d.index.tz) == "America/New_York"
    assert gold_price.PRODUCT == "PAXG-USD" and gold_price.REFERENCE_FUTURES == "GC=F"


def test_app_uses_gold_price_module_for_signals():
    src = open("app.py", encoding="utf-8").read()
    assert "gold_price.candles(interval" in src and 'load("GC=F", interval)' not in src
