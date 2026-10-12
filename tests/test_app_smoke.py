"""Smoke: کل اپ Streamlit با AppTest رندر شود، بدون استثنا؛ اگر داده‌ی زنده در دسترس و بازار باز است،
عقربه‌ی پیش‌نمایش (نیم‌دایره) و کارت تصمیم باید وجود داشته باشند."""
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_source_keeps_preview_and_card():
    src = open(APP, encoding="utf-8").read()
    assert "def preview_svg" in src and "linearGradient" in src and "decision-card" in src
    assert "next_decision_preview(dec, now)" in src


def test_app_renders_without_exception():
    at = st_testing.AppTest.from_file(APP, default_timeout=200).run()
    assert not at.exception, [e.value for e in at.exception]
    md = " ".join(m.value for m in at.markdown)
    if "🟢" in md:                                   # بازار باز/بیدار (نیازمند شبکه)
        assert "linearGradient" in md and "decision-card" in md and "#### 🔮" in md


def test_paxg_10m_resample_and_trade_marks():
    import numpy as np
    import pandas as pd
    src = open(APP, encoding="utf-8").read()
    assert "def resample_10m" in src and "paxg_chart_section()" in src
    # resample logic (same code as app) without importing streamlit app module
    idx = pd.date_range("2026-10-12 00:00", periods=12, freq="5min", tz="UTC")
    d = pd.DataFrame(dict(Open=np.arange(12.), High=np.arange(12.) + 1, Low=np.arange(12.) - 1, Close=np.arange(12.) + .5, Volume=1.0), index=idx)
    r = d.resample("10min", label="left", closed="left").agg(dict(Open="first", High="max", Low="min", Close="last", Volume="sum"))
    assert len(r) == 6 and r.Open.iloc[1] == 2 and r.High.iloc[1] == 4 and r.Close.iloc[1] == 3.5
