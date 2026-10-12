# core/movement.py
"""
تحلیل «حرکت» قیمت PAXG-USD روی کندل‌های ۱ دقیقه‌ای (فقط نمایش؛ هیچ تصمیم/سفارشی).
- day_window: امروز به وقت برلین؛ اگر خیلی کم بود، ۲۴ ساعت اخیر.
- time_at_price: هیستوگرام زمان-در-قیمت از Close های ۱ دقیقه‌ای (دقیقه در هر سطل) + پربازدیدترین نوارها.
- touch_levels: سطوح حمایت/مقاومت از پیوت‌های محلی که در یک تلورانس خوشه شده‌اند؛ برترین‌ها با تعداد برخورد.
- pause_zones: بازه‌هایی که دامنه‌ی قیمت حداقل N دقیقه تنگ ماند (تثبیت/انتظار).
"""
import numpy as np
import pandas as pd

BERLIN = "Europe/Berlin"


def day_window(m1, now=None, min_bars=60):
    """m1: کندل‌های ۱ دقیقه‌ای (index tz-aware). برمی‌گرداند (df, 'today'|'24h')."""
    if m1 is None or m1.empty:
        return m1, "24h"
    idx = m1.index.tz_convert(BERLIN)
    d = m1.copy(); d.index = idx
    now = pd.Timestamp.now(tz=BERLIN) if now is None else pd.Timestamp(now).tz_convert(BERLIN)
    d = d[d.index <= now]
    today = d[d.index >= now.normalize()]
    if len(today) >= min_bars:
        return today, "today"
    return d[d.index >= now - pd.Timedelta(hours=24)], "24h"


def change(df):
    a, b = float(df["Open"].iloc[0]), float(df["Close"].iloc[-1])
    return a, b, (b / a - 1) if a else 0.0


def time_at_price(close, bins=None, top=3):
    """(edges, minutes_per_bin, top_bands[(lo, hi, minutes)])."""
    c = np.asarray(close, float)
    lo, hi = float(c.min()), float(c.max())
    if hi - lo < 1e-9:
        hi = lo + 0.01
    bins = bins or int(np.clip(np.sqrt(len(c)) * 1.5, 10, 40))
    cnt, edges = np.histogram(c, bins=bins, range=(lo, hi))
    order = np.argsort(cnt)[::-1]
    bands = [(float(edges[i]), float(edges[i + 1]), int(cnt[i])) for i in order[:top] if cnt[i] > 0]
    return edges, cnt, bands


def pivots(df, k=5):
    """پیوت‌های محلی: High بیشینه / Low کمینه در پنجره‌ی ±k."""
    h, l = df["High"].values, df["Low"].values
    out = []
    for i in range(k, len(df) - k):
        if h[i] == h[i - k:i + k + 1].max():
            out.append((i, float(h[i]), "R"))
        if l[i] == l[i - k:i + k + 1].min():
            out.append((i, float(l[i]), "S"))
    return out


def touch_levels(df, tol=None, k=5, top=5, min_touches=2):
    """خوشه‌بندی پیوت‌ها در تلورانس (پیش‌فرض: max(0.03٪ قیمت، ۰٫۵×میانه‌ی دامنه‌ی ۱ دقیقه)).
    برمی‌گرداند [{price, touches, kind}] — مرتب بر تعداد برخورد."""
    if df is None or len(df) < 2 * k + 2:
        return []
    px = float(df["Close"].iloc[-1])
    rng = float((df["High"] - df["Low"]).median())
    tol = tol or max(px * 0.0003, 0.5 * rng, 0.01)
    pts = sorted(pivots(df, k), key=lambda x: x[1])
    clusters = []
    for i, p, kind in pts:
        if clusters and p - clusters[-1]["hi"] <= tol:
            c = clusters[-1]; c["pts"].append(p); c["idx"].append(i); c["kinds"].append(kind); c["hi"] = p
        else:
            clusters.append(dict(pts=[p], idx=[i], kinds=[kind], hi=p))
    out = []
    for c in clusters:
        # برخوردهای جدا: پیوت‌هایی که حداقل k کندل از هم فاصله دارند
        idx = sorted(c["idx"]); n = 1
        for a, b in zip(idx, idx[1:]):
            if b - a > k:
                n += 1
        if n >= min_touches:
            kind = "S" if c["kinds"].count("S") >= c["kinds"].count("R") else "R"
            out.append(dict(price=round(float(np.mean(c["pts"])), 2), touches=n, kind=kind))
    out.sort(key=lambda x: (-x["touches"], abs(x["price"] - px)))
    return out[:top]


def pause_zones(df, minutes=20, tight=None):
    """بازه‌های تثبیت: دامنه‌ی (max High − min Low) ≤ tight برای حداقل `minutes` دقیقه‌ی پیوسته.
    tight پیش‌فرض: max(0.04٪ قیمت، ۲×میانه‌ی دامنه‌ی ۱ دقیقه). حریصانه، بدون هم‌پوشانی."""
    if df is None or len(df) < minutes:
        return []
    h, l = df["High"].values, df["Low"].values
    px = float(df["Close"].iloc[-1])
    tight = tight or max(px * 0.0004, 2 * float(np.median(h - l)), 0.02)
    out, i, n = [], 0, len(df)
    while i < n:
        j, hi, lo = i, h[i], l[i]
        while j + 1 < n and max(hi, h[j + 1]) - min(lo, l[j + 1]) <= tight:
            j += 1; hi = max(hi, h[j]); lo = min(lo, l[j])
        dur = int(round((df.index[j] - df.index[i]).total_seconds() / 60)) + 1
        if dur >= minutes:
            out.append(dict(start=df.index[i], end=df.index[j], lo=float(lo), hi=float(hi), minutes=dur))
            i = j + 1
        else:
            i += 1
    return out
