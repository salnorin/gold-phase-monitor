import json
import sqlite3

import numpy as np
import pandas as pd
import pytest

from core.config import PROFILES, momentum_params, profile_overrides
from core.momentum import momentum_journal, momentum_return
from core.recorder import log_tick


def _feat(closes):
    idx = pd.date_range("2026-10-01", periods=len(closes), freq="h", tz="UTC")
    return pd.DataFrame(dict(Close=closes), index=idx)


def test_profiles_default_unchanged():
    assert profile_overrides("normal") == {} and set(PROFILES) == {"normal", "strict", "active"}
    with pytest.raises(ValueError):
        profile_overrides("yolo")


def test_momentum_params_env(monkeypatch):
    monkeypatch.setenv("GOLD_MOM_BARS", "8"); monkeypatch.setenv("GOLD_MOM_PCT", "0.5")
    mp = momentum_params()
    assert (mp.bars, mp.pct) == (8, 0.5) and momentum_params(3, 0.1).bars == 3


def test_momentum_journal_signals():
    f = _feat([100, 100, 100, 100, 101, 101, 101, 101, 100, 99])
    j = momentum_journal(f, 4, 0.5)
    assert j["action"].iloc[4] == "LONG" and j["action"].iloc[9] == "SHORT" and j["action"].iloc[2] == "WAIT"
    assert set(["P_bull", "P_bear", "P_range", "doubt"]) <= set(j.columns)
    assert momentum_return(f, 4) == pytest.approx(99 / 101 - 1)


def test_log_tick_migrates_old_table(tmp_path):
    db = tmp_path / "x.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE ticks (time TEXT PRIMARY KEY, price REAL, decision TEXT, asleep INTEGER, equity REAL, change_pct REAL, open INTEGER)")
    con.commit(); con.close()
    s = dict(equity=600.0, change_pct=0.0, open=False)
    log_tick(db, "2026-10-12 02:00", 4200.0, "WAIT", False, s, dict(action="WAIT", items=[dict(k="whale", ok=False, v=2, thr=6)]))
    r = sqlite3.connect(db).execute("SELECT reason FROM ticks").fetchone()[0]
    assert json.loads(r)["items"][0]["k"] == "whale"


def test_dashboard_shows_why(tmp_path):
    pytest.importorskip("flask")
    from dashboard_lite.app import create_app
    db = tmp_path / "live_account_gold.sqlite"
    log_tick(db, "2026-10-12 02:00", 4200.0, "WAIT", False, dict(equity=600.0, change_pct=0.0, open=False),
             dict(action="WAIT", reason="احتیاط: ردپای نهنگ", profile="normal",
                  items=[dict(k="confidence", ok=False, v=0.03, thr=0.2)]))
    c = create_app(db).test_client()
    assert c.get("/api/state").get_json()["why"]["items"][0]["k"] == "confidence"
    html = c.get("/").get_data(as_text=True)
    assert 'id="why"' in html and "ردپای نهنگ" in html


def test_gate_breakdown_on_synthetic():
    from core.decision import organism_decision
    from core.explain import gate_breakdown
    from core.fx import Capital
    from core.mind import capital_mind_config
    rng = np.random.default_rng(0)
    idx = pd.date_range("2026-09-01", periods=400, freq="h", tz="America/New_York")
    c = 4000 + np.cumsum(rng.normal(0, 3, 400))
    raw = pd.DataFrame(dict(Open=c, High=c + 2, Low=c - 2, Close=c, Volume=rng.uniform(50, 150, 400)), index=idx)
    cap = Capital(eur=500, usd=580, risk_usd=5.8, stop_usd=406, rate=1.16, timestamp=None, source="t", warning=None)
    cfg = capital_mind_config(cap)
    dec, ctx = organism_decision(raw, cfg, idx[-1] + pd.Timedelta(hours=1))
    w = gate_breakdown(dec, ctx, cfg, raw)
    keys = {i["k"] for i in w["items"]}
    assert {"move_1h", "dominance", "doubt", "whale", "oxygen", "organ_score", "energy"} <= keys
    json.dumps(w)
