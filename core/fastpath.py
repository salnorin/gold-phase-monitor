# core/fastpath.py
"""
Client for the optional Go fast-path daemon (fastpath-go, 127.0.0.1:8787). PAPER ONLY, read-only.
If the daemon is not running (e.g. on Streamlit Cloud), every call falls back to the Python fetch in core.gold_price.
"""
import os
import requests

URL = os.getenv("GPM_FASTPATH_URL", "http://127.0.0.1:8787")
TIMEOUT = 0.25


def _get(path):
    try:
        r = requests.get(URL + path, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def available():
    h = _get("/health")
    return bool(h and h.get("ok"))


def books():
    d = _get("/book")
    return d["books"] if d else None


def arb():
    return _get("/arb")


def paxg_price():
    """(price, source). Mid price from fast path (Coinbase, then Kraken); fallback core.gold_price.ticker()."""
    b = books()
    if b:
        usd = [x for x in b if x.get("quote") == "USD" and x["bid"] > 0]
        if usd:   # freshest USD venue (Coinbase ticker only updates on trades; Kraken BBO updates on every quote change)
            t = max(usd, key=lambda x: x.get("recv_ts", ""))
            return (t["bid"] + t["ask"]) / 2, f"fastpath:{t['venue']}"
    from core import gold_price
    return gold_price.ticker(), "python:coinbase/kraken"
