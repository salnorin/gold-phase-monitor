# core/market_hours.py
"""
ساعات بازار آتی طلا (CME Globex, GC) — بر حسب وقت شیکاگو (DST به‌طور خودکار):
  - تعطیلی آخر هفته: جمعه 16:00 CT تا یکشنبه 17:00 CT  (≈ جمعه 23:00 تا دوشنبه 00:00 برلین)
  - وقفه‌ی روزانه: 16:00–17:00 CT دوشنبه تا پنجشنبه      (≈ 23:00–00:00 برلین)
  - داده‌ی کهنه: اگر آخرین کندل قدیمی‌تر از (۱ + stale_intervals) بازه باشد → بسته/خواب
تعطیلات رسمی مدل نشده‌اند؛ تشخیص داده‌ی کهنه آن‌ها را پوشش می‌دهد.
"""
import pandas as pd

CT = "America/Chicago"


def is_market_open(ts) -> bool:
    t = pd.Timestamp(ts)
    t = (t.tz_localize("UTC") if t.tzinfo is None else t).tz_convert(CT)
    wd, hm = t.weekday(), t.hour + t.minute / 60
    if wd == 5:                      # شنبه
        return False
    if wd == 4 and hm >= 16:         # جمعه بعد از 16:00
        return False
    if wd == 6 and hm < 17:          # یکشنبه قبل از 17:00
        return False
    if wd in (0, 1, 2, 3) and 16 <= hm < 17:   # وقفه‌ی روزانه
        return False
    return True


def is_stale(last_bar_time, now, interval_hours: float, stale_intervals: float = 2.0) -> bool:
    """last_bar_time زمان شروع کندل است؛ کندل بسته‌شده تا یک بازه بعد معتبر است."""
    age = pd.Timestamp(now) - pd.Timestamp(last_bar_time)
    return age > pd.Timedelta(hours=interval_hours * (1 + stale_intervals))


def market_status(last_bar_time, now, interval_hours):
    if not is_market_open(now):
        return False, "بازار بسته است (تعطیلی آخر هفته یا وقفه‌ی روزانه CME) → ارگانیسم خواب است"
    if is_stale(last_bar_time, now, interval_hours):
        return False, "داده‌ی کهنه (کندل تازه‌ای نیامده) → ارگانیسم خواب است"
    return True, "بازار باز است"
