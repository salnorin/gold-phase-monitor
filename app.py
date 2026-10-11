# app.py — رابط کاربری (فقط نمایش؛ منطق در core/brain.py)
from datetime import timedelta
import time

import plotly.graph_objects as go
import streamlit as st

from core.config import DEFAULT_CONFIG
from core.organism import BiologicalOrganism

st.set_page_config(page_title="ارگانیسم طلا - سیگنال معاملاتی", layout="wide", initial_sidebar_state="collapsed")
st.title("🧬 ارگانیسم زنده طلا (XAU/USD)")
st.caption("⚠️ آزمایشی و آموزشی — توصیه‌ی مالی نیست. بک‌تست فعلی مزیت آماری نشان نمی‌دهد.")

cfg = DEFAULT_CONFIG
live_mode = st.sidebar.checkbox(f"🔴 حالت زنده (آپدیت خودکار هر {cfg.refresh_seconds // 60} دقیقه)", value=True)

STYLE = {"LONG": ("🔺", "#00cc66", "منطقه رشد با توافق ارگان‌ها. ذهنیت خرید."),
         "SHORT": ("🔻", "#ff3366", "منطقه شکار با توافق ارگان‌ها. ذهنیت فروش."),
         "FLAT": ("⏸️", "#888888", "")}


def refresh():
    with st.spinner("در حال تحلیل بازار و به‌روزرسانی سیگنال..."):
        org = BiologicalOrganism(config=cfg)
        df, decision = org.live_cycle()
        st.session_state.update(df=df, decision=decision, last_update=time.time())


@st.fragment(run_every=timedelta(seconds=cfg.refresh_seconds) if live_mode else None)
def dashboard():
    if st.button("🔄 به‌روزرسانی دستی", width="stretch") or \
            time.time() - st.session_state.get("last_update", 0) >= cfg.refresh_seconds:
        refresh()
    df = st.session_state.get("df")
    if df is None or df.empty:
        st.info(st.session_state.get("decision") or "در حال آماده‌سازی اولین سیگنال...")
        return
    last = df.iloc[-1]
    signal = last["signal"]
    emoji, color, text = STYLE[signal]
    text = text if signal != "FLAT" else last["reason"]
    mins = int((time.time() - st.session_state.last_update) / 60)
    st.caption(f"آخرین به‌روزرسانی: {mins} دقیقه پیش" if mins else "آخرین به‌روزرسانی: همین الان")

    st.header("📈 سیگنال معاملاتی")
    st.markdown(f"""<div style="background:{color}33;border:3px solid {color};border-radius:20px;padding:25px;text-align:center;margin-bottom:20px;">
        <div style="font-size:4em">{emoji}</div><h1 style="margin:10px 0;color:{color}">{signal}</h1>
        <p style="font-size:1.2em">{text}</p></div>""", unsafe_allow_html=True)

    st.subheader("نقاط معاملاتی")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("قیمت فعلی", f"{last.Close:.2f}")
    c2.metric("اطمینان", f"{last.confidence:.2f}")
    c3.metric("تارگت", f"{last.Target_Price:.2f}" if last.Target_Price else "—")
    c4.metric("استاپ‌لاس", f"{last.Stop_Loss:.2f}" if last.Stop_Loss else "—")
    c5.metric("ATR", f"{last.ATR:.2f}")

    with st.expander("🦊 وضعیت داخلی ارگانیسم (جریان خون)"):
        a, b, c = st.columns(3)
        a.metric("انرژی ATP", f"{last.Brain_ATP:.1f}%")
        b.metric("کورتیزول", f"{last.Brain_Cortisol:.1f}")
        c.metric("خستگی", f"{last.fatigue:.2f}")
        st.markdown(st.session_state.decision)

    st.subheader("نمودار")
    ch = df.tail(150)
    fig = go.Figure(go.Scatter(x=ch.index, y=ch.Close, mode="lines", name="قیمت", line=dict(color="#00ffcc", width=2)))
    for d, name, col, sym in ((1, "LONG", "#00cc66", "triangle-up"), (-1, "SHORT", "#ff3366", "triangle-down")):
        pts = ch[ch.Signal_Dir == d]
        if not pts.empty:
            fig.add_trace(go.Scatter(x=pts.index, y=pts.Close, mode="markers", name=name, marker=dict(color=col, size=10, symbol=sym)))
    fig.update_layout(template="plotly_dark", height=400, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, width="stretch")


dashboard()
st.sidebar.markdown("---")
st.sidebar.markdown("### حمایت")
st.sidebar.code("bc1qh2wwl2s2x4qzthtruj4rrphh6xkg98vfysu659")
