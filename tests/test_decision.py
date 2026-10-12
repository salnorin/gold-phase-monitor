"""همه‌ی نمایش‌ها باید دقیقاً با شیء Decision یگانه یکی باشند."""
import numpy as np
import pandas as pd
import pytest

from core.decision import Decision, advice_key, live_signal, organism_decision, signal_card, status_key
from core.mind import Mind, MindConfig
from core.organism import BiologicalOrganism
from tests.conftest import make_ohlcv

KEYS = {"LONG": "adv_long", "SHORT": "adv_short"}


OPEN_NOW = pd.Timestamp("2026-10-13 15:01", tz="UTC")      # سه‌شنبه، CME باز


def _raw(n=900, seed=7, end=OPEN_NOW):
    r = make_ohlcv(n, seed)
    r.index = pd.date_range(end=end.floor("h") - pd.Timedelta(hours=1), periods=len(r), freq="h", tz="UTC")
    return r


def _awake_now(raw):
    return raw.index[-1] + pd.Timedelta(hours=1, minutes=1)


def test_decision_matches_mind_and_all_displays():
    raw = _raw()
    now = _awake_now(raw)
    dec, ctx = organism_decision(raw, MindConfig(), now)
    j = ctx["journal"]
    c = dec.confirmed
    assert isinstance(dec, Decision) and c is not None and not dec.provisional
    # همان شیء ذهن کامل
    expect = "WAIT" if c.asleep else j.action.iloc[-1]
    assert c.action == expect and c.reason == j.reason.iloc[-1]
    assert c.P_bull == pytest.approx(j.P_bull.iloc[-1]) and c.doubt == pytest.approx(j.doubt.iloc[-1])
    # نمایش‌ها
    assert advice_key(dec) == ("adv_wait" if dec.asleep else KEYS.get(dec.action, "adv_wait"))
    assert live_signal(dec) == c.action
    card = signal_card(dec)
    assert (card is None) == (c.action == "WAIT")
    if card:
        assert card["action"] == c.action and card["entry"] == c.entry
    assert dec.bias == {"LONG": 1, "SHORT": -1}.get(dec.action, 0)
    assert status_key(dec).startswith("st_")


def test_sweep_many_bars_advice_equals_decision():
    raw = _raw(1100, 3)
    seen = set()
    for k in range(700, 1100, 40):
        r = _raw(k, 3)
        dec, ctx = organism_decision(r, MindConfig(), _awake_now(r))
        seen.add(dec.action)
        assert advice_key(dec) == ("adv_wait" if dec.asleep else KEYS.get(dec.action, "adv_wait"))
        assert live_signal(dec) == dec.confirmed.action
        assert dec.action == ("WAIT" if dec.asleep else ctx["journal"].action.iloc[-1])


def test_asleep_forces_wait_everywhere():
    raw = _raw()
    sat = pd.Timestamp("2026-10-10 12:00", tz="UTC")       # شنبه: بازار CME بسته
    dec, _ = organism_decision(raw, MindConfig(), sat, wake_bar=sat - pd.Timedelta(minutes=1), wake_interval_h=1 / 60)
    assert dec.asleep and dec.action == "WAIT" and dec.market_state == "closed"
    assert advice_key(dec) == "adv_wait" and signal_card(dec) is None and live_signal(dec) == "WAIT" and dec.bias == 0


def test_provisional_uses_same_pipeline():
    raw = _raw()
    now = _awake_now(raw)
    step = pd.Timedelta(hours=1)
    start = raw.index[-1] + step
    mi = pd.date_range(start, periods=20, freq="min")
    px = float(raw.Close.iloc[-1])
    mins = pd.DataFrame(dict(Open=px, High=px + 1, Low=px - 1, Close=px + .5, Volume=5.0), index=mi)
    dec, _ = organism_decision(raw, MindConfig(), start + pd.Timedelta(minutes=21), minutes=mins)
    if not dec.asleep:
        assert dec.provisional and dec.timestamp == start and dec.bar_close == start + step
        ext = pd.concat([raw, pd.DataFrame(dict(Open=px, High=px + 1, Low=px - 1, Close=px + .5, Volume=100.0), index=[start])])
        jj = Mind(MindConfig()).run(BiologicalOrganism().build_features(ext))
        assert dec.action == jj.action.iloc[-1]
        assert advice_key(dec) == KEYS.get(dec.action, "adv_wait")


def test_app_has_no_independent_decision_logic():
    src = open("app.py", encoding="utf-8").read()
    live = src[src.index("def live_panel"):src.index("@st.fragment(run_every=timedelta(seconds=300)")]
    for bad in ("last.action", "last.evidence", "Mind(", "status_detail(", "np.sign("):
        assert bad not in live, bad
    assert "organism_decision_cached" in live and "live_action(dec, exec_thr)" in live and "signal=final_action" in live


def test_market_state_from_cme_calendar_not_gc_delay():
    raw = _raw()
    now = _awake_now(raw)
    dec, _ = organism_decision(raw, MindConfig(), now)                     # PAXG تازه، CME باز
    assert dec.market_state == "open" and not dec.asleep
    sat = pd.Timestamp("2026-10-10 12:00", tz="UTC")
    r2 = _raw(end=sat)
    d2, _ = organism_decision(r2, MindConfig(), sat)
    assert d2.market_state == "closed"
    src = open("app.py", encoding="utf-8").read()
    assert "organism_decision_cached(raw, cross, interval, leverage, manual, None" in src   # GC=F وضعیت را تعیین نمی‌کند


@pytest.mark.parametrize("forced", ["LONG", "SHORT", "WAIT"])
def test_forced_actions_flow_to_every_display(monkeypatch, forced):
    import core.decision as D

    class Forced(Mind):
        def run(self, feat, now=None):
            j = super().run(feat, now)
            j.iloc[-1, j.columns.get_loc("action")] = forced
            return j
    monkeypatch.setattr(D, "Mind", Forced)
    raw = _raw()
    dec, _ = organism_decision(raw, MindConfig(), _awake_now(raw))
    assert not dec.asleep and dec.action == forced
    assert advice_key(dec) == KEYS.get(forced, "adv_wait")
    assert live_signal(dec) == forced
    card = signal_card(dec)
    assert (card["action"] if card else "WAIT") == forced
    assert dec.bias == {"LONG": 1, "SHORT": -1}.get(forced, 0)
    if card:
        d = 1 if forced == "LONG" else -1
        assert d * (card["target"] - card["entry"]) > 0 and d * (card["entry"] - card["stop"]) > 0
