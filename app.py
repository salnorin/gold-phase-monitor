# app.py — داشبورد موجود زنده (فقط شبیه‌سازی کاغذی؛ هیچ سفارش واقعی)
from datetime import timedelta
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.arena import run_arena
from core.mind import FA, Mind, MindConfig
from core.organism import BiologicalOrganism
from core.research import load

st.set_page_config(page_title="ارگانیسم طلا — موجود زنده", layout="wide", initial_sidebar_state="collapsed")
st.markdown("<style>section.main .stMarkdown, [data-testid='stMainBlockContainer'] .stMarkdown {direction: rtl; text-align: right;}</style>", unsafe_allow_html=True)
st.title("🐻 ارگانیسم زنده‌ی طلا (XAU/USD)")
st.caption("⚠️ فقط شبیه‌سازی کاغذی و آموزشی — بدون سفارش واقعی و بدون کلید صرافی. توصیه‌ی مالی نیست.")

INTERVAL_H = {"1h": 1.0, "15m": 0.25, "5m": 5 / 60}
interval = st.sidebar.selectbox("بازه‌ی کندل", list(INTERVAL_H), index=0)
leverage = st.sidebar.select_slider("اهرم شبیه‌سازی", options=[1, 5, 10, 20], value=20)
pop = st.sidebar.select_slider("جمعیت میدان تکامل", options=[500, 2000, 10000], value=2000)
live = st.sidebar.checkbox("🔴 به‌روزرسانی خودکار (هر ۴ دقیقه)", value=True)


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
    m = Mind(MindConfig(leverage=float(leverage), bar_hours=INTERVAL_H[interval]))
    j = m.run(feat, now=pd.Timestamp.now(tz="UTC"))
    return feat, j, m.trades_frame(), m.blackbox_frame(), m.explain(), m.events, m.strat


@st.cache_data(ttl=3600, show_spinner=False)
def run_arena_cached(raw, cross, interval, pop):
    res, cut = run_arena(raw, cross, INTERVAL_H[interval], pop=pop, generations=6)
    return {lev: dict(history=r["history"], deflation=r["deflation"]) for lev, r in res.items()}, cut


def creature_svg(breath_s, hue, label):
    return f"""
<div style="display:flex;justify-content:center">
<svg viewBox="0 0 220 200" width="260" height="236" xmlns="http://www.w3.org/2000/svg">
 <style>
  .body {{ transform-origin: 110px 120px; animation: breathe {breath_s:.2f}s ease-in-out infinite; }}
  @keyframes breathe {{ 0%,100% {{ transform: scale(1,1); }} 50% {{ transform: scale(1.06,1.10); }} }}
  .eye {{ animation: blink 5s infinite; transform-origin: center; }}
  @keyframes blink {{ 0%,94%,100% {{ transform: scaleY(1); }} 97% {{ transform: scaleY(0.1); }} }}
 </style>
 <g class="body" fill="hsl({hue},55%,42%)">
  <circle cx="62" cy="52" r="20"/><circle cx="158" cy="52" r="20"/>
  <circle cx="62" cy="52" r="10" fill="hsl({hue},45%,65%)"/><circle cx="158" cy="52" r="10" fill="hsl({hue},45%,65%)"/>
  <ellipse cx="110" cy="140" rx="70" ry="52"/>
  <circle cx="110" cy="85" r="52"/>
  <ellipse cx="110" cy="102" rx="24" ry="18" fill="hsl({hue},40%,72%)"/>
  <ellipse cx="110" cy="95" rx="9" ry="6" fill="#222"/>
  <path d="M100 108 Q110 116 120 108" stroke="#222" stroke-width="3" fill="none"/>
  <g class="eye"><circle cx="90" cy="72" r="6" fill="#111"/><circle cx="130" cy="72" r="6" fill="#111"/></g>
  <ellipse cx="110" cy="150" rx="40" ry="30" fill="hsl({hue},40%,62%)"/>
 </g>
 <text x="110" y="196" text-anchor="middle" font-size="13" fill="#ddd">{label}</text>
</svg></div>"""


@st.fragment(run_every=timedelta(seconds=240) if live else None)
def dashboard():
    try:
        raw, cross = get_data(interval)
    except Exception as e:
        st.error(f"دریافت داده ناموفق بود: {e}"); return
    with st.spinner("ذهن در حال مرور تاریخچه..."):
        feat, j, trades, bb, explain, events, strat = run_mind(raw, cross, interval, leverage)
    last = j.iloc[-1]
    start_eq = MindConfig().start_equity
    health = float(np.clip(last.juice / start_eq, 0, 1.5))
    hue = int(np.clip((health - 0.5) / 0.7, 0, 1) * 120)                       # قرمز → سبز
    breath = float(np.clip(4.0 / (max(last.vol_ratio, 0.2) * max(last.oxygen, 0.2) ** 0.5), 0.6, 6.0))
    sleeping = not bool(last.get("market_open", True))
    if sleeping:
        hue, breath = 210, 7.0
    mood = "خواب — بازار بسته 💤" if sleeping else "در حال استراحت 😴" if "استراحت" in last.reason else ("محتاط 🐋" if "نهنگ" in last.reason else
                                                                ("در شکار 🎯" if last.action != "WAIT" else "هوشیار 👀"))

    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown(creature_svg(breath, hue, f"تنفس هر {breath:.1f} ثانیه · {mood}"), unsafe_allow_html=True)
    with c2:
        a, b, c, d = st.columns(4)
        a.metric("🧃 آب‌میوه (سرمایه کاغذی)", f"{last.juice:,.0f}", f"{last.juice / start_eq - 1:+.1%} | افت از اوج کل {last.drawdown_all:.0%}")
        b.metric("قیمت", f"{last.close:,.2f}")
        c.metric("🫁 اکسیژن (نقدینگی)", f"{last.oxygen:.2f}")
        d.metric("نوسان / عادی", f"{last.vol_ratio:.2f}")
        a.metric("حالت غالب", f"{FA[last.regime]} {max(last.P_bull, last.P_bear, last.P_range):.0%}")
        b.metric("تردید", f"{last.doubt:.2f}")
        c.metric("اعتماد به شهود", f"{last.trust:.2f}")
        d.metric("استراتژی فعال", last.strategy)
        sig_color = {"LONG": "#00cc66", "SHORT": "#ff3366"}.get(last.action, "#888")
        st.markdown(f"<div style='border:2px solid {sig_color};border-radius:12px;padding:12px;background:{sig_color}22'>"
                    f"<b style='color:{sig_color};font-size:1.4em'>{last.action}</b> — {last.reason}</div>", unsafe_allow_html=True)
    if sleeping:
        st.info("💤 بازار بسته است یا داده‌ی تازه نمی‌رسد؛ ارگانیسم خواب است و هیچ سیگنال یا معامله‌ای نمی‌دهد.")
    with st.expander("🧠 توضیح کامل تصمیم ذهن", expanded=False):
        st.markdown(explain)

    t1, t2, t3, t4 = st.tabs(["📡 جریان سیگنال‌ها", "📒 معاملات کاغذی", "📈 پیشرفت یادگیری", "🗃️ حافظه"])
    with t1:
        feed = j[j["action"] != "WAIT"].tail(20)[["close", "action", "strategy", "doubt", "reason"]]
        st.dataframe(feed.iloc[::-1], width="stretch")
        ch = j.tail(200)
        fig = go.Figure(go.Scatter(x=ch.index, y=ch.close, name="قیمت", line=dict(color="#00ffcc")))
        for act, col, sym in (("LONG", "#00cc66", "triangle-up"), ("SHORT", "#ff3366", "triangle-down")):
            p = ch[ch.action == act]
            fig.add_trace(go.Scatter(x=p.index, y=p.close, mode="markers", name=act, marker=dict(color=col, size=10, symbol=sym)))
        fig.update_layout(template="plotly_dark", height=320, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width="stretch")
    with t2:
        if trades.empty:
            st.info("هنوز معامله‌ی کاغذی بسته‌شده‌ای نیست.")
        else:
            w = (trades.pnl > 0).mean()
            x, y, z = st.columns(3)
            x.metric(f"نرخ برد ({leverage}x)", f"{w:.0%}"); y.metric("میانگین R", f"{trades.R.mean():+.2f}")
            z.metric("لیکوئید", int((trades.reason == "liquidation").sum()))
            st.dataframe(trades.tail(30).iloc[::-1], width="stretch")
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
    with t4:
        st.subheader("جعبه‌سیاه اشتباهات")
        st.dataframe(bb.tail(30).iloc[::-1] if not bb.empty else pd.DataFrame({"پیام": ["خالی"]}), width="stretch")
        st.subheader("دفتر روزنامه‌ی تصمیم‌ها")
        st.dataframe(j.tail(50).iloc[::-1][["action", "reason", "intuition", "evidence", "doubt", "trust", "juice"]], width="stretch")
        st.download_button("دانلود دفتر (CSV)", j.to_csv().encode("utf-8"), "journal.csv", "text/csv")
        st.subheader("رویدادها")
        st.write([e[1] for e in events[-15:]])


dashboard()
st.sidebar.markdown("---")
st.sidebar.markdown("ساخته‌شده توسط **Intelgy** (دستیار هوش مصنوعی) با همکاری سازنده **salnorin**")
