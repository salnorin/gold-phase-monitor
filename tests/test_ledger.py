import numpy as np
import pandas as pd
import pytest

from core.ledger import DecisionLedger, ExitRules, resolve, summarize, TIER_RULES
from core.paper import CostModel, open_position, step_position
from core import arena as A


def bars(close, spread=0.5):
    c = np.asarray(close, float)
    o = np.r_[c[0], c[:-1]]
    return o, np.maximum(o, c) + spread, np.minimum(o, c) - spread, c, np.full(len(c), 2.0)


def test_energy_default_020_per_side_margin_mode():
    cm = CostModel(leverage=20)
    assert cm.energy_pct == pytest.approx(0.20) and cm.energy_mode == "margin"
    p = open_position(cm, 1000, 1, 100.0, 1.0, 1.0, 50.0, margin_frac=0.5)
    assert p.energy == pytest.approx(p.margin * 0.002)
    step_position(cm, p, 100, 100.2, 99.9, 100.1, 1.0, max_hold=1)
    assert p.energy == pytest.approx(2 * p.margin * 0.002, rel=1e-3)     # ~0.40% round trip
    n = CostModel(leverage=20, energy_mode="notional")
    assert n.energy(10, 200) == pytest.approx(0.4)
    with pytest.raises(ValueError):
        CostModel(energy_mode="x")


def test_no_trade_costs_nothing_and_trade_pays_energy():
    o, h, l, c, atr = bars([100, 100, 100, 100, 100])
    cm = CostModel(leverage=20)
    assert resolve(o, h, l, c, atr, 0, 0, ExitRules(), cm)[2:] == (0.0, 0.0, 0.0)
    j, why, pct, juice, energy = resolve(o, h, l, c, atr, 0, 1, ExitRules(3, 1.5, 2), cm)
    assert why == "TIMEOUT" and energy == pytest.approx(0.004) and juice < 0


def test_counterfactual_tp_sl_and_liquidation():
    o, h, l, c, atr = bars([100, 100, 104, 104, 104])
    cm = CostModel(leverage=20)
    assert resolve(o, h, l, c, atr, 0, 1, ExitRules(1.0, 1.0, 10), cm)[1] == "TP"
    assert resolve(o, h, l, c, atr, 0, -1, ExitRules(1.0, 1.0, 10), cm)[1] == "SL"
    o, h, l, c, atr = bars([100, 100, 90, 90])
    assert resolve(o, h, l, c, atr, 0, 1, ExitRules(1.0, 50.0, 10), cm)[1:4:2] == ("LIQ", -1.0 - 0.004)


def test_ledger_reveals_only_resolved_past():
    o, h, l, c, atr = bars(np.linspace(100, 110, 30))
    idx = pd.date_range("2026-01-05", periods=30, freq="h", tz="UTC")
    L, cm, rules = DecisionLedger(), CostModel(leverage=20), ExitRules(1, 1, 5)
    seen = []
    for i in range(30):
        L.log(i, idx[i], "NO_TRADE", 0.3, {"doubt": 0.1}, "organism", 20, "1h", (o, h, l, c, atr, idx), rules, cm, suggested=1)
        for r in L.reveal(i):
            assert r["resolved_index"] <= i and r["index"] <= i
            seen.append(r)
    assert len(L.rows) == 90 and all(r["option"] in ("LONG", "SHORT", "NO_TRADE") for r in L.rows)
    assert sum(r["chosen"] for r in L.rows) == 30
    df = L.frame()
    s = summarize(df)
    assert "organism" in s.index and s.loc["organism", "no_trade"] == 30
    assert s.loc["organism", "energy_spent"] == 0.0     # همیشه NO_TRADE انتخاب شد


def test_ledger_persist_sqlite_and_parquet(tmp_path):
    o, h, l, c, atr = bars(np.linspace(100, 101, 10))
    idx = pd.date_range("2026-01-05", periods=10, freq="h", tz="UTC")
    L = DecisionLedger()
    for i in range(10):
        L.log(i, idx[i], "LONG", 0.5, {}, "trend", 20, "1h", (o, h, l, c, atr, idx), ExitRules(1, 1, 3), CostModel())
    assert len(DecisionLedger.load(L.save(tmp_path / "l.sqlite"))) == 30
    try:
        assert len(DecisionLedger.load(L.save(tmp_path / "l.parquet"))) == 30
    except ImportError:
        pass


def test_20x_tier_bounds_tight():
    B = A.bounds_for(20.0)
    assert B["hold"][1] <= 12 and B["stop"][1] <= 1.0 and B["target"][1] <= 2.0
    g = A.random_genomes(500, np.random.default_rng(0), B)
    assert g[:, 8].max() <= 12 and g[:, 7].max() <= 1.0
    kids = A.mutate(g, 500, np.random.default_rng(1), scale=1.0, B=B)
    assert kids[:, 8].max() <= 12 and kids[:, 6].max() <= 2.0
    assert TIER_RULES[20.0].max_hold <= 12


def test_arena_energy_and_ledger_credit_past_only():
    n = 120
    rng = np.random.default_rng(0)
    c = 100 + np.cumsum(rng.normal(0, 0.5, n))
    o, h, l, c, atr = bars(c)
    df = pd.DataFrame(dict(Open=o, High=h, Low=l, Close=c, ATR=atr),
                      index=pd.date_range("2026-01-05", periods=n, freq="h", tz="UTC"))
    F = rng.normal(0, 1, (n, 5))
    cm = CostModel(leverage=20)
    G = A.random_genomes(200, rng, A.bounds_for(20))
    cf = A.counterfactual_table(df, cm)
    r = A.simulate_population(G, F, df, 1, 60, cm, cf=cf)
    assert (r["energy"][r["trades"] > 0] > 0).all() and (r["energy"][r["trades"] == 0] == 0).all()
    # بریدن آینده‌ی بعد از پنجره نتیجه را عوض نمی‌کند
    r2 = A.simulate_population(G, F, df.iloc[:60], 1, 60, cm, cf=A.counterfactual_table(df.iloc[:60], cm))
    assert np.allclose(r["credit"], r2["credit"]) and np.allclose(r["equity"], r2["equity"])
    zero = CostModel(leverage=20, energy_pct=0.0)
    r0 = A.simulate_population(G, F, df, 1, 60, zero)
    assert r0["equity"].sum() >= r["equity"].sum()


def test_mind_writes_ledger_no_lookahead():
    from core.mind import Mind
    from tests.test_mind import feats
    f = feats(900, 3)
    m = Mind(); j = m.run(f)
    L = m.ledger.frame()
    assert len(L) == 3 * len(j) and L.groupby("index").chosen.sum().eq(1).all()
    done = L.dropna(subset=["resolved_index"])
    assert (done.resolved_index >= done["index"]).all()
    assert (L[L.option == "NO_TRADE"].energy.fillna(0) == 0).all()
    assert m.energy_spent >= 0
    # پیشوند داده همان تصمیم‌ها را می‌دهد (پشیمانی دروازه فقط از گذشته)
    m2 = Mind(); j2 = m2.run(f.iloc[:600])
    assert (j2.action.values == j.action.values[:600]).all()
