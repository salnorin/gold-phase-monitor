# app.py — داشبورد موجود زنده (فقط شبیه‌سازی کاغذی؛ هیچ سفارش واقعی)
from datetime import timedelta
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.arena import run_arena
from core.mind import FA, Mind, MindConfig, capital_mind_config
from core.fx import paper_capital
from core.market_hours import FEED_DELAY_MIN, status_detail
from core.organism import BiologicalOrganism
from core.research import load

st.set_page_config(page_title="ارگانیسم طلا — موجود زنده", layout="wide", initial_sidebar_state="collapsed")
st.markdown("<style>section.main .stMarkdown, [data-testid='stMainBlockContainer'] .stMarkdown {direction: rtl; text-align: right;}</style>", unsafe_allow_html=True)
st.title("🐻 ارگانیسم زنده‌ی طلا (XAU/USD)")
st.caption("⚠️ فقط شبیه‌سازی کاغذی و آموزشی — بدون سفارش واقعی و بدون کلید صرافی. توصیه‌ی مالی نیست.")

BERLIN = "Europe/Berlin"
CREDIT_FA = "این ارگانیسم توسط سالار خانبابا و با همفکری گروک بات خلق شده است"


def credit_footer():
    st.markdown(f"<div style='text-align:center;direction:rtl;opacity:.75;margin-top:24px;font-size:.95em'>{CREDIT_FA}</div>",
                unsafe_allow_html=True)


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
interval = st.sidebar.selectbox("بازه‌ی کندل", list(INTERVAL_H), index=0)
leverage = st.sidebar.select_slider("اهرم شبیه‌سازی", options=[1, 5, 10, 20], value=20)
pop = st.sidebar.select_slider("جمعیت میدان تکامل", options=[500, 2000, 10000], value=2000)
live = st.sidebar.checkbox("🔴 به‌روزرسانی خودکار (پنل زنده هر ۱۵ ثانیه، بقیه هر ۵ دقیقه)", value=True)


@st.cache_data(ttl=240, show_spinner=False)
def get_data(interval):
    raw = load("GC=F", interval)
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
    return feat, j, m.trades_frame(), m.blackbox_frame(), m.explain(), m.events, m.strat


@st.cache_data(ttl=3600, show_spinner=False)
def run_arena_cached(raw, cross, interval, pop):
    res, cut = run_arena(raw, cross, INTERVAL_H[interval], pop=pop, generations=6)
    return {lev: dict(history=r["history"], deflation=r["deflation"]) for lev, r in res.items()}, cut


MOUTH = {"happy": "M96 106 Q110 122 124 106", "sad": "M98 116 Q110 104 122 116", "neutral": "M100 108 Q110 116 120 108"}


WARNING_3L = ("⚠️ سیگنال کاغذی و اثبات‌نشده است؛ توصیه‌ی مالی نیست؛ اهرم می‌تواند کل حساب را از بین ببرد. · "
              "Unproven paper signal, not financial advice; leverage can wipe out the account. · "
              "Unbewiesenes Papiersignal, keine Finanzberatung; Hebel kann das gesamte Konto vernichten.")


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
 <text x="196" y="40" font-size="34" fill="{'#00cc66' if bias > 0 else '#ff3366' if bias < 0 else '#aaa'}">{'↗' if bias > 0 else '↙' if bias < 0 else '→'}</text>
 <text x="110" y="196" text-anchor="middle" font-size="13" fill="#ddd">{label}</text>
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
    st.caption(f"فقط کاغذی: سقف مجازی {cap.eur:,.2f} € ≈ {cap.usd:,.2f} $، حداکثر ریسک هر معامله {cap.risk_usd:,.2f} $ (۱٪)، "
               f"توقف خودکار در {cap.stop_usd:,.2f} $ (۷۰٪). بازار ۲۴/۷. هیچ سفارش واقعی.")
    product = st.radio("دارایی", ["BTC-USD", "ETH-USD"], horizontal=True)
    try:
        j, trades, bb, feeds, has_defi, expl = crypto_data(product)
    except Exception as e:
        st.error(f"داده‌ی کریپتو در دسترس نیست: {e}"); return
    last = j.iloc[-1]
    a, b, c, d = st.columns(4)
    a.metric("🧃 آب‌میوه مجازی", f"${last.juice:,.2f}", f"{last.juice / cap.usd - 1:+.1%}")
    b.metric("قیمت", f"{last.close:,.2f}")
    c.metric("🫁 اکسیژن (با DeFi)" if has_defi else "🫁 اکسیژن", f"{last.oxygen:.2f}")
    d.metric("اقدام", last.action)
    st.markdown(expl)
    st.caption(f"خوراک نهنگ: {', '.join(feeds)} | DefiLlama: {'فعال' if has_defi else 'در دسترس نیست'}")
    st.subheader("📜 تاریخچه‌ی معاملات کاغذی (وقت برلین)")
    st.dataframe(to_berlin(trades.tail(20).iloc[::-1]) if not trades.empty else pd.DataFrame({"پیام": ["هنوز معامله‌ای نیست"]}), width="stretch")
    st.subheader("پرتفوی واقعی (فقط‌خواندنی)")
    try:
        bal, tot = portfolio_view()
        st.dataframe(bal, width="stretch"); st.dataframe(tot, width="stretch")
    except Exception as e:
        st.info(f"کلید فقط‌خواندنی پیدا نشد یا اتصال ناموفق بود ({type(e).__name__}).")


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
            pair = {"BTC-USD": "XBTUSD", "ETH-USD": "ETHUSD"}[product]
            js = requests.get("https://api.kraken.com/0/public/Ticker", params={"pair": pair}, timeout=5).json()
            return float(next(iter(js["result"].values()))["c"][0])
        except Exception:
            return None


@st.fragment(run_every=timedelta(seconds=15) if live else None)
def live_panel():
    """پنل زنده (هر ۱۵ ثانیه، بدون بارگذاری کل صفحه): وضعیت بازار، خرس، قیمت، حساب کاغذی زنده، آخرین سیگنال."""
    from core.live_account import LivePaperAccount
    try:
        raw, cross = get_data(interval)
        feat, j, trades, bb, explain, events, strat = run_mind(raw, cross, interval, leverage)
    except Exception as e:
        st.error(f"دریافت داده ناموفق بود: {e}"); return
    cap = capital()
    now = pd.Timestamp.now(tz="UTC")
    mins = gold_minute()
    fast = mins.index[-1] if mins is not None else None
    last = j.iloc[-1]
    last_bar = max([t for t in (j.index[-1], fast) if t is not None])
    use_fast = fast is not None and last_bar == fast
    state, state_reason = status_detail(last_bar, now, 1 / 60 if use_fast else INTERVAL_H[interval],
                                        feed_delay_min=FEED_DELAY_MIN if use_fast else 0.0)
    if state == "open" and j.index[-1] < last_bar - pd.Timedelta(minutes=int(INTERVAL_H[interval] * 60)):
        state_reason += f" — بیدار؛ منتظر بسته شدن اولین کندل {interval} برای سیگنال"
    awake = state == "open"
    # حساب کاغذی زنده (از لحظه‌ی ایجاد، روی دیسک)
    cfg = capital_mind_config(cap, leverage=float(leverage), bar_hours=INTERVAL_H[interval])
    acc = LivePaperAccount("gold", cap.usd, cfg)
    acc.update(feat, j, awake)
    price = float(mins["Close"].iloc[-1]) if mins is not None else float(last.close)
    prev = float(mins["Close"].iloc[-2]) if mins is not None and len(mins) > 1 else price
    pos = acc.state["position"]
    unreal = 0.0
    if pos:
        unreal = pos["qty"] * (price - pos["entry"]) * pos["direction"] - pos["fees"] - pos["funding"]
    lt = acc.trades_frame()
    feeling = "neutral"
    if not lt.empty:
        feeling = "happy" if lt.iloc[-1]["pnl"] > 0 else "sad"
    elif not trades.empty and "pnl" in trades and trades["pnl"].notna().any():
        feeling = "happy" if trades["pnl"].dropna().iloc[-1] > 0 else "sad"
    hue = {"happy": 125, "sad": 0, "neutral": 210}[feeling]
    breath = float(np.clip(4.0 / (max(last.vol_ratio, 0.2) * max(last.oxygen, 0.2) ** 0.5), 0.6, 6.0))
    if feeling == "sad":
        breath = max(breath, 5.5)
    if not awake:
        breath = 7.0
    mood = {"closed": "خواب — بازار بسته 💤", "awaiting": "در حال بیدار شدن ⏳", "stale": "منتظر داده 💤"}.get(state, "بیدار 👀")
    mood += {"happy": " · معامله‌ی آخر: برد 😊", "sad": " · معامله‌ی آخر: باخت 🤒", "neutral": ""}[feeling]
    badge = {"open": ("#00cc66", "🟢 بازار باز — بیدار"), "closed": ("#888888", "⚫ بازار بسته"),
             "awaiting": ("#ffaa00", "🟡 بازار باز — منتظر اولین کندل بسته‌شده"), "stale": ("#ffaa00", "🟡 داده‌ی کهنه")}[state]
    live_action = last.action if awake else "WAIT"
    st.markdown(f"<div style='direction:rtl;border:3px solid {badge[0]};border-radius:16px;padding:14px;margin-bottom:12px;background:{badge[0]}22'>"
                f"<div style='font-size:1.6em;font-weight:bold;color:{badge[0]}'>وضعیت فعلی: {badge[1]}</div>"
                f"<div>{state_reason}</div>"
                f"<div>آخرین کندل بسته‌شده: {pd.Timestamp(last_bar).tz_convert(BERLIN):%Y-%m-%d %H:%M} (وقت برلین) · "
                f"اکنون: {now.tz_convert(BERLIN):%H:%M:%S} · داده‌ی طلای Yahoo حدود ۱۰ دقیقه تأخیر دارد</div>"
                f"<div>اقدام فعلی: <b>{live_action}</b> — {last.reason if awake else 'بدون سیگنال تا رسیدن کندل تازه'}</div></div>",
                unsafe_allow_html=True)
    if cap.warning:
        st.warning(cap.warning)
    c1, c2 = st.columns([1, 2])
    with c1:
        bias = int(np.sign(last.evidence)) if awake and abs(last.evidence) >= 0.15 else 0
        st.markdown(creature_svg(breath, hue, f"تنفس هر {breath:.1f} ثانیه · {mood}", feeling, bias, asleep=not awake),
                    unsafe_allow_html=True)
    with c2:
        a, b, c = st.columns(3)
        a.metric("قیمت طلا (۱ دقیقه)", f"{price:,.2f}", f"{price - prev:+.2f}")
        b.metric("💼 حساب کاغذی زنده ($)", f"{acc.equity + unreal:,.2f}", f"{(acc.equity + unreal) / acc.state['start_equity'] - 1:+.2%}")
        c.metric("سود/زیان باز", f"{unreal:+,.2f}" if pos else "—", f"{unreal:+.2f}" if pos else None)
        x, y, z = st.columns(3)
        btc, eth = crypto_ticker("BTC-USD"), crypto_ticker("ETH-USD")
        old_btc, old_eth = st.session_state.get("btc", btc), st.session_state.get("eth", eth)
        x.metric("BTC", f"{btc:,.0f}" if btc else "—", f"{btc - old_btc:+.1f}" if btc and old_btc else None)
        y.metric("ETH", f"{eth:,.1f}" if eth else "—", f"{eth - old_eth:+.2f}" if eth and old_eth else None)
        st.session_state["btc"], st.session_state["eth"] = btc, eth
        z.metric("معاملات زنده", len(lt))
        st.caption(f"💶 سقف مجازی: {cap.eur:,.2f} € ≈ {cap.usd:,.2f} $ · ریسک هر معامله ≤ {cap.risk_usd:,.2f} $ (۱٪) · "
                   f"توقف خودکار: {cap.stop_usd:,.2f} $ (۷۰٪) · نرخ EUR/USD {cap.rate:.4f} "
                   f"({cap.source}، {pd.Timestamp(cap.timestamp).tz_convert(BERLIN):%Y-%m-%d %H:%M} برلین) · "
                   f"حساب زنده از {pd.Timestamp(acc.state['created']).tz_convert(BERLIN):%Y-%m-%d %H:%M} برلین")
    # ---------- کارت سیگنال (فقط وقتی دروازه‌ی اطمینان بالا باز است) ----------
    oc = cfg.organism
    bar_end = j.index[-1] + pd.Timedelta(hours=INTERVAL_H[interval])
    conf = float(max(last.P_bull, last.P_bear, last.P_range) * (1 - last.doubt))
    if awake and last.action in ("LONG", "SHORT"):
        d = 1 if last.action == "LONG" else -1
        atr = float(feat["ATR"].iloc[-1]); entry = float(last.close)
        col = "#00cc66" if d > 0 else "#ff3366"
        st.markdown(f"<div style='direction:rtl;border:4px solid {col};border-radius:18px;padding:16px;background:{col}22'>"
                    f"<div style='font-size:2.4em;font-weight:bold;color:{col}'>{last.action}</div>"
                    f"<div>ورود ≈ {entry:,.2f} · استاپ {entry - d * atr * oc.stop_atr_mult:,.2f} · تارگت {entry + d * atr * oc.target_atr_mult:,.2f}</div>"
                    f"<div>اطمینان {conf:.0%} · بازه {interval} · صادرشده {bar_end.tz_convert(BERLIN):%Y-%m-%d %H:%M} برلین · "
                    f"انقضا {(bar_end + pd.Timedelta(hours=INTERVAL_H[interval])).tz_convert(BERLIN):%H:%M}</div>"
                    f"<div>{last.reason}</div></div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div style='direction:rtl;border:2px solid #888;border-radius:18px;padding:12px'>"
                    f"<span style='font-size:1.8em;font-weight:bold;color:#aaa'>WAIT</span> — "
                    f"{last.reason if awake else 'ارگانیسم خواب است'}</div>", unsafe_allow_html=True)
    # ---------- کارنامه‌ی تأییدشده ----------
    n_live = len(lt); win_live = float((lt["pnl"] > 0).mean()) if n_live else 0.0
    pnl_live = float(lt["pnl"].sum()) if n_live else 0.0
    replay_ret = float(j["juice"].iloc[-1] / cap.usd - 1)
    st.markdown(f"<div style='direction:rtl;opacity:.9'>📊 کارنامه‌ی حساب کاغذی زنده: {n_live} سیگنال · نرخ برد {win_live:.0%} · "
                f"سود/زیان {pnl_live:+,.2f} $ · بازپخش تاریخی: {replay_ret:+.1%}</div>", unsafe_allow_html=True)
    st.warning(WARNING_3L)
    if not awake:
        st.info("💤 ارگانیسم خواب است و هیچ سیگنال یا معامله‌ی جدیدی نمی‌دهد. جدول‌های پایین «تاریخچه»اند، نه سیگنال زنده.")
    if not lt.empty:
        with st.expander("📒 معاملات حساب کاغذی زنده (وقت برلین)"):
            st.dataframe(to_berlin(lt.iloc[::-1]), width="stretch")


@st.fragment(run_every=timedelta(seconds=300) if live else None)   # بخش سنگین: هر ۵ دقیقه
def dashboard():
    try:
        raw, cross = get_data(interval)
    except Exception as e:
        st.error(f"دریافت داده ناموفق بود: {e}"); return
    with st.spinner("ذهن در حال مرور تاریخچه..."):
        feat, j, trades, bb, explain, events, strat = run_mind(raw, cross, interval, leverage)
    last = j.iloc[-1]
    cap = capital()
    st.subheader("🕰️ بازپخش تاریخی (backtest replay) — نه حساب زنده")
    st.caption(f"ذهن کل پنجره‌ی داده ({to_berlin(j.iloc[[0]]).index[0]} تا {to_berlin(j.iloc[[-1]]).index[0]} برلین) را از "
               f"{cap.usd:,.2f} $ بازپخش می‌کند و هر بار دوباره محاسبه می‌شود. این عدد سود/زیان واقعی یا زنده نیست.")
    a, b, c, d = st.columns(4)
    a.metric("آب‌میوه‌ی بازپخش ($)", f"{last.juice:,.2f}", f"{last.juice / cap.usd - 1:+.1%}")
    b.metric("معاملات بازپخش", len(trades))
    c.metric("حالت غالب", f"{FA[last.regime]} {max(last.P_bull, last.P_bear, last.P_range):.0%}")
    d.metric("استراتژی فعال", last.strategy)
    with st.expander("🧠 توضیح کامل تصمیم ذهن", expanded=False):
        st.markdown(explain)

    t1, t2, t3, t4, t5 = st.tabs(["📜 تاریخچه‌ی سیگنال‌ها", "📒 معاملات کاغذی", "📈 پیشرفت یادگیری", "🗃️ حافظه", "🪙 کریپتو (کاغذی)"])
    with t5:
        crypto_tab(); credit_footer()
    with t1:
        st.subheader("📜 تاریخچه‌ی سیگنال‌های کاغذی (وقت برلین) — نه سیگنال زنده")
        feed = j[j["action"] != "WAIT"].tail(20)[["close", "action", "strategy", "doubt", "reason"]]
        st.dataframe(to_berlin(feed.iloc[::-1]), width="stretch")
        ch = j.tail(200)
        fig = go.Figure(go.Scatter(x=ch.index, y=ch.close, name="قیمت", line=dict(color="#00ffcc")))
        for act, col, sym in (("LONG", "#00cc66", "triangle-up"), ("SHORT", "#ff3366", "triangle-down")):
            p = ch[ch.action == act]
            fig.add_trace(go.Scatter(x=p.index, y=p.close, mode="markers", name=act, marker=dict(color=col, size=10, symbol=sym)))
        fig.update_layout(template="plotly_dark", height=320, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width="stretch")
        credit_footer()
    with t2:
        if trades.empty:
            st.info("هنوز معامله‌ی کاغذی بسته‌شده‌ای نیست.")
        else:
            w = (trades.pnl > 0).mean()
            x, y, z = st.columns(3)
            x.metric(f"نرخ برد ({leverage}x)", f"{w:.0%}"); y.metric("میانگین R", f"{trades.R.mean():+.2f}")
            z.metric("لیکوئید", int((trades.reason == "liquidation").sum()))
            st.subheader("📜 تاریخچه‌ی معاملات کاغذی (وقت برلین)")
            st.dataframe(to_berlin(trades.tail(30).iloc[::-1]), width="stretch")
        credit_footer()
    with t3:
        fig = go.Figure(go.Scatter(x=j.index, y=j.juice, name="آب‌میوه", line=dict(color="#ffcc00")))
        fig.update_layout(template="plotly_dark", height=250, margin=dict(l=10, r=10, t=30, b=10), title="منحنی آب‌میوه")
        st.plotly_chart(fig, width="stretch")
        fig = go.Figure(go.Scatter(x=j.index, y=j.trust, name="اعتماد به شهود", line=dict(color="#cc88ff")))
        fig.update_layout(template="plotly_dark", height=220, margin=dict(l=10, r=10, t=30, b=10), title="اعتماد به شهود (به تفکیک رژیم فعلی)")
        st.plotly_chart(fig, width="stretch")
        with st.spinner(f"میدان تکامل با {pop:,} ژنوم..."):
            arena, cut = run_arena_cached(raw, cross, interval, pop)
        fig = go.Figure()
        rows = []
        for lev, r in arena.items():
            h = r["history"]
            fig.add_trace(go.Scatter(x=h.generation, y=h.survival, mode="lines+markers", name=f"بقا {lev:g}x"))
            dfl = r["deflation"]
            rows.append({"سطح": f"{lev:g}x", "بقای قهرمانان OOS": dfl["champ_oos_survival"],
                         "لیکوئید قهرمانان OOS": dfl["champ_oos_liquidated"], "بازده میانه قهرمانان": dfl["champ_oos_median_ret"],
                         "بازده میانه تصادفی": dfl["random_oos_median_ret"], "صدک در برابر تصادفی": dfl["champ_pctile_vs_random"]})
        fig.update_layout(template="plotly_dark", height=260, margin=dict(l=10, r=10, t=30, b=10),
                          title="منحنی بقا در نسل‌ها (فقط IS)", xaxis_title="نسل", yaxis_title="سهم بازمانده")
        st.plotly_chart(fig, width="stretch")
        st.caption(f"OOS از {cut} — قهرمانان در برابر ژنوم‌های تصادفی (آزمون آزمون‌های چندگانه)")
        st.dataframe(pd.DataFrame(rows).round(3), width="stretch")
        st.dataframe(pd.DataFrame(strat).T.rename(columns={"score": "امتیاز EWMA (R)", "n": "تعداد", "demoted_until": "تنزل تا کندل"}),
                     width="stretch")
        credit_footer()
    with t4:
        st.subheader("جعبه‌سیاه اشتباهات")
        st.dataframe(bb.tail(30).iloc[::-1] if not bb.empty else pd.DataFrame({"پیام": ["خالی"]}), width="stretch")
        st.subheader("دفتر روزنامه‌ی تصمیم‌ها")
        st.dataframe(to_berlin(j.tail(50).iloc[::-1][["action", "reason", "intuition", "evidence", "doubt", "trust", "juice"]]), width="stretch")
        st.download_button("دانلود دفتر (CSV)", j.to_csv().encode("utf-8"), "journal.csv", "text/csv")
        st.subheader("رویدادها")
        st.write([e[1] for e in events[-15:]])
        credit_footer()


live_panel()
dashboard()
st.sidebar.markdown("---")
st.sidebar.markdown(CREDIT_FA)
credit_footer()
