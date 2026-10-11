import core.fastpath as F


def test_fallback_when_daemon_down(monkeypatch):
    monkeypatch.setattr(F, "URL", "http://127.0.0.1:9")      # nothing listens
    import core.gold_price as G
    monkeypatch.setattr(G, "ticker", lambda: 4180.0)
    assert not F.available()
    assert F.paxg_price() == (4180.0, "python:coinbase/kraken")


def test_uses_fastpath_mid(monkeypatch):
    monkeypatch.setattr(F, "books", lambda: [
        {"venue": "kraken", "quote": "USD", "bid": 4179.0, "ask": 4181.0, "recv_ts": "2026-10-11T23:21:05Z"},
        {"venue": "coinbase", "quote": "USD", "bid": 4180.0, "ask": 4181.0, "recv_ts": "2026-10-11T23:20:00Z"},
        {"venue": "binance", "quote": "USDT", "bid": 4300.0, "ask": 4301.0, "recv_ts": "2026-10-11T23:21:09Z"}])
    p, src = F.paxg_price()
    assert p == 4180.0 and src == "fastpath:kraken"          # freshest USD venue; USDT ignored


def test_no_order_code_in_fastpath():
    import pathlib, re
    for f in pathlib.Path("fastpath-go").glob("*.go"):
        s = f.read_text(encoding="utf-8").lower()
        assert not re.search(r"(place_?order|/orders|new_?order|create_?order)", s), f
