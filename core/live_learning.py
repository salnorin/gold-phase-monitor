# core/live_learning.py
"""
یادگیری از معاملات کاغذی *زنده*ی بسته‌شده (فقط کاغذی، فقط نتایج گذشته).
وضعیت در data dir: learning_gold.json — بعد از ری‌استارت ادامه پیدا می‌کند.
  - boldness (جسارت): ضریب base_risk، در [0.5, 1.5]، هر معامله حداکثر ±step؛ ریسک نهایی همیشه ≤ ۱٪ (max_risk).
  - organ_mult: ضریب وزن اولیه‌ی هر ارگان در [0.7, 1.3]، هر معامله حداکثر ±step (اعتبار = R در جهت رأی ارگان).
  - strategy: EMA از R معاملات زنده‌ی هر استراتژی → امتیاز اولیه‌ی استخر استراتژی ذهن.
  - juice: آخرین سرمایه‌ی کاغذی زنده.
رأی ارگان‌ها/استراتژی در لحظه‌ی سیگنال در هر دور ذخیره می‌شود (note_signal) و فقط وقتی معامله *بسته شد* استفاده می‌شود.
GOLD_LEARN=0 → خاموش (ارگانیسم دقیقاً پیش‌فرض).
"""
import json
import os
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

BOLD_MIN, BOLD_MAX = 0.5, 1.5
MULT_MIN, MULT_MAX = 0.7, 1.3
STEP = 0.05          # سقف تغییر در هر معامله
MAX_SIGNALS = 300


def enabled():
    return os.getenv("GOLD_LEARN", "1") != "0"


class LiveLearner:
    def __init__(self, path):
        self.path = Path(path)
        self.state = dict(boldness=1.0, organ_mult={}, strategy={}, seen=[], signals={}, history=[], juice=None)
        if self.path.exists():
            self.state.update(json.loads(self.path.read_text(encoding="utf-8")))

    @classmethod
    def for_account(cls, acc_path):
        return cls(Path(acc_path).with_name("learning_" + Path(acc_path).stem.replace("live_account_", "") + ".json"))

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        tmp.replace(self.path)

    # ---- ثبت رأی‌ها در لحظه‌ی سیگنال (کندل بسته‌ی آخر) ----
    def note_signal(self, bar_time, action, votes, strategy):
        if action not in ("LONG", "SHORT"):
            return
        sig = self.state["signals"]
        sig[str(pd.Timestamp(bar_time))] = dict(action=action, votes={k: float(v) for k, v in (votes or {}).items()},
                                                strategy=strategy)
        for k in sorted(sig)[:-MAX_SIGNALS]:
            del sig[k]

    def _signal_for(self, entry_time):
        """سیگنال کندل قبل از ورود (ورود در Open کندل بعد از سیگنال)."""
        et = pd.Timestamp(entry_time)
        best = None
        for k, v in self.state["signals"].items():
            t = pd.Timestamp(k)
            if t < et and (best is None or t > best[0]):
                best = (t, v)
        return best[1] if best and et - best[0] <= pd.Timedelta(hours=6) else None

    # ---- یادگیری فقط از معاملات بسته‌شده ----
    def learn(self, trades, equity=None):
        seen, changes = set(self.state["seen"]), []
        for t in trades:
            key = f"{t['entry_time']}|{t['direction']}"
            if key in seen or t.get("exit_time") in (None, "") or t.get("R") is None:
                continue
            seen.add(key)
            r = float(np.clip(float(t["R"]), -3, 3))
            d = 1 if t["direction"] == "LONG" else -1
            adj = dict(trade=key, R=round(r, 2))
            b0 = self.state["boldness"]
            self.state["boldness"] = float(np.clip(b0 + np.clip(0.02 * r, -STEP, STEP), BOLD_MIN, BOLD_MAX))
            adj["boldness"] = round(self.state["boldness"] - b0, 4)
            sig = self._signal_for(t["entry_time"])
            if sig:
                om = self.state["organ_mult"]
                for organ, v in sig["votes"].items():
                    if abs(v) < 1e-9:
                        continue
                    credit = r if np.sign(v) == d else -r
                    m0 = om.get(organ, 1.0)
                    om[organ] = float(np.clip(m0 + np.clip(0.02 * credit, -STEP, STEP), MULT_MIN, MULT_MAX))
                    adj[organ] = round(om[organ] - m0, 4)
                s = sig.get("strategy") or "organism"
                st = self.state["strategy"].setdefault(s, dict(score=0.0, n=0))
                st["n"] += 1
                st["score"] = float(0.8 * st["score"] + 0.2 * r)
            changes.append(adj)
        self.state["seen"] = sorted(seen)
        if equity is not None:
            self.state["juice"] = float(equity)
        self.state["history"] = (self.state["history"] + changes)[-20:]
        return changes

    # ---- اعمال روی پیکربندی ذهن (قبل از تصمیم) ----
    def apply(self, cfg):
        oc = cfg.organism
        w = {k: float(np.clip(v * self.state["organ_mult"].get(k, 1.0), oc.weight_min, oc.weight_max)) if v else v
             for k, v in oc.initial_weights.items()}
        base = float(min(cfg.max_risk, max(cfg.min_risk, cfg.base_risk * self.state["boldness"])))
        return replace(cfg, organism=replace(oc, initial_weights=w), base_risk=base)

    def seed_mind(self, mind):
        for s, v in self.state["strategy"].items():
            if s in mind.strat:
                mind.strat[s]["score"] = float(v["score"])

    def summary(self):
        return dict(boldness=round(self.state["boldness"], 3),
                    organ_mult={k: round(v, 3) for k, v in self.state["organ_mult"].items()},
                    strategy=self.state["strategy"], learned=len(self.state["seen"]), juice=self.state["juice"],
                    last=self.state["history"][-5:])
