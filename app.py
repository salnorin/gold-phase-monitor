# app.py
from core.organism import BiologicalOrganism
import plotly.graph_objects as go
import streamlit as st
import time

st.set_page_config(
    page_title="ارگانیسم طلا - سیگنال معاملاتی",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.title("🧬 ارگانیسم زنده طلا (XAU/USD)")

if "organism" not in st.session_state:
    st.session_state.organism = BiologicalOrganism()
if "last_update" not in st.session_state:
    st.session_state.last_update = 0
if "df" not in st.session_state:
    st.session_state.df = None

organism = st.session_state.organism

# کنترل حالت زنده
live_mode = st.sidebar.checkbox("🔴 حالت زنده (آپدیت خودکار هر ۴ دقیقه)", value=True)
interval = 240  # ثانیه (۴ دقیقه)

# دکمه دستی (اختیاری)
manual = st.button("🔄 به‌روزرسانی دستی", use_container_width=True)

now = time.time()
should_update = manual or (live_mode and (now - st.session_state.last_update > interval))

if should_update:
    with st.spinner("در حال تحلیل بازار و به‌روزرسانی سیگنال..."):
        df, decision = organism.live_cycle()
        st.session_state.df = df
        st.session_state.decision = decision
        st.session_state.last_update = now

# نمایش نتایج
if st.session_state.df is not None and not st.session_state.df.empty:
    df = st.session_state.df
    decision = st.session_state.get("decision", "")
    latest = df.iloc[-1]

    price = float(latest.get("Close", 0))
    atp = float(latest.get("ATP_Energy", 0))
    cortisol = float(latest.get("Cortisol_Stress", 0))
    optical = float(latest.get("Optical_Pull", 0))
    slaughter = bool(latest.get("Slaughter_Zone", False))
    long_zone = bool(latest.get("Long_Zone", False))
    target = float(latest.get("Target_Price", 0) or 0)
    stop = float(latest.get("Stop_Loss", 0) or 0)

    # زمان آخرین به‌روزرسانی
    mins_ago = int((time.time() - st.session_state.last_update) / 60)
    st.caption(f"آخرین به‌روزرسانی: {mins_ago} دقیقه پیش" if mins_ago > 0 else "آخرین به‌روزرسانی: همین الان")

    # ========== سیگنال معاملاتی اصلی ==========
    st.header("📈 سیگنال معاملاتی")

    if atp < 30 or cortisol > 75:
        signal = "صبر کن"
        emoji = "⏸️"
        color = "#ffaa00"
        explanation = "انرژی ارگانیسم خیلی کم یا استرس خیلی بالاست. فعلاً هیچ تریدی نکن."
        direction = "FLAT"
    elif slaughter and atp > 30:
        signal = "SHORT"
        emoji = "🔻"
        color = "#ff3366"
        explanation = "منطقه شکار فعال است. ذهنیت فروش داشته باش."
        direction = "SHORT"
    elif long_zone and atp > 35 and cortisol < 60:
        signal = "LONG"
        emoji = "🔺"
        color = "#00cc66"
        explanation = "منطقه رشد فعال است. ذهنیت خرید داشته باش."
        direction = "LONG"
    elif optical > 0.4 and atp > 40:
        signal = "تمایل به LONG"
        emoji = "🔺"
        color = "#00cc66"
        explanation = "کشش نوری به سمت بالا قوی است."
        direction = "LONG"
    elif optical < -0.4 and atp > 40:
        signal = "تمایل به SHORT"
        emoji = "🔻"
        color = "#ff3366"
        explanation = "کشش نوری به سمت پایین قوی است."
        direction = "SHORT"
    else:
        signal = "بدون سیگنال قوی"
        emoji = "⚖️"
        color = "#888888"
        explanation = "بازار در تعادل نسبی است. منتظر سیگنال واضح‌تر بمان."
        direction = "FLAT"

    st.markdown(
        f"""
        <div style="background:{color}33; border:3px solid {color}; border-radius:20px; padding:25px; text-align:center; margin-bottom:20px;">
            <div style="font-size:4em; margin:0;">{emoji}</div>
            <h1 style="margin:10px 0; color:{color};">{signal}</h1>
            <p style="font-size:1.2em; margin:0;">{explanation}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # نقاط معاملاتی
    st.subheader("نقاط معاملاتی")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("قیمت فعلی", f"{price:.2f}")
    col2.metric("جهت", direction)
    col3.metric("تارگت", f"{target:.2f}" if target > 0 else "—")
    col4.metric("استاپ‌لاس", f"{stop:.2f}" if stop > 0 else "—")

    # وضعیت ارگانیسم
    with st.expander("🦊 وضعیت داخلی ارگانیسم"):
        c1, c2, c3 = st.columns(3)
        c1.metric("انرژی ATP", f"{atp:.1f}%")
        c2.metric("کورتیزول", f"{cortisol:.1f}")
        c3.metric("کشش نوری", f"{optical:.2f}")
        st.markdown(decision)

    # نمودار
    st.subheader("نمودار")
    chart_data = df.tail(100)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=chart_data.index, y=chart_data["Close"],
        mode="lines", name="قیمت", line=dict(color="#00ffcc", width=2)
    ))

    shorts = chart_data[chart_data.get("Slaughter_Zone", False) == True]
    longs = chart_data[chart_data.get("Long_Zone", False) == True]
    if not shorts.empty:
        fig.add_trace(go.Scatter(
            x=shorts.index, y=shorts["Close"], mode="markers",
            name="SHORT", marker=dict(color="#ff3366", size=10, symbol="triangle-down")
        ))
    if not longs.empty:
        fig.add_trace(go.Scatter(
            x=longs.index, y=longs["Close"], mode="markers",
            name="LONG", marker=dict(color="#00cc66", size=10, symbol="triangle-up")
        ))

    fig.update_layout(template="plotly_dark", height=400, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("در حال آماده‌سازی اولین سیگنال... اگر چیزی نشان داده نشد، دکمه به‌روزرسانی دستی را بزن.")

# اگر حالت زنده فعال است، بعد از مدتی صفحه را رفرش کن
if live_mode:
    time.sleep(2)
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### حمایت")
st.sidebar.code("bc1qh2wwl2s2x4qzthtruj4rrphh6xkg98vfysu659")
