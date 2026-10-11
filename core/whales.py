# core/whales.py
"""
رابط افزونه‌ای «خوراک نهنگ‌ها».
  - CandleWhaleProxy (رایگان، همیشه فعال): حجم یا بدنه‌ی کندل غیرعادی نسبت به گذشته.
  - ArkhamWhaleFeed: فقط اگر متغیر محیطی ARKHAM_API_KEY تنظیم شده باشد (API رسمی Arkham نیاز به کلید تأییدشده دارد؛
    هیچ اسکرپ وب‌سایتی انجام نمی‌شود). در غیر این صورت غیرفعال است.
خروجی هر خوراک: Series بولی Whale_Event هم‌تراز با ایندکس کندل‌ها (فقط گذشته).
"""
import os
import numpy as np
import pandas as pd
import requests


class WhaleFeed:
    name = "base"

    def available(self) -> bool:
        return True

    def events(self, candles: pd.DataFrame, asset: str) -> pd.Series:
        raise NotImplementedError


class CandleWhaleProxy(WhaleFeed):
    name = "candle_proxy"

    def __init__(self, vol_mult=3.0, range_mult=3.0, lookback=50):
        self.vol_mult, self.range_mult, self.lookback = vol_mult, range_mult, lookback

    def events(self, candles, asset=""):
        v = candles["Volume"]; rng = candles["High"] - candles["Low"]
        vn = v.shift(1).rolling(self.lookback, min_periods=5).median()
        rn = rng.shift(1).rolling(self.lookback, min_periods=5).median()
        return ((v > self.vol_mult * vn) | (rng > self.range_mult * rn)).fillna(False).rename("Whale_Event")


class ArkhamWhaleFeed(WhaleFeed):
    """API رسمی Arkham (https://api.arkhamintelligence.com) — انتقال‌های بزرگ بر حسب دلار."""
    name = "arkham"
    BASE = "https://api.arkhamintelligence.com"
    TOKENS = {"BTC-USD": "bitcoin", "ETH-USD": "ethereum"}

    def __init__(self, usd_threshold=10_000_000, session=None):
        self.key = os.getenv("ARKHAM_API_KEY")
        self.usd_threshold, self.session = usd_threshold, session or requests.Session()

    def available(self):
        return bool(self.key)

    def fetch_transfers(self, asset, since):
        r = self.session.get(f"{self.BASE}/transfers", headers={"API-Key": self.key}, timeout=30,
                             params={"tokens": self.TOKENS.get(asset, asset), "usdGte": self.usd_threshold,
                                     "timeGte": int(pd.Timestamp(since).timestamp() * 1000), "limit": 500})
        r.raise_for_status()
        return r.json().get("transfers", [])

    def events(self, candles, asset):
        if not self.available():
            raise RuntimeError("ARKHAM_API_KEY تنظیم نشده است")
        tr = self.fetch_transfers(asset, candles.index[0])
        times = pd.to_datetime([t.get("blockTimestamp") for t in tr], utc=True, errors="coerce").dropna()
        idx = candles.index.tz_convert("UTC")
        bar = pd.Series(idx).diff().median()
        hit = np.zeros(len(idx), bool)
        pos = np.searchsorted(idx.values, times.values, side="right") - 1   # رویداد درون کندل → همان کندل
        pos = pos[(pos >= 0) & (pos < len(idx))]
        hit[pos] = True
        return pd.Series(hit, index=candles.index, name="Whale_Event")


def active_feeds():
    feeds = [CandleWhaleProxy()]
    ark = ArkhamWhaleFeed()
    if ark.available():
        feeds.append(ark)
    return feeds


def combined_whale(candles, asset, feeds=None):
    feeds = feeds or active_feeds()
    out = pd.Series(False, index=candles.index, name="Whale_Event")
    used = []
    for f in feeds:
        try:
            out |= f.events(candles, asset).reindex(candles.index, fill_value=False)
            used.append(f.name)
        except Exception as e:  # خوراک خراب نباید ارگانیسم را بکشد
            used.append(f"{f.name}: خطا {type(e).__name__}")
    return out, used
