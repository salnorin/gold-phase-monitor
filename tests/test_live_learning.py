import json

import pandas as pd
import pytest

from core.live_learning import BOLD_MAX, MULT_MAX, STEP, LiveLearner
from core.mind import Mind, MindConfig


def _t(entry, r, d="LONG"):
    return dict(entry_time=entry, exit_time="2026-10-12 12:00", direction=d, R=r, pnl=r)


def test_learns_only_closed_once_and_persists(tmp_path):
    L = LiveLearner(tmp_path / "learning_gold.json")
    L.note_signal("2026-10-12 09:00", "LONG", {"respiration": 1.0, "optical": -0.5}, "organism")
    ch = L.learn([_t("2026-10-12 10:00", 2.0), dict(entry_time="x", exit_time=None, direction="LONG", R=None)], 650)
    assert len(ch) == 1 and L.state["boldness"] > 1 and L.state["organ_mult"]["respiration"] > 1
    assert L.state["organ_mult"]["optical"] < 1                     # opposed a winner
    assert L.learn([_t("2026-10-12 10:00", 2.0)]) == []             # same trade never twice
    L.save()
    L2 = LiveLearner(tmp_path / "learning_gold.json")               # survives restart
    assert L2.state["boldness"] == L.state["boldness"] and L2.summary()["learned"] == 1
    assert L2.state["strategy"]["organism"]["n"] == 1


def test_adaptation_capped(tmp_path):
    L = LiveLearner(tmp_path / "l.json")
    for i in range(200):
        L.note_signal(f"2026-01-01 {i % 24:02d}:00" if False else str(pd.Timestamp("2026-01-01") + pd.Timedelta(hours=2 * i)),
                      "LONG", {"respiration": 1.0}, "organism")
        b0 = L.state["boldness"]
        L.learn([_t(str(pd.Timestamp("2026-01-01") + pd.Timedelta(hours=2 * i + 1)), 100.0)])
        assert L.state["boldness"] - b0 <= STEP + 1e-9
    assert L.state["boldness"] == BOLD_MAX and L.state["organ_mult"]["respiration"] == MULT_MAX


def test_apply_keeps_risk_cap_and_seeds_strategy(tmp_path):
    L = LiveLearner(tmp_path / "l.json")
    L.state.update(boldness=1.5, organ_mult={"respiration": 1.3}, strategy={"trend": dict(score=0.4, n=3)})
    cfg = MindConfig()
    c2 = L.apply(cfg)
    assert c2.base_risk <= cfg.max_risk and c2.base_risk > cfg.base_risk
    assert c2.organism.initial_weights["respiration"] == pytest.approx(1.3)
    assert c2.organism.initial_weights["cross"] == 0.0 and cfg.organism.initial_weights["respiration"] == 1.0
    m = Mind(c2); L.seed_mind(m)
    assert m.strat["trend"]["score"] == 0.4


def test_default_learner_is_identity(tmp_path):
    cfg = MindConfig()
    c2 = LiveLearner(tmp_path / "none.json").apply(cfg)
    assert c2.base_risk == cfg.base_risk and c2.organism.initial_weights == cfg.organism.initial_weights


def test_signal_lookup_ignores_future(tmp_path):
    L = LiveLearner(tmp_path / "l.json")
    L.note_signal("2026-10-12 11:00", "LONG", {"respiration": 1.0}, "organism")   # after entry → not used
    L.learn([_t("2026-10-12 10:00", 1.0)])
    assert L.state["organ_mult"] == {}
