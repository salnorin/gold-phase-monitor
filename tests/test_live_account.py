import pandas as pd

from core.live_account import LivePaperAccount
from core.mind import Mind, MindConfig
from core.organism import BiologicalOrganism
from tests.conftest import make_ohlcv


def setup(n=900):
    f = BiologicalOrganism().build_features(make_ohlcv(n, 8))
    cfg = MindConfig(whale_volume=99, whale_range_atr=99, low_oxygen=0.0, start_equity=600, capital_cap=600, kill_equity=420)
    return f, cfg, Mind(cfg).run(f)


def test_live_account_starts_now_and_ignores_history(tmp_path):
    f, cfg, j = setup()
    acc = LivePaperAccount("gold", 600, cfg, path=tmp_path / "a.json", now=f.index[-1])
    assert acc.update(f, j, awake=True) == 0 and acc.equity == 600 and not acc.state["trades"]   # تاریخچه نادیده


def test_live_account_persists_and_only_trades_when_awake(tmp_path):
    f, cfg, j = setup()
    k = 450
    acc = LivePaperAccount("gold", 600, cfg, path=tmp_path / "a.json", now=f.index[k])
    # خواب: هیچ ورودی
    for i in range(k + 1, len(f)):
        acc.update(f.iloc[:i + 1], j.iloc[:i + 1], awake=False)
    assert acc.state["position"] is None and not acc.state["trades"] and acc.equity == 600
    # بیدار از ابتدا
    p = tmp_path / "b.json"
    acc2 = LivePaperAccount("gold", 600, cfg, path=p, now=f.index[k])
    for i in range(k + 1, len(f)):
        acc2.update(f.iloc[:i + 1], j.iloc[:i + 1], awake=True)
    again = LivePaperAccount("gold", path=p, cfg=cfg)                     # از دیسک
    assert again.state["last_bar"] == str(f.index[-1]) and again.equity == acc2.equity
    signals = (j.iloc[k + 1:-1]["action"] != "WAIT").sum()
    assert signals == 0 or acc2.state["trades"] or acc2.state["position"] is not None


def test_manual_preset_fixed_risk_and_1to1(tmp_path):
    import numpy as np, pandas as pd
    from core.live_account import LivePaperAccount
    from core.mind import capital_mind_config
    idx = pd.date_range("2026-10-12 08:00", periods=4, freq="h", tz="UTC")
    feat = pd.DataFrame(dict(Open=100.0, High=100.2, Low=99.8, Close=100.0, ATR=1.0, Market_Open=True), index=idx)
    j = pd.DataFrame(dict(action=["WAIT", "LONG", "WAIT", "WAIT"]), index=idx)
    cfg = capital_mind_config(None, leverage=20.0, bar_hours=1.0)
    acc = LivePaperAccount("gold", 600.0, cfg, path=tmp_path / "m.json", now=idx[0] - pd.Timedelta(hours=1),
                           fixed_risk_usd=2.32, rr=1.0)
    acc.update(feat.iloc[:2], j.iloc[:2], True)
    acc.update(feat.iloc[:3], j.iloc[:3], True)
    p = acc.state["position"]
    assert p and acc.state["last_event"]["kind"] == "opened"
    assert abs(p["qty"] * (p["entry"] - p["stop"]) - 2.32) < 1e-6           # ریسک تا استاپ = ۲ € (به دلار)
    assert abs((p["target"] - p["entry"]) - (p["entry"] - p["stop"])) < 1e-9  # ۱:۱
