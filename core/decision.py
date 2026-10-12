# core/decision.py
"""
خط لوله‌ی تصمیم یگانه (single source of truth) — فقط کاغذی.

organism_decision(...) → Decision
  یک بار در هر تازه‌سازی محاسبه می‌شود (ذهن کامل: همه‌ی ارگان‌ها، ریسک، نهنگ، اکسیژن، دروازه‌ها) روی قیمت PAXG-USD.
  همه‌ی نمایش‌ها و مصرف‌کننده‌ها فقط همین شیء را می‌خوانند: کارت سیگنال، پیش‌نمایش/عقربه، «با کمک رسول واحد»،
  حالت/خم شدن خرس، متن وضعیت، آزمون دستی ۲ یورویی، حساب کاغذی زنده و دفتر تصمیم.

  - Decision.confirmed: تصمیم کندل بسته‌شده‌ی آخر (مبنای کارت سیگنال و حساب کاغذی).
  - Decision خودش: تصمیم «جاری» — اگر کندل در حال شکل‌گیری از کندل‌های ۱ دقیقه‌ای بسته‌شده موجود باشد، موقت (provisional)؛
    وگرنه همان confirmed.
  - اگر ارگانیسم خواب باشد (بازار CME بسته / داده‌ی کهنه) action همیشه WAIT است.
بدون نگاه به آینده: فقط کندل‌های بسته‌شده (و دقیقه‌های بسته‌شده برای کندل موقت).
"""
from dataclasses import dataclass, field, replace
from typing import Optional

import numpy as np
import pandas as pd

from core.market_hours import status_detail
from core.mind import Mind
from core.organism import BiologicalOrganism


@dataclass
class Decision:
    action: str                      # LONG | SHORT | WAIT
    provisional: bool
    confidence: float
    entry: float
    stop: float
    target: float
    reason: str
    organ_votes: dict
    regime: str
    P_bull: float
    P_bear: float
    P_range: float
    doubt: float
    dominance_thr: float
    max_doubt: float
    risk_state: str                  # دلیل حد سخت (اگر فعال)؛ "" یعنی آزاد
    whale: bool
    oxygen: float
    vol_ratio: float
    asleep: bool
    market_state: str                # open | closed | awaiting | stale
    market_reason: str
    timestamp: pd.Timestamp          # شروع کندلی که تصمیم روی آن است
    bar_close: pd.Timestamp          # زمان بسته شدن آن کندل
    price: float
    interval_h: float
    confirmed: Optional["Decision"] = field(default=None, repr=False)

    @property
    def bias(self):
        return {"LONG": 1, "SHORT": -1}.get(self.action, 0)

    @property
    def lean(self):
        """خم شدن پیوسته برای عقربه/خرس: فقط وقتی بیدار است."""
        return 0.0 if self.asleep else float(np.clip(self.P_bull - self.P_bear, -1, 1))


HARD_MARKERS = ("خواب", "توقف خودکار", "استراحت", "نوسان", "نهنگ", "اکسیژن", "بسته", "کهنه")


def _from_row(r, m, feat, cfg, market, provisional, rr=None):
    oc = cfg.organism
    atr = float(feat["ATR"].iloc[-1])
    d = {"LONG": 1, "SHORT": -1}.get(r.action, 0)
    entry = float(r.close)
    stop_d = atr * oc.stop_atr_mult
    tgt_d = stop_d * rr if rr else atr * oc.target_atr_mult
    step = pd.Timedelta(minutes=int(round(cfg.bar_hours * 60)))
    state, why = market
    asleep = state != "open"
    hard = next((k for k in HARD_MARKERS if k in str(r.reason)), "") and r.action == "WAIT"
    return Decision(
        action="WAIT" if asleep else r.action, provisional=provisional,
        confidence=float(max(r.P_bull, r.P_bear, r.P_range) * (1 - r.doubt)),
        entry=entry, stop=entry - d * stop_d if d else np.nan, target=entry + d * tgt_d if d else np.nan,
        reason=str(r.reason), organ_votes=dict(m.brain.blood.votes), regime=str(r.regime),
        P_bull=float(r.P_bull), P_bear=float(r.P_bear), P_range=float(r.P_range), doubt=float(r.doubt),
        dominance_thr=cfg.dominance, max_doubt=cfg.max_doubt, risk_state=str(r.reason) if hard else "",
        whale=bool(r.whale), oxygen=float(r.oxygen), vol_ratio=float(r.vol_ratio), asleep=asleep,
        market_state=state, market_reason=why, timestamp=r.name, bar_close=r.name + step, price=entry,
        interval_h=cfg.bar_hours)


def forming_bar(raw, minutes, step):
    """کندل در حال شکل‌گیری از کندل‌های ۱ دقیقه‌ای *بسته‌شده* پس از آخرین کندل بسته‌ی بازه."""
    if minutes is None or not len(minutes):
        return None, None
    start = raw.index[-1] + step
    m = minutes[(minutes.index >= start) & (minutes.index < start + step)]
    if m.empty:
        return None, start
    bar = pd.DataFrame(dict(Open=m.Open.iloc[0], High=m.High.max(), Low=m.Low.min(), Close=m.Close.iloc[-1],
                            Volume=m.Volume.sum()), index=[start])
    return bar, start


def _features(raw, cross):
    feat = BiologicalOrganism().build_features(raw)
    if cross is not None:
        from core.research import add_cross
        feat = add_cross(feat, cross)
    return feat


def organism_decision(raw, cfg, now, cross=None, wake_bar=None, wake_interval_h=None, feed_delay_min=0.0,
                      minutes=None, rr=None, mind_hook=None):
    """mind_hook(mind): اختیاری، قبل از اجرای ذهن (مثلاً بذر استخر استراتژی از یادگیری زنده).
    raw: کندل‌های بسته‌شده‌ی PAXG-USD. wake_bar: آخرین کندل بسته‌ی مرجع ساعات CME (GC=F ۱ دقیقه).
    برمی‌گرداند: (Decision, ctx) — ctx = journal/feat/mind/ledger برای جدول‌های تاریخچه (همان اجرای ذهن)."""
    now = pd.Timestamp(now)
    feat = _features(raw, cross)
    m = Mind(cfg)
    if mind_hook: mind_hook(m)
    j = m.run(feat)                                    # تصمیم روی هر کندل بسته‌شده (بدون وتوی «اکنون»)
    ref = wake_bar if wake_bar is not None else j.index[-1]
    market = status_detail(ref, now, wake_interval_h or cfg.bar_hours, feed_delay_min=feed_delay_min)
    confirmed = _from_row(j.iloc[-1], m, feat, cfg, market, False, rr)
    current = confirmed
    if not confirmed.asleep and minutes is not None:
        step = pd.Timedelta(minutes=int(round(cfg.bar_hours * 60)))
        bar, _ = forming_bar(raw, minutes, step)
        if bar is not None:
            ext = pd.concat([raw, bar[list(raw.columns.intersection(bar.columns))]])
            f2 = _features(ext, cross)
            m2 = Mind(cfg)
            if mind_hook: mind_hook(m2)
            j2 = m2.run(f2)
            current = _from_row(j2.iloc[-1], m2, f2, cfg, market, True, rr)
    current = replace(current, confirmed=confirmed)
    return current, dict(journal=j, feat=feat, mind=m)


# ---------- نگاشت‌های نمایشی (فقط از Decision) ----------
def advice_key(dec: Optional[Decision]):
    """«با کمک رسول واحد»."""
    if dec is None or dec.asleep:
        return "adv_wait"
    return {"LONG": "adv_long", "SHORT": "adv_short"}.get(dec.action, "adv_wait")


def status_key(dec: Decision):
    return {"open": "st_open", "closed": "st_closed", "awaiting": "st_awaiting", "stale": "st_stale"}[dec.market_state]


def signal_card(dec: Decision):
    """کارت سیگنال: فقط از تصمیم تأییدشده (کندل بسته)."""
    c = dec.confirmed or dec
    if c.asleep or c.action not in ("LONG", "SHORT"):
        return None
    return dict(action=c.action, entry=c.entry, stop=c.stop, target=c.target, confidence=c.confidence,
                issued=c.bar_close, expires=c.bar_close + pd.Timedelta(hours=c.interval_h))


def live_signal(dec: Decision):
    """ورودی حساب کاغذی زنده/آزمون دستی: همان تصمیم تأییدشده."""
    c = dec.confirmed or dec
    return "WAIT" if c.asleep else c.action
