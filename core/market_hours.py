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

try:   # تعطیلات رسمی CME (اختیاری)
    import exchange_calendars as _xc
    _CAL = _xc.get_calendar("CMES")
except Exception:  # pragma: no cover
    _CAL = None


from functools import lru_cache


@lru_cache(maxsize=20000)
def _holiday_date(d) -> bool:
    if _CAL is None or d.weekday() >= 5:
        return False
    try:
        return not _CAL.is_session(pd.Timestamp(d))
    except Exception:
        return False


def _holiday(t_ct) -> bool:
    return _holiday_date((t_ct + pd.Timedelta(hours=7)).date())   # جلسه از 17:00 روز قبل


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
    return not _holiday(t)


is_open = is_market_open


def open_mask(index, bar_hours: float):
    """True فقط برای کندل‌هایی که بازار باز است و «اولین کندل پس از بازگشایی» نیستند."""
    idx = pd.DatetimeIndex(index)
    is_o = pd.Series([is_market_open(t) for t in idx], index=idx)
    gap = pd.Series(idx, index=idx).diff() > pd.Timedelta(hours=bar_hours * 2.5)
    first_after_reopen = gap | ~is_o.shift(1, fill_value=True)
    return (is_o & ~first_after_reopen).values


def drop_forming_candle(df, bar_hours: float, now=None):
    """کندل در حال شکل‌گیری حذف می‌شود: فقط کندل‌هایی که index + طول کندل <= اکنون."""
    if df is None or df.empty:
        return df
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if df.index[-1] + pd.Timedelta(hours=bar_hours) > now:
        return df.iloc[:-1]
    return df


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
