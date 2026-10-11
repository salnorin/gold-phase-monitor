# core/crypto.py
"""
بخش کریپتو — فقط کاغذی. هیچ کد سفارش یا انتقال وجود ندارد.
  - داده: کندل‌های عمومی Coinbase Exchange (بدون کلید)
  - بازار ۲۴/۷: Market_Open همیشه True
  - قوانین: سقف مجازی ۱۰ دلار، حداکثر ریسک ۱٪ در هر معامله، توقف خودکار در ۷ دلار
  - نمای پرتفوی فقط‌خواندنی با کلید CDP (فقط متدهای لیست/مشاهده)
"""
import json
import os
import time
from dataclasses import replace

import pandas as pd
import requests

from core.mind import Mind, MindConfig
from core.organism import BiologicalOrganism

PRODUCTS = ("BTC-USD", "ETH-USD")
PUBLIC_URL = "https://api.exchange.coinbase.com/products/{p}/candles"
GRAN = {"1h": 3600, "15m": 900, "5m": 300}
SECRET_PATH = os.path.expanduser("~/.secrets/coinbase_cdp.json")

CRYPTO_CONFIG = MindConfig(start_equity=10.0, base_risk=0.01, min_risk=0.0025, max_risk=0.01,
                           capital_cap=10.0, kill_equity=7.0, market="24/7", leverage=1.0)


def fetch_candles(product="BTC-USD", interval="1h", bars=2000, session=None, now=None):
    """کندل‌های عمومی (حداکثر ۳۰۰ در هر درخواست، صفحه‌بندی به عقب). کندل در حال شکل‌گیری حذف می‌شود."""
    s = session or requests.Session()
    g = GRAN[interval]
    end = pd.Timestamp.now(tz="UTC").floor(f"{g}s") if now is None else pd.Timestamp(now)
    frames = []
    while sum(len(f) for f in frames) < bars:
        start = end - pd.Timedelta(seconds=g * 300)
        r = s.get(PUBLIC_URL.format(p=product), params={"granularity": g, "start": start.isoformat(), "end": end.isoformat()},
                  timeout=20, headers={"User-Agent": "gold-phase-monitor-paper"})
        r.raise_for_status()
        rows = r.json()
        if not rows:
            break
        frames.append(pd.DataFrame(rows, columns=["t", "Low", "High", "Open", "Close", "Volume"]))
        end = start
        time.sleep(0.15)
    if not frames:
        return None
    df = pd.concat(frames).drop_duplicates("t").sort_values("t")
    df.index = pd.to_datetime(df.pop("t"), unit="s", utc=True)
    df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    cutoff = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    return df[df.index + pd.Timedelta(seconds=g) <= cutoff].tail(bars)


CRYPTO_SIM = dict(start_equity=10.0, risk_cap=0.01, kill_equity=7.0)


def crypto_features(raw, product="BTC-USD", defi_sig=None, whale_feeds=None):
    """ارگان‌ها + نهنگ (پراکسی/Arkham) + اکسیژن DeFi (اگر داده باشد)."""
    from core.whales import combined_whale
    from core.defi import attach_defi
    feat = BiologicalOrganism().build_features(raw, market="24/7")
    w, used = combined_whale(feat, product, whale_feeds)
    feat["Whale_Event"] = w.values
    if defi_sig is not None:
        feat = attach_defi(feat, defi_sig)
    feat.attrs["whale_feeds"] = used
    return feat


def run_crypto_arena(feat, interval="1h", pop=2000, generations=6, tiers=(1.0, 10.0, 20.0), seed=0):
    """همان میدان تکامل برای هر دارایی، با سقف ۱۰ دلار، ریسک ۱٪ و حذف در ۷ دلار."""
    from core import arena as A
    from core.paper import CostModel
    df, F = A.feature_matrix(feat)
    is_end = int(len(df) * 0.7); oos = min(len(df) - 2, is_end + 48)
    hours = GRAN[interval] / 3600
    out = {}
    for lev in tiers:
        cm = CostModel(leverage=lev, bar_hours=hours)
        G, final, hist = A.evolve(F, df, is_end, cm, pop=pop, generations=generations, seed=seed, warmup=50, sim_kw=CRYPTO_SIM)
        d, champs = A.deflation_test(G, final, F, df, oos, len(df), cm, sim_kw=CRYPTO_SIM)
        out[lev] = dict(history=hist, deflation=d)
    return out, df.index[oos]


def run_crypto_mind(raw, interval="1h", cfg: MindConfig = CRYPTO_CONFIG, feat=None):
    hours = GRAN[interval] / 3600
    feat = feat if feat is not None else BiologicalOrganism().build_features(raw, market="24/7")
    m = Mind(replace(cfg, bar_hours=hours))
    j = m.run(feat)
    return m, j


class ReadOnlyCoinbase:
    """پوسته‌ی فقط‌خواندنی: فقط لیست حساب‌ها و پرتفوی. هیچ متد سفارش/انتقالی در دسترس نیست."""
    ALLOWED = ("get_accounts", "get_portfolios", "get_portfolio_breakdown")

    def __init__(self, path=SECRET_PATH):
        from coinbase.rest import RESTClient
        with open(path) as f:
            k = json.load(f)
        self._c = RESTClient(api_key=k["name"], api_secret=k["privateKey"])

    def __getattr__(self, name):
        if name in ReadOnlyCoinbase.ALLOWED:
            return getattr(self._c, name)
        raise AttributeError(f"'{name}' مجاز نیست (فقط‌خواندنی)")

    def balances(self):
        accs = self._c.get_accounts(limit=250).to_dict().get("accounts", [])
        rows = []
        for a in accs:
            avail = float(a["available_balance"]["value"]); hold = float((a.get("hold") or {}).get("value", 0) or 0)
            if avail + hold > 0:
                rows.append(dict(asset=a["currency"], available=avail, hold=hold))
        totals = []
        for p in self._c.get_portfolios().to_dict().get("portfolios", []):
            b = self._c.get_portfolio_breakdown(p["uuid"]).to_dict()["breakdown"]["portfolio_balances"]["total_balance"]
            totals.append(dict(portfolio=p["name"], total=float(b["value"]), currency=b["currency"]))
        return pd.DataFrame(rows), pd.DataFrame(totals)
