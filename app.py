import json
# app.py — داشبورد موجود زنده (فقط شبیه‌سازی کاغذی؛ هیچ سفارش واقعی)
from datetime import timedelta
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from core.live_account import DATA_DIR
from core.config import ENERGY_FEE_PCT, ENERGY_FEE_MODE

from core.arena import run_arena
from core.mind import FA, Mind, MindConfig, capital_mind_config
from core.fx import paper_capital
from core.market_hours import FEED_DELAY_MIN, status_detail
from core.organism import BiologicalOrganism
from core.research import load

from core.i18n import CREDIT, LANGS, RTL, norm, regime, t as _t

# ---------- زبان: ?lang= ← session_state؛ پیش‌فرض فارسی ----------
if "lang" not in st.session_state:
    st.session_state.lang = norm(st.query_params.get("lang"))
L = st.session_state.lang


def T(key, **kw):
    return _t(key, L, **kw)


def _set_lang(src):
    v = st.session_state.get(src)
    if v:
        st.session_state.lang = v
        st.session_state.lang_top = st.session_state.lang_side = v
        st.query_params["lang"] = v


st.session_state.setdefault("lang_top", L)
st.session_state.setdefault("lang_side", L)

st.set_page_config(page_title=T("page_title"), page_icon="🐻", layout="wide", initial_sidebar_state="collapsed")
RTL_ON = L in RTL
DIR = "rtl" if RTL_ON else "ltr"
COL = {"LONG": "#22c55e", "SHORT": "#ef4444", "WAIT": "#94a3b8"}     # رنگ‌های ثابت جهت
GOLD = "#e8b931"
st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap');
html, body, [class*="css"], .stMarkdown, .stMetric, button, input {{ font-family: {"'Vazirmatn', " if RTL_ON else ""}'Inter', system-ui, sans-serif; }}
[data-testid='stMainBlockContainer'] {{ padding-top: 3rem; max-width: 1300px; }}
[data-testid='stMainBlockContainer'] .stMarkdown, [data-testid='stMainBlockContainer'] .stCaption {{ direction: {DIR}; text-align: {"right" if RTL_ON else "left"}; }}
[data-testid='stMetric'] {{ background: rgba(255,255,255,.035); border: 1px solid rgba(232,185,49,.18); border-radius: 14px; padding: 12px 14px; }}
[data-testid='stMetricLabel'] {{ opacity: .8; }}
.stTabs [data-baseweb='tab-list'] {{ gap: 6px; }}
.stTabs [data-baseweb='tab'] {{ background: rgba(255,255,255,.04); border-radius: 10px 10px 0 0; padding: 8px 14px; }}
.stTabs [aria-selected='true'] {{ color: {GOLD} !important; }}
.hero {{ direction:{DIR}; display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:6px; }}
.hero h1 {{ margin:0; font-size:1.9rem; font-weight:800; color:{GOLD}; }}
.card {{ direction:{DIR}; border-radius:16px; padding:14px 16px; margin-bottom:12px; }}
@media (max-width: 640px) {{
  [data-testid='stMainBlockContainer'] {{ padding: .6rem .7rem; }}
  .hero h1 {{ font-size: 1.25rem; }}
  .card {{ padding: 10px 12px; border-radius: 12px; font-size: .92em; }}
  [data-testid='stMetric'] {{ padding: 8px 10px; }}
  [data-testid='stMetricValue'] {{ font-size: 1.3rem; }}
  svg {{ max-width: 170px; height: auto; }}
  .stTabs [data-baseweb='tab'] {{ padding: 6px 8px; font-size: .85em; }}
  .hide-mobile {{ display: none; }}
}}
.credit {{ text-align:center; direction:{DIR}; opacity:.7; margin-top:24px; font-size:.9em; }}
</style>""", unsafe_allow_html=True)

top_l, top_r = st.columns([3, 2])
with top_l:
    st.markdown(f"<div class='hero'><h1>{T('title')}</h1></div>", unsafe_allow_html=True)
with top_r:
    st.segmented_control(T("language"), list(LANGS), format_func=LANGS.get, key="lang_top",
                         on_change=_set_lang, args=("lang_top",), label_visibility="collapsed")
st.caption(f"{T('disclaimer')} · {CREDIT[L]}")
st.sidebar.radio(T("language"), list(LANGS), format_func=LANGS.get, key="lang_side", on_change=_set_lang, args=("lang_side",))

BERLIN = "Europe/Berlin"
CREDIT_FA = CREDIT["fa"]


def credit_footer():
    st.markdown(f"<div class='credit'>{CREDIT[L]}</div>", unsafe_allow_html=True)


def to_berlin(df):
    df = df.copy()
    if isinstance(df.index, pd.DatetimeIndex):
        df.index = df.index.tz_convert(BERLIN).strftime("%Y-%m-%d %H:%M")
    for c in ("entry_time", "exit_time"):
        if c in df:
            df[c] = pd.to_datetime(df[c], utc=True).dt.tz_convert(BERLIN).dt.strftime("%Y-%m-%d %H:%M")
    return df


@st.cache_data(ttl=600, show_spinner=False)
def capital():
    return paper_capital()


@st.cache_data(ttl=50, show_spinner=False)
def latest_fast_candle():
    """بیداری مستقل از بازه‌ی سیگنال: آخرین کندل بسته‌شده‌ی ۱ دقیقه‌ای طلا (بیدار اگر < ~۳ دقیقه)."""
    try:
        d = load("GC=F", "1m")
        return d.index[-1] if d is not None and len(d) else None
    except Exception:
        return None


INTERVAL_H = {"1h": 1.0, "15m": 0.25, "5m": 5 / 60}
interval = st.sidebar.selectbox(T("interval"), list(INTERVAL_H), index=0)
leverage = st.sidebar.select_slider(T("leverage"), options=[1, 5, 10, 20], value=20)
pop = st.sidebar.select_slider(T("population"), options=[500, 2000, 10000], value=2000)
manual = st.sidebar.toggle(T("manual_preset"), value=False, help=T("manual_help"))
live = st.sidebar.checkbox(T("auto"), value=True)


@st.cache_data(ttl=60, show_spinner=False)
def get_data(interval):
    from core import gold_price
    raw = gold_price.candles(interval, 3000)        # PAXG-USD: قیمت یگانه‌ی طلا
    try:
        cross = load("SI=F", interval)
    except Exception:
        cross = None
    return raw, cross


@st.cache_data(ttl=240, show_spinner=False)
def run_mind(raw, cross, interval, leverage):
    from core.research import add_cross
    feat = BiologicalOrganism().build_features(raw)
    if cross is not None:
        feat = add_cross(feat, cross)
    m = Mind(capital_mind_config(capital(), leverage=float(leverage), bar_hours=INTERVAL_H[interval]))
    j = m.run(feat, now=pd.Timestamp.now(tz="UTC"))
    led = m.ledger.frame()
    try:
        m.ledger.save(DATA_DIR / f"ledger_{interval}_{leverage:g}x.sqlite")
    except Exception:
        pass
    extra = dict(ledger=led, energy=m.energy_spent, gate_regret=m.gate_regret)
    return feat, j, m.trades_frame(), m.blackbox_frame(), m.explain(), m.events, m.strat, extra


@st.cache_data(ttl=3600, show_spinner=False)
def run_arena_cached(raw, cross, interval, pop):
    res, cut = run_arena(raw, cross, INTERVAL_H[interval], pop=pop, generations=6)
    return {lev: dict(history=r["history"], deflation=r["deflation"]) for lev, r in res.items()}, cut


MOUTH = {"happy": "M96 106 Q110 122 124 106", "sad": "M98 116 Q110 104 122 116", "neutral": "M100 108 Q110 116 120 108"}


def warning_box():
    st.markdown(f"<div class='card' dir='{DIR}' style='direction:{DIR};text-align:{"right" if RTL_ON else "left"};"
                f"border:1px solid #f59e0b66;background:#f59e0b14;font-size:.9em'>{T('warning3')}</div>", unsafe_allow_html=True)


def creature_svg(breath_s, hue, label, mood="neutral", bias=0, asleep=False):
    lean = 6 * bias
    droop = f"transform: translateY({6 if mood == 'sad' else 0}px) rotate({lean - (3 if mood == 'sad' else 0)}deg);"
    sat, light = (30, 38) if mood == "sad" else (55, 42)
    if asleep:
        sat, light = 0, 45
    return f"""
<div style="display:flex;justify-content:center">
<svg viewBox="0 0 220 200" width="260" height="236" xmlns="http://www.w3.org/2000/svg">
 <style>
  .body {{ transform-origin: 110px 120px; animation: breathe {breath_s:.2f}s ease-in-out infinite; }}
  @keyframes breathe {{ 0%,100% {{ transform: scale(1,1); }} 50% {{ transform: scale(1.06,1.10); }} }}
  .eye {{ animation: blink 5s infinite; transform-origin: center; }}
  @keyframes blink {{ 0%,94%,100% {{ transform: scaleY(1); }} 97% {{ transform: scaleY(0.1); }} }}
 </style>
 <g class="body" fill="hsl({hue},{sat}%,{light}%)" style="{droop}">
  <circle cx="62" cy="52" r="20"/><circle cx="158" cy="52" r="20"/>
  <circle cx="62" cy="52" r="10" fill="hsl({hue},45%,65%)"/><circle cx="158" cy="52" r="10" fill="hsl({hue},45%,65%)"/>
  <ellipse cx="110" cy="140" rx="70" ry="52"/>
  <circle cx="110" cy="85" r="52"/>
  <ellipse cx="110" cy="102" rx="24" ry="18" fill="hsl({hue},40%,72%)"/>
  <ellipse cx="110" cy="95" rx="9" ry="6" fill="#222"/>
  <path d="{MOUTH.get(mood, MOUTH['neutral'])}" stroke="#222" stroke-width="3" fill="none"/>
  <g class="eye"><circle cx="90" cy="72" r="6" fill="#111"/><circle cx="130" cy="72" r="6" fill="#111"/></g>
  <ellipse cx="110" cy="150" rx="40" ry="30" fill="hsl({hue},40%,62%)"/>
 </g>
 <text x="196" y="40" font-size="34" fill="{COL['LONG'] if bias > 0 else COL['SHORT'] if bias < 0 else COL['WAIT']}">{'↗' if bias > 0 else '↙' if bias < 0 else '→'}</text>
 </svg></div>"""


@st.cache_data(ttl=600, show_spinner=False)
def crypto_data(product):
    from core.crypto import fetch_candles, crypto_features, run_crypto_mind
    from core.defi import fetch_defi, defi_signals
    try:
        sig = defi_signals(fetch_defi())
    except Exception:
        sig = None
    raw = fetch_candles(product, "1h", 2000)
    f = crypto_features(raw, product, sig)
    from core.crypto import crypto_config
    m, j = run_crypto_mind(raw, feat=f, cfg=crypto_config(capital()))
    return j, m.trades_frame(), m.blackbox_frame(), f.attrs.get("whale_feeds", []), sig is not None, m.explain()


@st.cache_data(ttl=300, show_spinner=False)
def portfolio_view():
    from core.crypto import ReadOnlyCoinbase
    return ReadOnlyCoinbase().balances()


def crypto_tab():
    cap = capital()
    st.caption(T("crypto_cap", eur=cap.eur, usd=cap.usd, risk=cap.risk_usd, stop=cap.stop_usd))
    product = st.radio(T("asset"), ["BTC-USD", "ETH-USD"], horizontal=True)
    try:
        j, trades, bb, feeds, has_defi, expl = crypto_data(product)
    except Exception as e:
        st.error(T("crypto_fail", e=e)); return
    last = j.iloc[-1]
    a, b, c, d = st.columns(4)
    a.metric(T("vjuice"), f"${last.juice:,.2f}", f"{last.juice / cap.usd - 1:+.1%}")
    b.metric(T("price"), f"{last.close:,.2f}")
    c.metric(T("oxygen") + (" (DeFi)" if has_defi else ""), f"{last.oxygen:.2f}")
    d.metric(T("action"), last.action)
    st.markdown(expl)
    st.caption(T("feeds", f=", ".join(feeds), d=T("active") if has_defi else T("unavailable")))
    st.subheader(T("trades_h"))
    st.dataframe(to_berlin(trades.tail(20).iloc[::-1]) if not trades.empty else pd.DataFrame({T("msg"): [T("no_trades_yet")]}), width="stretch")
    st.subheader(T("portfolio"))
    try:
        bal, tot = portfolio_view()
        st.dataframe(bal, width="stretch"); st.dataframe(tot, width="stretch")
    except Exception as e:
        st.info(T("no_key", e=type(e).__name__))


@st.cache_data(ttl=15, show_spinner=False)
def gold_minute():
    try:
        d = load("GC=F", "1m")
        return d.tail(3) if d is not None and len(d) else None
    except Exception:
        return None


@st.cache_data(ttl=8, show_spinner=False)
def crypto_ticker(product):
    import requests
    try:
        r = requests.get(f"https://api.exchange.coinbase.com/products/{product}/ticker", timeout=5,
                         headers={"User-Agent": "gold-phase-monitor-paper"})
        r.raise_for_status()
        return float(r.json()["price"])
    except Exception:
        try:
            pair = {"BTC-USD": "XBTUSD", "ETH-USD": "ETHUSD", "PAXG-USD": "PAXGUSD"}[product]
            js = requests.get("https://api.kraken.com/0/public/Ticker", params={"pair": pair}, timeout=5).json()
            return float(next(iter(js["result"].values()))["c"][0])
        except Exception:
            return None


@st.cache_data(ttl=8, show_spinner=False)
def paxg_price():
    """PAXG-USD — قیمت یگانه‌ی طلا (core.gold_price). باز بودن بازار را GC=F/ساعات CME تعیین می‌کند، نه PAXG."""
    from core import fastpath
    return fastpath.paxg_price()[0]          # Go fast path if running locally, else Python (Coinbase → Kraken)


@st.cache_data(ttl=10, show_spinner=False)
def gold_minutes_all():
    from core import gold_price
    try:
        return gold_price.candles("1m", 120)
    except Exception:
        return None


@st.cache_data(ttl=15, show_spinner=False)
def organism_decision_cached(raw, cross, interval, leverage, manual, wake_bar, minutes, _now_key):
    """تصمیم یگانه — یک بار در هر تازه‌سازی (کش ۱۵ ثانیه)."""
    from core.config import MANUAL_TEST_RR
    from core.decision import organism_decision
    cfg = capital_mind_config(capital(), leverage=float(leverage), bar_hours=INTERVAL_H[interval])
    dec, ctx = organism_decision(raw, cfg, pd.Timestamp.now(tz="UTC"), cross=cross, wake_bar=wake_bar,
                                 wake_interval_h=1 / 60 if wake_bar is not None else None,
                                 feed_delay_min=FEED_DELAY_MIN if wake_bar is not None else 0.0,
                                 minutes=minutes, rr=MANUAL_TEST_RR if manual else None)
    return dec, ctx["feat"], ctx["journal"]


def preview_svg(lean, conf, color, pulse_s):
    """عقربه‌ی طلایی: −۱ = SHORT (چپ)، +۱ = LONG (راست)؛ نبض با نزدیک شدن بسته شدن کندل تندتر می‌شود."""
    ang = float(np.clip(lean, -1, 1)) * 80
    return f"""<div style="display:flex;justify-content:center"><svg viewBox="0 0 240 150" width="300" height="188">
<style>.pulse{{transform-origin:120px 120px;animation:pl {pulse_s:.2f}s ease-in-out infinite}}
@keyframes pl{{0%,100%{{opacity:.35;transform:scale(1)}}50%{{opacity:.9;transform:scale(1.08)}}}}
.orb{{transform-origin:120px 120px;animation:orb 6s linear infinite}}@keyframes orb{{to{{transform:rotate(360deg)}}}}
.needle{{transform-origin:120px 120px;transform:rotate({ang:.1f}deg);transition:transform 1.2s}}</style>
<path d="M20 120 A100 100 0 0 1 220 120" stroke="#2a2f3a" stroke-width="16" fill="none"/>
<path d="M20 120 A100 100 0 0 1 95 25" stroke="{COL['SHORT']}" stroke-width="16" fill="none" opacity=".55"/>
<path d="M95 25 A100 100 0 0 1 145 25" stroke="{COL['WAIT']}" stroke-width="16" fill="none" opacity=".45"/>
<path d="M145 25 A100 100 0 0 1 220 120" stroke="{COL['LONG']}" stroke-width="16" fill="none" opacity=".55"/>
<circle class="pulse" cx="120" cy="120" r="30" fill="{color}" opacity=".4"/>
<g class="orb"><circle cx="120" cy="52" r="4" fill="{GOLD}"/></g>
<g class="needle"><line x1="120" y1="120" x2="120" y2="32" stroke="{GOLD}" stroke-width="5" stroke-linecap="round"/></g>
<circle cx="120" cy="120" r="10" fill="{GOLD}"/>
<text x="120" y="146" text-anchor="middle" font-size="15" fill="{color}" font-weight="700">{conf:.0%}</text>
<text x="18" y="146" font-size="12" fill="{COL['SHORT']}">SHORT</text><text x="222" y="146" text-anchor="end" font-size="12" fill="{COL['LONG']}">LONG</text>
</svg></div>"""


def gate_bar(label, value, thr, color):
    pct = float(np.clip(value / thr if thr else 0, 0, 1.2))
    return (f"<div style='margin:4px 0'><div style='display:flex;justify-content:space-between;font-size:.88em'>"
            f"<span>{label}</span><span>{value:.0%} / {thr:.0%}</span></div>"
            f"<div style='background:#2a2f3a;border-radius:6px;height:8px'><div style='width:{min(pct, 1) * 100:.0f}%;"
            f"height:8px;border-radius:6px;background:{color}'></div></div></div>")


RASOUL_TITLE = "با کمک رسول واحد"   # PLACEHOLDER — منتظر املای نهایی مالک؛ فقط همین ثابت را عوض کنید


def advice_box(dec):
    """«با کمک رسول واحد»: هیچ محاسبه‌ی جداگانه — فقط شیء Decision."""
    from core.decision import advice_key
    key = advice_key(dec)
    col = {"adv_long": COL["LONG"], "adv_short": COL["SHORT"]}.get(key, "#f59e0b")
    title = RASOUL_TITLE + ("" if L == "fa" else f" · {T('adv_title_tr')}")
    st.markdown(f"<div class='card' style='border:2px solid {col};background:{col}1a;text-align:center'>"
                f"<div style='font-size:.95em;opacity:.8'>{title}</div>"
                f"<div style='font-size:1.8em;font-weight:800;color:{col}'>{T(key)}</div>"
                f"<div style='font-size:.75em;opacity:.65'>{T('adv_caption')}</div></div>", unsafe_allow_html=True)


def next_decision_preview(dec, now):
    st.markdown(f"#### {T('pv_title')}")
    if not dec.provisional:
        st.caption(T("pv_none")); return
    left = max(pd.Timedelta(0), dec.bar_close - now)
    pulse = float(np.clip(left.total_seconds() / 900, 0.5, 3.0))
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown(preview_svg(dec.lean, dec.confidence, COL.get(dec.action, COL["WAIT"]), pulse), unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div class='card' style='border:1px dashed {GOLD}88'>"
                    f"<div style='font-size:1.5em;font-weight:800;color:{COL.get(dec.action, COL['WAIT'])}'>{dec.action} · {T('pv_badge')}</div>"
                    f"<div style='opacity:.85'>{T('pv_label', t=f'{dec.bar_close.tz_convert(BERLIN):%H:%M}', m=int(left.total_seconds() // 60), s=int(left.total_seconds() % 60), n=int((now - dec.timestamp).total_seconds() // 60))}</div>"
                    + gate_bar("LONG · " + T("pv_bull"), dec.P_bull, dec.dominance_thr, COL["LONG"])
                    + gate_bar("SHORT · " + T("pv_bear"), dec.P_bear, dec.dominance_thr, COL["SHORT"])
                    + gate_bar(T("pv_doubt"), dec.doubt, dec.max_doubt, COL["WAIT"])
                    + f"<div style='opacity:.75;font-size:.85em;margin-top:6px'>{dec.reason}</div></div>",
                    unsafe_allow_html=True)


@st.fragment(run_every=timedelta(seconds=15) if live else None)
def live_panel():
    """پنل زنده: همه‌چیز از یک شیء Decision (core.decision) — وضعیت، خرس، کارت، پیش‌نمایش، رسول واحد، حساب کاغذی."""
    from core.decision import live_signal, signal_card, status_key
    from core.live_account import LivePaperAccount
    now = pd.Timestamp.now(tz="UTC")
    mins = gold_minute()                                   # GC=F: فقط مرجع آتی + نشان «تأخیر خوراک»
    try:
        raw, cross = get_data(interval)
        # باز/بسته از تقویم CME (اصلی) + تازگی کندل‌های PAXG؛ GC=F هرگز وضعیت را «بسته» نمی‌کند
        dec, feat, j = organism_decision_cached(raw, cross, interval, leverage, manual, None, gold_minutes_all(),
                                                now.floor("15s"))
    except Exception as e:
        st.error(T("data_fail", e=e)); return
    cap = capital()
    conf_dec = dec.confirmed or dec
    awake = not dec.asleep
    cfg = capital_mind_config(cap, leverage=float(leverage), bar_hours=INTERVAL_H[interval])
    from core.config import MANUAL_TEST_RISK_EUR, MANUAL_TEST_RR
    acc = LivePaperAccount("gold", cap.usd, cfg, fixed_risk_usd=MANUAL_TEST_RISK_EUR * cap.rate if manual else None,
                           rr=MANUAL_TEST_RR if manual else None)
    acc.update(feat, j, awake, signal=live_signal(dec))
    paxg = paxg_price()
    fut = float(mins["Close"].iloc[-1]) if mins is not None else None      # GC=F فقط مرجع
    price = paxg if paxg else dec.price
    prev = st.session_state.get("paxg", price) or price
    pos = acc.state["position"]
    unreal = pos["qty"] * (price - pos["entry"]) * pos["direction"] - pos["fees"] - pos["funding"] if pos else 0.0
    lt = acc.trades_frame()
    from core.live_account import live_feeling
    feeling = live_feeling(lt)                 # فقط حساب زنده؛ بازپخش تاریخی هرگز حال خرس را تعیین نمی‌کند
    if feeling == "none":
        feeling = "neutral"
    hue = {"happy": 125, "sad": 0, "neutral": 210}[feeling]
    breath = float(np.clip(4.0 / (max(dec.vol_ratio, 0.2) * max(dec.oxygen, 0.2) ** 0.5), 0.6, 6.0))
    if feeling == "sad":
        breath = max(breath, 5.5)
    if not awake:
        breath = 7.0
    mood = {"open": "👀", "closed": "💤", "awaiting": "⏳", "stale": "💤"}[dec.market_state]
    mood += {"happy": " · " + T("mood_happy"), "sad": " · " + T("mood_sad"), "neutral": " · " + T("mood_none")}[feeling]
    colr = {"open": "#22c55e", "closed": "#64748b", "awaiting": "#f59e0b", "stale": "#f59e0b"}[dec.market_state]
    icon = {"open": "🟢", "closed": "⚫", "awaiting": "🟡", "stale": "🟡"}[dec.market_state]
    if awake and dec.provisional:
        left = max(pd.Timedelta(0), dec.bar_close - now)
        reason_txt = T("awake_wait", iv=interval, t=f"{dec.bar_close.tz_convert(BERLIN):%H:%M}",
                       m=int(left.total_seconds() // 60), s=int(left.total_seconds() % 60))
    elif awake and any(k in conf_dec.reason for k in ("بسته", "خواب", "کهنه")):
        reason_txt = T("awake_wait", iv=interval, t=f"{(conf_dec.bar_close + pd.Timedelta(hours=INTERVAL_H[interval])).tz_convert(BERLIN):%H:%M}",
                       m=int(max(0, (conf_dec.bar_close + pd.Timedelta(hours=INTERVAL_H[interval]) - now).total_seconds()) // 60), s=0)
    else:
        reason_txt = conf_dec.reason if awake else T("no_sig_sleep")
    shown = live_signal(dec)
    # ===== ۱) وضعیت (یک شیء بازار) =====
    st.markdown(f"<div class='card' style='border:2px solid {colr};background:{colr}1a'>"
                f"<div style='font-size:1.4em;font-weight:800;color:{colr}'>{icon} {T(status_key(dec))}</div>"
                f"<div>{T('action_now')}: <b style='color:{COL[shown]}'>{shown}</b> — {reason_txt}</div>"
                f"<div style='opacity:.7;font-size:.85em'>{T('last_candle', t=f'{conf_dec.timestamp.tz_convert(BERLIN):%Y-%m-%d %H:%M}', now=f'{now.tz_convert(BERLIN):%H:%M:%S}')}</div></div>",
                unsafe_allow_html=True)
    # ===== ۱ب) معاملات کاغذی خودکار (از همان Decision) =====
    auto_paper_panel(acc, price, cap, now)
    # ===== ۲) با کمک رسول واحد =====
    advice_box(dec)
    # ===== ۳) کارت تصمیم (از Decision.confirmed) =====
    card = signal_card(dec)
    if card:
        col = COL[card["action"]]
        lv = T("sig_levels", e=card["entry"], s=card["stop"], t=card["target"])
        meta = T("sig_meta", c=card["confidence"], iv=interval, t=f"{card['issued'].tz_convert(BERLIN):%Y-%m-%d %H:%M}",
                 x=f"{card['expires'].tz_convert(BERLIN):%H:%M}")
        st.markdown(f"<div class='card' style='border:3px solid {col};background:{col}1f'>"
                    f"<div style='font-size:2em;font-weight:800;color:{col}'>{card['action']}</div>"
                    f"<div>{lv}</div><div style='opacity:.85'>{meta}</div></div>", unsafe_allow_html=True)
    # ===== ۴) قیمت (فقط PAXG) و حساب کاغذی =====
    a, b, c = st.columns(3)
    a.metric(T("gold_main"), f"{price:,.2f}", f"{price - prev:+.2f}")
    b.metric(T("live_acc"), f"{acc.equity + unreal:,.2f}", f"{(acc.equity + unreal) / acc.state['start_equity'] - 1:+.2%}")
    c.metric(T("open_pnl"), f"{unreal:+,.2f}")
    st.session_state["paxg"] = paxg
    # ===== ۵) خرس (SVG جدا) + متن‌ها در ستون جدا؛ روی موبایل زیر هم =====
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown(creature_svg(breath, hue, "", feeling, dec.bias, asleep=dec.asleep), unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div class='card' style='border:1px solid #ffffff1f'>{T('breath', s=breath)} · {mood}</div>",
                    unsafe_allow_html=True)
        ev = acc.state.get("last_event") or {}
        if pos:
            txt, col = T("ex_long" if pos["direction"] > 0 else "ex_short"), COL["LONG" if pos["direction"] > 0 else "SHORT"]
        elif ev.get("kind") == "closed" and pd.Timestamp(ev["time"]) >= conf_dec.timestamp:
            txt, col = T("ex_closed", r={"target": "TP", "stop": "SL", "gap_stop": "SL", "liquidation": "LIQ", "time": "⏱"}.get(ev["reason"], ev["reason"]),
                         p=ev["pnl"]), GOLD
        else:
            txt, col = T("ex_next", a=T({"LONG": "a_long", "SHORT": "a_short"}.get(dec.action, "a_wait"))), COL.get(dec.action, COL["WAIT"])
        st.markdown(f"<div class='card' style='text-align:center;font-size:1.35em;font-weight:800;color:{col};border:2px solid {col}55'>"
                    f"{txt}<div style='font-size:.55em;font-weight:400;opacity:.7'>{T('paper_only')}"
                    f"{' · ' + T('manual_on') if manual else ''}</div></div>", unsafe_allow_html=True)
    # ===== ۶) پیش‌نمایش =====
    if awake:
        next_decision_preview(dec, now)
    if cap.warning:
        st.warning(cap.warning)
    warning_box()
    # ===== جزئیات (جمع‌شده) =====
    n_live = len(lt); win_live = float((lt["pnl"] > 0).mean()) if n_live else 0.0
    pnl_live = float(lt["pnl"].sum()) if n_live else 0.0
    replay_ret = float(j["juice"].iloc[-1] / cap.usd - 1)
    gc_age = (now - mins.index[-1]).total_seconds() / 60 if mins is not None else None
    pm = gold_minutes_all()
    pm_age = (now - pm.index[-1]).total_seconds() / 60 if pm is not None and len(pm) else None
    bar_age = (now - conf_dec.bar_close).total_seconds() / 60
    fmt = lambda v: "—" if v is None else f"{v:.0f} min"
    delayed = gc_age is not None and gc_age > 20
    with st.expander(T("details")):
        st.markdown(f"<div class='card' style='padding:4px'>{T('track', n=n_live, w=win_live, p=pnl_live, r=replay_ret)}</div>",
                    unsafe_allow_html=True)
        st.caption(dec.market_reason)
        st.caption(T("feed_ages", p=fmt(pm_age), b=fmt(bar_age), g=fmt(gc_age)) + (f" · 🟠 {T('gc_delayed')}" if delayed else ""))
        if fut and paxg:
            st.caption(T("fut_ref", f=fut, d=fut - paxg, p=fut / paxg - 1))
        st.caption(T("cap_line", eur=cap.eur, usd=cap.usd, risk=cap.risk_usd, stop=cap.stop_usd, rate=cap.rate, src=cap.source,
                     ts=f"{pd.Timestamp(cap.timestamp).tz_convert(BERLIN):%Y-%m-%d %H:%M}"))
        x, y, z = st.columns(3)
        btc, eth = crypto_ticker("BTC-USD"), crypto_ticker("ETH-USD")
        x.metric("BTC", f"{btc:,.0f}" if btc else "—"); y.metric("ETH", f"{eth:,.1f}" if eth else "—")
        z.metric(T("live_trades"), len(lt))
        if conf_dec.reason and card:
            st.caption(conf_dec.reason)
        if L != "fa":
            st.caption(T("note_reasons"))
        if not lt.empty:
            st.dataframe(to_berlin(lt.iloc[::-1]), width="stretch")
    if not awake:
        st.info(T("asleep_info"))


def auto_paper_panel(acc, price, cap, now):
    """«معاملات کاغذی خودکار»: کارت موفقیت + پوزیشن باز با P&L شناور در برابر PAXG زنده + تاریخچه + CSV."""
    stt = acc.stats(price, start_eur=cap.eur, rate=cap.rate)
    icon = {"bull": "🐂", "bear": "🐻", "neutral": "⚖️"}[stt["mood"]]
    mcol = {"bull": COL["LONG"], "bear": COL["SHORT"], "neutral": COL["WAIT"]}[stt["mood"]]
    sign = T("grown") if stt["change"] >= 0 else T("shrunk")
    pct = lambda v: "—" if v is None else f"{v:.0%}"
    money = lambda v: "—" if v is None else f"{v:+,.2f} $"
    st.markdown(f"### {T('auto_h')}")
    st.markdown(
        f"<div class='card' style='border:2px solid {mcol};background:{mcol}14'>"
        f"<div style='display:flex;align-items:center;gap:.6em'><span style='font-size:2.4em'>{icon}</span>"
        f"<div><div style='font-size:1.25em;font-weight:800;color:{mcol}'>{T('mood_' + stt['mood'])}</div>"
        f"<div>{T('start_cap', eur=cap.eur, usd=stt['start_usd'], rate=cap.rate)}</div>"
        f"<div>{T('now_eq', e=stt['equity'])} · <b style='color:{mcol}'>{sign} {stt['change']:+,.2f} $ ({stt['change_pct']:+.2%})</b></div>"
        f"</div></div></div>", unsafe_allow_html=True)
    a, b, c, d = st.columns(4)
    a.metric(T("tot_trades"), stt["n"], f"{stt['wins']}✓ / {stt['losses']}✗", delta_color="off")
    b.metric(T("win_rate"), pct(stt["win_rate"]))
    c.metric(T("realized"), f"{stt['realized']:+,.2f} $")
    d.metric(T("max_dd"), f"{stt['max_dd']:.1%}")
    st.caption(T("avg_wl", w=money(stt["avg_win"]), l=money(stt["avg_loss"])) + " · " + T("sample_n", n=stt["n"]))
    pos = acc.state["position"]
    if pos:
        side = "LONG" if pos["direction"] > 0 else "SHORT"
        fl = stt["floating"]
        st.markdown(f"<div class='card' style='border:2px solid {COL[side]}'><b style='color:{COL[side]}'>{T('open_pos')}: {side}</b> · "
                    f"{T('entry')} {pos['entry']:,.2f} · SL {pos['stop']:,.2f} · TP {pos['target']:,.2f} · PAXG {price:,.2f} · "
                    f"<b style='color:{COL['LONG'] if fl >= 0 else COL['SHORT']}'>{T('floating')} {fl:+,.2f} $</b>"
                    f"<div style='opacity:.7;font-size:.85em'>{T('opened_at')} {pd.Timestamp(pos['open_time']).tz_convert(BERLIN):%Y-%m-%d %H:%M}"
                    f" · {T('conf')} {pct((acc.state.get('open_meta') or {}).get('confidence'))}</div></div>", unsafe_allow_html=True)
    else:
        st.caption(T("no_open_pos") + (f" · {T('pending_entry')}" if acc.state.get("pending") else ""))
    with st.expander(T("hist_h", n=stt["n"]), expanded=False):
        lt = acc.trades_frame()
        if lt.empty:
            st.info(T("no_auto_trades"))
        else:
            show = lt.iloc[::-1].copy()
            for k in ("entry_time", "exit_time"):
                show[k] = pd.to_datetime(show[k], utc=True).dt.tz_convert(BERLIN).dt.strftime("%Y-%m-%d %H:%M")
            st.dataframe(show, width="stretch", hide_index=True)
        x, y = st.columns(2)
        x.download_button(T("dl_auto"), acc.to_csv(), "auto_paper_trades.csv", "text/csv", key="dl_auto")
        up = y.file_uploader(T("ul_auto"), type="csv", key="ul_auto")
        if up is not None and st.session_state.get("ul_done") != up.file_id:
            added = acc.import_csv(up.getvalue())
            st.session_state["ul_done"] = up.file_id
            st.success(T("ul_ok", n=added))
        st.caption(T("ephemeral"))


@st.fragment(run_every=timedelta(seconds=300) if live else None)   # بخش سنگین: هر ۵ دقیقه
def dashboard():
    try:
        raw, cross = get_data(interval)
    except Exception as e:
        st.error(T("data_fail", e=e)); return
    with st.spinner(T("thinking")):
        feat, j, trades, bb, explain, events, strat, extra = run_mind(raw, cross, interval, leverage)
    last = j.iloc[-1]
    cap = capital()
    with st.expander(T("replay_h"), expanded=False):
        st.caption(T("replay_cap", a=to_berlin(j.iloc[[0]]).index[0], b=to_berlin(j.iloc[[-1]]).index[0], usd=cap.usd))
        a, b, c, d, e = st.columns(5)
        a.metric(T("replay_juice"), f"{last.juice:,.2f}", f"{last.juice / cap.usd - 1:+.1%}")
        b.metric(T("replay_trades"), len(trades))
        c.metric(T("regime"), f"{regime(last.regime, L)} {max(last.P_bull, last.P_bear, last.P_range):.0%}")
        d.metric(T("strategy"), last.strategy)
        e.metric(T("energy"), f"{extra['energy']:,.2f} $", T("energy_delta", p=-extra['energy'] / cap.usd), delta_color="off")
        st.caption(T("energy_note", f=ENERGY_FEE_PCT, m=T("margin") if ENERGY_FEE_MODE == "margin" else T("notional"), r=2 * ENERGY_FEE_PCT))
        st.markdown(f"**{T('explain')}**")
        st.markdown(explain)

    t1, t2, t3, t6, t4, t5, t7 = st.tabs([T("tab_signals"), T("tab_trades"), T("tab_learning"), T("tab_ledger"), T("tab_memory"),
                                          T("tab_crypto"), T("tab_colony")])
    with t7:
        colony_tab(); credit_footer()
    with t5:
        crypto_tab(); credit_footer()
    with t1:
        st.subheader(T("sig_hist_h"))
        feed = j[j["action"] != "WAIT"].tail(20)[["close", "action", "strategy", "doubt", "reason"]]
        st.dataframe(to_berlin(feed.iloc[::-1]), width="stretch")
        ch = j.tail(200)
        fig = go.Figure(go.Scatter(x=ch.index, y=ch.close, name=T("price"), line=dict(color=GOLD)))
        for act, col, sym in (("LONG", COL["LONG"], "triangle-up"), ("SHORT", COL["SHORT"], "triangle-down")):
            p = ch[ch.action == act]
            fig.add_trace(go.Scatter(x=p.index, y=p.close, mode="markers", name=act, marker=dict(color=col, size=10, symbol=sym)))
        fig.update_layout(template="plotly_dark", height=320, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width="stretch")
        credit_footer()
    with t2:
        if trades.empty:
            st.info(T("no_trades"))
        else:
            w = (trades.pnl > 0).mean()
            x, y, z = st.columns(3)
            x.metric(T("win_rate", l=leverage), f"{w:.0%}"); y.metric(T("mean_r"), f"{trades.R.mean():+.2f}")
            z.metric(T("liquidated"), int((trades.reason == "liquidation").sum()))
            st.subheader(T("trades_h"))
            st.dataframe(to_berlin(trades.tail(30).iloc[::-1]), width="stretch")
        credit_footer()
    with t3:
        fig = go.Figure(go.Scatter(x=j.index, y=j.juice, name=T("juice"), line=dict(color=GOLD)))
        fig.update_layout(template="plotly_dark", height=250, margin=dict(l=10, r=10, t=30, b=10), title=T("juice_curve"))
        st.plotly_chart(fig, width="stretch")
        fig = go.Figure(go.Scatter(x=j.index, y=j.trust, name=T("trust"), line=dict(color="#cc88ff")))
        fig.update_layout(template="plotly_dark", height=220, margin=dict(l=10, r=10, t=30, b=10), title=T("trust"))
        st.plotly_chart(fig, width="stretch")
        with st.spinner(T("arena_spin", n=pop)):
            arena, cut = run_arena_cached(raw, cross, interval, pop)
        fig = go.Figure()
        rows = []
        for lev, r in arena.items():
            h = r["history"]
            fig.add_trace(go.Scatter(x=h.generation, y=h.survival, mode="lines+markers", name=f"{T('survival')} {lev:g}x"))
            dfl = r["deflation"]
            rows.append({T("tier"): f"{lev:g}x", T("c_surv"): dfl["champ_oos_survival"],
                         T("c_liq"): dfl["champ_oos_liquidated"], T("c_ret"): dfl["champ_oos_median_ret"],
                         T("r_ret"): dfl["random_oos_median_ret"], T("pctile"): dfl["champ_pctile_vs_random"]})
        fig.update_layout(template="plotly_dark", height=260, margin=dict(l=10, r=10, t=30, b=10),
                          title=T("survival_curve"), xaxis_title=T("generation"), yaxis_title=T("surv_share"))
        st.plotly_chart(fig, width="stretch")
        st.caption(T("oos_note", c=cut))
        st.dataframe(pd.DataFrame(rows).round(3), width="stretch")
        st.dataframe(pd.DataFrame(strat).T.rename(columns={"score": T("score"), "n": T("count"), "demoted_until": T("demoted")}),
                     width="stretch")
        credit_footer()
    with t4:
        st.subheader(T("blackbox"))
        st.dataframe(bb.tail(30).iloc[::-1] if not bb.empty else pd.DataFrame({T("msg"): [T("empty")]}), width="stretch")
        st.subheader(T("journal"))
        st.dataframe(to_berlin(j.tail(50).iloc[::-1][["action", "reason", "intuition", "evidence", "doubt", "trust", "juice"]]), width="stretch")
        st.download_button(T("dl_journal"), j.to_csv().encode("utf-8"), "journal.csv", "text/csv")
        st.subheader(T("events"))
        st.write([e[1] for e in events[-15:]])
        credit_footer()
    with t6:
        st.subheader(T("ledger_h"))
        led = extra["ledger"]
        if led.empty:
            st.info(T("ledger_empty"))
        else:
            from core.ledger import summarize
            st.caption(T("ledger_note"))
            st.markdown(f"**{T('per_model')}**")
            st.dataframe(summarize(led).round(3), width="stretch")
            show = led.tail(60).iloc[::-1][["time", "option", "chosen", "suggested", "confidence", "model", "tier", "timeframe",
                                            "exit_time", "exit_reason", "pct", "juice", "energy"]]
            st.dataframe(show, width="stretch")
            st.download_button(T("dl_ledger"), led.to_csv(index=False).encode("utf-8"), "decision_ledger.csv", "text/csv")
            st.caption(T("regret", v=extra["gate_regret"]))
        credit_footer()


def colony_tab():
    """Memory monitor of the local organism colony (reads the supervisor's status file; paper only)."""
    from core.colony import COLONY_DIR
    st.subheader(T("colony_h"))
    st.caption(T("colony_note"))
    p = COLONY_DIR / "colony_status.json"
    if not p.exists():
        st.info(T("colony_empty")); return
    d = json.loads(p.read_text())
    inst = pd.DataFrame(d.get("instances", []))
    a, b, c = st.columns(3)
    a.metric(T("colony_n"), f"{d.get('n', 0)} / {d.get('cap', 21)}")
    b.metric(T("colony_rss"), f"{d.get('total_rss_mb', 0):,.0f} MB")
    c.metric(T("colony_leaks"), int(inst["leak"].sum()) if "leak" in inst else 0)
    if not inst.empty:
        cols = [k for k in ("id", "pid", "alive", "cycle", "mean_ret", "trades", "rss_mb", "peak_mb", "trend_mb_min", "leak") if k in inst]
        st.dataframe(inst[cols], width="stretch")
    st.write([e["e"] for e in d.get("events", [])[-15:]])


live_panel()
dashboard()
st.sidebar.markdown("---")
st.sidebar.caption(CREDIT[L])
credit_footer()
