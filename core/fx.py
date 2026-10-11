# core/fx.py
"""
نرخ زنده‌ی EUR/USD برای تبدیل سقف سرمایه‌ی مجازی (یورو) به دلار. هیچ نرخ ثابتی در کد نیست.
  ۱) yfinance 'EURUSD=X'   ۲) Frankfurter (ECB، رایگان، بدون کلید)   ۳) آخرین نرخ معتبر ذخیره‌شده (با هشدار)
کش ۱۰ دقیقه‌ای روی دیسک.
"""
import json
import os
import time
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import requests

from core.config import AUTO_STOP_FRACTION, MAX_RISK_PER_TRADE, PAPER_CAPITAL_EUR

CACHE_DIR = os.path.expanduser(os.getenv("GPM_CACHE_DIR", "~/.cache/gold-phase-monitor"))
TTL = 600
FRANKFURTER = "https://api.frankfurter.app/latest?from=EUR&to=USD"


@dataclass
class FxQuote:
    rate: float
    timestamp: pd.Timestamp
    source: str
    warning: Optional[str] = None


@dataclass
class Capital:
    eur: float
    usd: float
    risk_usd: float
    stop_usd: float
    rate: float
    timestamp: pd.Timestamp
    source: str
    warning: Optional[str] = None


def _paths():
    return os.path.join(CACHE_DIR, "eurusd_cache.json"), os.path.join(CACHE_DIR, "eurusd_last_good.json")


def _from_yfinance():
    import yfinance as yf
    df = yf.download("EURUSD=X", period="5d", interval="1h", progress=False, auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError("yfinance empty")
    close = df["Close"].dropna()
    close = close.iloc[:, 0] if hasattr(close, "columns") else close
    t = pd.Timestamp(close.index[-1]); t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return FxQuote(float(close.iloc[-1]), t, "yfinance EURUSD=X")


def _from_frankfurter(session=None):
    r = (session or requests).get(FRANKFURTER, timeout=15, headers={"User-Agent": "gold-phase-monitor-paper"})
    r.raise_for_status()
    js = r.json()
    return FxQuote(float(js["rates"]["USD"]), pd.Timestamp(js["date"], tz="UTC"), "Frankfurter (ECB)")


def _save(path, q: FxQuote):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(dict(rate=q.rate, timestamp=str(q.timestamp), source=q.source, saved=time.time()), f)


def _load(path):
    with open(path) as f:
        d = json.load(f)
    return FxQuote(float(d["rate"]), pd.Timestamp(d["timestamp"]), d["source"]), d.get("saved", 0)


def eur_usd(use_cache=True, providers=None) -> FxQuote:
    cache, last_good = _paths()
    if use_cache and os.path.exists(cache):
        try:
            q, saved = _load(cache)
            if time.time() - saved < TTL:
                return q
        except Exception:
            pass
    errors = []
    for fn in providers or (_from_yfinance, _from_frankfurter):
        try:
            q = fn()
            if not (0.5 < q.rate < 2.5):
                raise ValueError(f"implausible rate {q.rate}")
            _save(cache, q); _save(last_good, q)
            return q
        except Exception as e:
            errors.append(f"{getattr(fn, '__name__', 'provider')}: {type(e).__name__}")
    if os.path.exists(last_good):
        q, _ = _load(last_good)
        q.warning = f"نرخ زنده در دسترس نیست؛ آخرین نرخ معتبر ({q.timestamp:%Y-%m-%d %H:%M} UTC) استفاده شد. [{'; '.join(errors)}]"
        q.source += " (last known good)"
        return q
    raise RuntimeError(f"هیچ نرخ EUR/USD در دسترس نیست: {'; '.join(errors)}")


def paper_capital(quote: FxQuote = None, eur: float = PAPER_CAPITAL_EUR) -> Capital:
    q = quote or eur_usd()
    usd = round(eur * q.rate, 2)
    return Capital(eur=eur, usd=usd, risk_usd=round(usd * MAX_RISK_PER_TRADE, 2),
                   stop_usd=round(usd * AUTO_STOP_FRACTION, 2), rate=q.rate, timestamp=q.timestamp,
                   source=q.source, warning=q.warning)
