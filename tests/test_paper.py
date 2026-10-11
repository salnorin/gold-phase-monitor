import pytest
from core.paper import CostModel, open_position, step_position


def test_20x_margin_and_liquidation_distance():
    cm = CostModel(leverage=20)
    p = open_position(cm, 1000, 1, 100, 0.0, 10, 20, margin_frac=1.0)
    assert abs(p.notional / p.margin - 20) < 1e-9          # مارجین ۵٪
    assert abs((p.entry - p.liq) / p.entry - 0.045) < 1e-9  # ۵٪ − ۰٫۵٪


def test_wick_liquidation_before_stop():
    cm = CostModel(leverage=20)
    p = open_position(cm, 1000, 1, 100, 0.0, 10, 20, margin_frac=1.0)  # استاپ ۹۰ < لیکوئید ۹۵.۵
    assert step_position(cm, p, 100, 100.2, 95.0, 99.9, 0.0, 48)
    assert p.reason == "liquidation" and p.pnl <= -p.margin


def test_stop_before_target_same_bar_and_costs():
    cm = CostModel(leverage=20)
    p = open_position(cm, 10_000, -1, 100, 1.0, 1.0, 2.0, risk_frac=0.01)
    assert p.entry < 100                                    # اسلیپیج علیه ما
    step_position(cm, p, 100, 101.5, 97.0, 100, 1.0, 48)
    assert p.reason == "stop" and p.pnl < -100              # کارمزد+اسلیپیج ضرر را بیشتر می‌کند


def test_gap_through_liquidation_short():
    cm = CostModel(leverage=20)
    p = open_position(cm, 1000, -1, 100, 0.0, 10, 5, margin_frac=0.5)
    step_position(cm, p, 106, 107, 105, 106, 0.0, 48)
    assert p.reason == "liquidation"


def test_funding_accrues_and_leverage_cap():
    cm = CostModel(leverage=20)
    p = open_position(cm, 1000, 1, 100, 0.0, 0.01, 100, risk_frac=0.01)  # استاپ خیلی نزدیک → سقف اهرم
    assert p.margin <= 1000 + 1e-9 and p.notional <= 20_000 + 1e-6
    step_position(cm, p, 100, 100.1, 99.995, 100, 0.0, 48)
    assert p.funding > 0
    with pytest.raises(ValueError):
        CostModel(leverage=50)


def test_weekend_swap_and_gap_through_stop():
    cm = CostModel(leverage=20)
    a = open_position(cm, 10_000, 1, 100, 0.0, 1.0, 5.0, risk_frac=0.01)
    b = open_position(cm, 10_000, 1, 100, 0.0, 1.0, 5.0, risk_frac=0.01)
    step_position(cm, a, 100, 100.2, 99.5, 100, 0.0, 48, hours=1)
    step_position(cm, b, 100, 100.2, 99.5, 100, 0.0, 48, hours=49)
    assert b.funding > 40 * a.funding
    # گپ دوشنبه از زیر استاپ: پر شدن در Open، نه در استاپ
    step_position(cm, b, 97.0, 97.5, 96.8, 97.2, 0.0, 48, hours=49)
    assert b.reason == "gap_stop" and b.exit <= 97.0
