# core/exec_prob.py
"""
اجرای خودکار با آستانه‌ی احتمال (تصمیم کاربر، فقط کاغذی).
اگر احتمال صعود یا نزول کندل بسته‌شده ≥ آستانه (GOLD_EXEC_PROB / --exec-prob، پیش‌فرض 0.55) باشد،
تصمیم LONG/SHORT می‌شود حتی اگر دروازه‌های نرم (توافق ارگان‌ها، تردید، نهنگ، اکسیژن، نوسان...) WAIT گفته باشند.
وتوهای ریسک همیشه می‌مانند: بازار بسته/خواب/داده‌ی کهنه، توقف خودکار (۷۰٪)، استراحت اجباری پس از ضرر؛
محافظ لیکوئیدیشن و SL/TP/کارمزد/ریسک ۱٪ در موتور حساب کاغذی (core.paper) اعمال می‌شوند.
exec_prob <= 0 → خاموش (فقط تصمیم خود ارگانیسم).
"""
import os

import numpy as np

RISK_VETOES = ("بسته", "خواب", "کهنه", "توقف خودکار", "استراحت اجباری")


def exec_prob_default(value=None):
    v = value if value is not None else os.getenv("GOLD_EXEC_PROB", "0.55")
    return float(v)


def is_risk_veto(reason):
    return any(k in str(reason) for k in RISK_VETOES)


def apply_exec_prob(journal, thr):
    """journal ذهن → کپی با action به‌روز. ستون exec_by: organism | prob | ''."""
    j = journal.copy()
    j["exec_by"] = np.where(j["action"].isin(["LONG", "SHORT"]), "organism", "")
    if thr is None or thr <= 0:
        return j
    veto = j["reason"].map(is_risk_veto) if "reason" in j else False
    wait = j["action"] == "WAIT"
    bull = wait & ~veto & (j["P_bull"] >= thr) & (j["P_bull"] >= j["P_bear"])
    bear = wait & ~veto & (j["P_bear"] >= thr) & (j["P_bear"] > j["P_bull"])
    j.loc[bull, "action"] = "LONG"
    j.loc[bear, "action"] = "SHORT"
    j.loc[bull | bear, "exec_by"] = "prob"
    return j


def live_action(dec, thr):
    """اقدام نهایی کندل بسته‌شده‌ی آخر برای حساب زنده."""
    c = dec.confirmed or dec
    if c.asleep or is_risk_veto(c.reason):
        return ("WAIT" if c.asleep else c.action), ("organism" if c.action != "WAIT" and not c.asleep else "")
    if c.action in ("LONG", "SHORT"):
        return c.action, "organism"
    if thr and thr > 0:
        if c.P_bull >= thr and c.P_bull >= c.P_bear:
            return "LONG", "prob"
        if c.P_bear >= thr and c.P_bear > c.P_bull:
            return "SHORT", "prob"
    return "WAIT", ""
