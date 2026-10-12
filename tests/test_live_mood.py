import pandas as pd

from core.i18n import t
from core.live_account import live_feeling


def test_live_feeling_only_from_live_trades():
    assert live_feeling(pd.DataFrame(columns=["pnl"])) == "none"
    assert live_feeling(pd.DataFrame(dict(pnl=[-1.0, 2.0]))) == "happy"
    assert live_feeling(pd.DataFrame(dict(pnl=[2.0, -1.0]))) == "sad"


def test_live_panel_never_reads_replay_for_mood():
    src = open("app.py", encoding="utf-8").read()
    live = src[src.index("def live_panel"):src.index("@st.fragment(run_every=timedelta(seconds=300)")]
    assert "run_mind(" not in live and "feeling = live_feeling(lt)" in live and 'T("mood_none")' in live


def test_mood_none_translations():
    assert t("mood_none", "fa") == "هنوز معامله‌ای نشده" and t("mood_none", "de") and t("mood_none", "en") == "no trade yet"
