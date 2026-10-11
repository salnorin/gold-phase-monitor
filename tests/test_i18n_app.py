import os
import pytest

from core.i18n import CREDIT, LANGS, S, t


def test_all_keys_have_three_languages():
    for k, v in S.items():
        assert len(v) == 3, k
    assert set(LANGS) == {"fa", "de", "en"}
    assert "سالار خانبابا (salnorin)" in CREDIT["fa"] and "© 2026" in CREDIT["de"] and "Grok Bot" in CREDIT["en"]
    assert t("tab_ledger", "fa") == "📓 دفتر تصمیم"


@pytest.mark.skipif(os.getenv("GPM_APPTEST") != "1", reason="network-heavy; set GPM_APPTEST=1")
def test_language_switch_changes_tabs():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file("../app.py", default_timeout=400).run()
    assert not at.exception
    fa = [tb.label for tb in at.tabs]
    assert "📓 دفتر تصمیم" in fa
    at.sidebar.radio[0].set_value("de").run()
    de = [tb.label for tb in at.tabs]
    assert "📓 Entscheidungsbuch" in de and de != fa
    at.sidebar.radio[0].set_value("en").run()
    assert "📓 Decision ledger" in [tb.label for tb in at.tabs]
    assert any(CREDIT["en"] in m.value for m in at.markdown)


def test_forming_bar_uses_only_closed_minutes():
    import numpy as np, pandas as pd, importlib
    idx = pd.date_range("2026-10-12 08:00", periods=3, freq="h", tz="UTC")
    raw = pd.DataFrame(dict(Open=1.0, High=2.0, Low=0.5, Close=1.5, Volume=10), index=idx)
    mi = pd.date_range("2026-10-12 11:00", periods=20, freq="min", tz="UTC")
    mins = pd.DataFrame(dict(Open=np.arange(20.0), High=np.arange(20.0) + 1, Low=np.arange(20.0) - 1,
                             Close=np.arange(20.0) + .5, Volume=1), index=mi)
    src = open("app.py", encoding="utf-8").read()
    ns = {"pd": pd}
    code = src[src.index("def forming_bar"):src.index("@st.cache_data(ttl=60, show_spinner=False)\ndef provisional_decision")]
    exec(code, ns)
    bar, start = ns["forming_bar"](raw, mins.iloc[:12], pd.Timedelta(hours=1))
    assert start == idx[-1] + pd.Timedelta(hours=1)
    assert bar.Close.iloc[0] == 11.5 and bar.High.iloc[0] == 12 and bar.Volume.iloc[0] == 12   # فقط ۱۲ دقیقه‌ی موجود
