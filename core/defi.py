# core/defi.py
"""
داده‌ی DeFi از API عمومی و رایگان DefiLlama (بدون کلید) به‌عنوان «اکسیژن/نقدینگی» کریپتو.
  - TVL کل زنجیره‌ها:      https://api.llama.fi/v2/historicalChainTvl
  - عرضه‌ی استیبل‌کوین:     https://stablecoins.llama.fi/stablecoincharts/all
  - حجم DEX روزانه:        https://api.llama.fi/overview/dexs
همه روزانه‌اند؛ برای جلوگیری از نگاه به آینده، مقدار روز D فقط از ابتدای روز D+1 (UTC) در دسترس فرض می‌شود.
"""
import numpy as np
import pandas as pd
import requests

URLS = {
    "tvl": "https://api.llama.fi/v2/historicalChainTvl",
    "stables": "https://stablecoins.llama.fi/stablecoincharts/all",
    "dex": "https://api.llama.fi/overview/dexs?excludeTotalDataChartBreakdown=true&dataType=dailyVolume",
}


def _get(url, session=None):
    r = (session or requests).get(url, timeout=40, headers={"User-Agent": "gold-phase-monitor-paper"})
    r.raise_for_status()
    return r.json()


def parse_tvl(js):
    return pd.Series({pd.Timestamp(int(x["date"]), unit="s", tz="UTC"): float(x["tvl"]) for x in js}, name="tvl")


def parse_stables(js):
    return pd.Series({pd.Timestamp(int(x["date"]), unit="s", tz="UTC"): float(x["totalCirculating"].get("peggedUSD", 0))
                      for x in js}, name="stables")


def parse_dex(js):
    return pd.Series({pd.Timestamp(int(t), unit="s", tz="UTC"): float(v) for t, v in js["totalDataChart"]}, name="dex")


def fetch_defi(session=None) -> pd.DataFrame:
    s = [parse_tvl(_get(URLS["tvl"], session)), parse_stables(_get(URLS["stables"], session)), parse_dex(_get(URLS["dex"], session))]
    return pd.concat(s, axis=1).sort_index()


def defi_signals(daily: pd.DataFrame) -> pd.DataFrame:
    """تغییرات ۷ روزه (TVL، استیبل‌کوین) و حجم DEX نسبت به میانه‌ی ۳۰ روزه‌ی گذشته."""
    d = daily.copy().sort_index().ffill()
    out = pd.DataFrame(index=d.index)
    out["TVL_7d"] = d["tvl"].pct_change(7)
    out["Stable_7d"] = d["stables"].pct_change(7)
    out["DEX_Rel"] = d["dex"] / d["dex"].shift(1).rolling(30, min_periods=5).median()
    flow = (np.tanh(out["TVL_7d"].fillna(0) * 20) + np.tanh(out["Stable_7d"].fillna(0) * 50)) / 2
    out["DeFi_Oxygen"] = (0.5 * flow + 0.5 * np.tanh((out["DEX_Rel"].fillna(1) - 1) * 2)).clip(-1, 1)
    out.index = out.index + pd.Timedelta(days=1)          # روز D فقط پس از بسته شدن در دسترس است
    return out


def attach_defi(feat: pd.DataFrame, sig: pd.DataFrame) -> pd.DataFrame:
    """merge_asof به عقب: هر کندل فقط آخرین مقدار روزانه‌ی منتشرشده را می‌بیند."""
    f = feat.copy()
    left = pd.DataFrame({"t": f.index.tz_convert("UTC")})
    right = sig.reset_index().rename(columns={"index": "t"})
    right["t"] = pd.to_datetime(right["t"], utc=True)
    m = pd.merge_asof(left, right.sort_values("t"), on="t", direction="backward")
    for col in ("TVL_7d", "Stable_7d", "DEX_Rel", "DeFi_Oxygen"):
        f[col] = m[col].fillna(0 if col != "DEX_Rel" else 1).values
    return f
