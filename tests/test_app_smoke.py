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



def test_movement_chart_wired():
    src = open(APP, encoding="utf-8").read()
    assert "def movement_figure" in src and "paxg_chart_section()" in src and "Candlestick" not in src
