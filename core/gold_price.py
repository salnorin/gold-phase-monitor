# core/gold_price.py
"""
منبع یگانه‌ی قیمت طلا: PAXG-USD (توکن طلای Paxos، ۲۴/۷) — Coinbase عمومی، با Kraken به‌عنوان جایگزین.
همه‌جا از این ماژول استفاده می‌شود: نمایش، سیگنال، ذهن، آرنا، دفتر تصمیم، بازپخش، حساب کاغذی زنده، پر شدن/TP/SL کاغذی
و هر مجری آینده. GC=F (آتی CME) فقط «مرجع» است و فقط برای تشخیص ساعات باز بودن بازار CME استفاده می‌شود.
آتی معمولاً حدود ۳۰ دلار بالاتر از نقد است (هزینه‌ی نگهداری/carry: بهره منهای بازده نگهداری تا سررسید).
فقط خواندن داده‌ی عمومی؛ هیچ سفارش.
"""
import time
import pandas as pd
import requests

PRODUCT = "PAXG-USD"
KRAKEN_PAIR = "PAXGUSD"
REFERENCE_FUTURES = "GC=F"
UA = {"User-Agent": "gold-phase-monitor-paper"}
KRAKEN_MIN = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "6h": 240}


def _kraken_candles(interval, bars):
    """جایگزین: Kraken OHLC عمومی (حداکثر ۷۲۰ کندل). کندل در حال شکل‌گیری (آخری) حذف می‌شود."""
    js = requests.get("https://api.kraken.com/0/public/OHLC", params={"pair": KRAKEN_PAIR, "interval": KRAKEN_MIN[interval]},
                      timeout=15, headers=UA).json()
    rows = next(v for k, v in js["result"].items() if k != "last")
    df = pd.DataFrame(rows, columns=["t", "Open", "High", "Low", "Close", "vwap", "Volume", "n"])
    df.index = pd.to_datetime(df.pop("t").astype(int), unit="s", utc=True)
    return df[["Open", "High", "Low", "Close", "Volume"]].astype(float).iloc[:-1].tail(bars)


def candles(interval="1h", bars=2000):
    """کندل‌های بسته‌شده‌ی PAXG-USD (UTC). Coinbase → Kraken."""
    from core.crypto import fetch_candles
    try:
        d = fetch_candles(PRODUCT, interval, bars)
        if d is not None and len(d):
            d.index = d.index.tz_convert("America/New_York")
            d.attrs["source"] = "Coinbase PAXG-USD"
            return d
    except Exception:
        pass
    d = _kraken_candles(interval, bars)
    d.index = d.index.tz_convert("America/New_York")
    d.attrs["source"] = "Kraken PAXGUSD"
    return d


def ticker():
    """آخرین قیمت PAXG-USD (Coinbase → Kraken)، یا None."""
    try:
        r = requests.get(f"https://api.exchange.coinbase.com/products/{PRODUCT}/ticker", timeout=5, headers=UA)
        r.raise_for_status()
        return float(r.json()["price"])
    except Exception:
        try:
            js = requests.get("https://api.kraken.com/0/public/Ticker", params={"pair": KRAKEN_PAIR}, timeout=5).json()
            return float(next(iter(js["result"].values()))["c"][0])
        except Exception:
            return None
