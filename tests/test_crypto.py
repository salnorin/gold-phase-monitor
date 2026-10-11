import json
import sys
import types
import pandas as pd
import pytest

from core import crypto as C
from core.mind import Mind
from core.fx import FxQuote, paper_capital

CAP = paper_capital(FxQuote(1.25, pd.Timestamp('2026-10-10', tz='UTC'), 'mock'))   # 540.16 € → 675.20 $
from tests.conftest import make_ohlcv


def test_24_7_always_open_and_limits():
    raw = make_ohlcv(1200, seed=4)
    m, j = C.run_crypto_mind(raw, cfg=C.crypto_config(CAP))
    feat = C.BiologicalOrganism().build_features(raw, market="24/7")
    assert feat["Market_Open"].all()
    cfg = C.crypto_config(CAP)
    assert cfg.start_equity == 675.2 and cfg.max_risk == 0.01 and cfg.kill_equity == 472.64
    for p in m.trades:
        assert p.qty * abs(p.entry - p.stop) <= 6.752 + 1e-9 and p.notional <= 675.2 + 1e-6


def test_kill_switch_at_7():
    from dataclasses import replace
    m = Mind(C.crypto_config(CAP))
    m.equity = 472.0
    j = m.run(C.BiologicalOrganism().build_features(make_ohlcv(800, seed=2), market="24/7"))
    assert (j["action"] == "WAIT").all() and not m.trades and "توقف خودکار" in j["reason"].iloc[-1]


def test_readonly_wrapper_blocks_orders(tmp_path, monkeypatch):
    class Fake:
        def __init__(self, **kw): pass
        def get_accounts(self, **kw): return "ok"
        def market_order_buy(self, **kw): raise AssertionError("must not be reachable")
    mod = types.ModuleType("coinbase.rest"); mod.RESTClient = Fake
    monkeypatch.setitem(sys.modules, "coinbase", types.ModuleType("coinbase"))
    monkeypatch.setitem(sys.modules, "coinbase.rest", mod)
    p = tmp_path / "k.json"; p.write_text(json.dumps({"name": "x", "privateKey": "y"}))
    ro = C.ReadOnlyCoinbase(str(p))
    assert ro.get_accounts() == "ok"
    for bad in ("market_order_buy", "create_order", "withdraw", "send"):
        with pytest.raises(AttributeError):
            getattr(ro, bad)


def test_no_order_code_in_repo():
    import pathlib, re
    root = pathlib.Path(__file__).resolve().parents[1]
    pat = re.compile(r"\.(create_order|market_order|limit_order|place_order|withdraw|send_money)\w*\(")
    for f in list(root.glob("core/*.py")) + [root / "app.py"]:
        assert not pat.search(f.read_text()), f


def test_secret_not_tracked():
    import subprocess, pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    files = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True).stdout
    assert "coinbase_cdp" not in files and ".secrets" not in files
