import numpy as np
import pandas as pd

from core.movement import change, day_window, pause_zones, time_at_price, touch_levels


def _m1(close, start="2026-10-12 00:00"):
    idx = pd.date_range(start, periods=len(close), freq="min", tz="Europe/Berlin")
    c = np.asarray(close, float)
    return pd.DataFrame(dict(Open=c, High=c + 0.05, Low=c - 0.05, Close=c, Volume=1.0), index=idx)


def test_day_window_today_and_fallback():
    d = _m1(np.full(300, 4200.0), start="2026-10-11 22:00")
    today, mode = day_window(d, now="2026-10-12 02:59+02:00", min_bars=60)
    assert mode == "today" and today.index[0] >= pd.Timestamp("2026-10-12", tz="Europe/Berlin")
    _, mode2 = day_window(d, now="2026-10-12 00:10+02:00", min_bars=60)
    assert mode2 == "24h"


def test_change_and_time_at_price():
    d = _m1([4200] * 50 + [4210] * 10)
    a, b, p = change(d)
    assert a == 4200 and b == 4210 and abs(p - 10 / 4200) < 1e-12
    edges, cnt, bands = time_at_price(d["Close"], bins=10, top=1)
    assert cnt.sum() == 60 and bands[0][2] == 50 and bands[0][0] <= 4200 <= bands[0][1]


def test_touch_levels_find_repeated_bounce():
    t = np.arange(240)
    c = 4200 + 3 * np.abs(np.sin(t / 15))          # bounces off 4200 repeatedly
    lv = touch_levels(_m1(c), k=5)
    assert lv and min(abs(x["price"] - 4200) for x in lv) < 0.3
    assert max(x["touches"] for x in lv) >= 3 and len(lv) <= 5


def test_pause_zones_detects_flat_period():
    c = np.r_[np.linspace(4200, 4210, 30), np.full(45, 4210.0), np.linspace(4210, 4200, 30)]
    z = pause_zones(_m1(c), minutes=20)
    assert len(z) == 1 and 45 <= z[0]["minutes"] <= 60
