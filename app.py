# app.py
from core.organism import BiologicalOrganism
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="ارگانیسم زنده طلا (XAU/USD)",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.title("🧬 ارگانیسم زنده و خودتکامل‌یابنده طلا (XAU/USD)")

# ساخت نمونه زنده از ارگانیسم در session_state
if "organism" not in st.session_state:
  st.session_state.organism = BiologicalOrganism()

organism = st.session_state.organism

# دکمه اجرای چرخه زندگی در سایدبار یا صفحه اصلی
if st.button("🔄 اجرای چرخه زندگی جدید ارگانیسم"):
  with st.spinner("ارگانیسم در حال تنفس، ادراک بازار و تفکر است..."):
    df, decision = organism.live_cycle()

  if df is not None:
    st.success(
        f"چرخه با موفقیت انجام شد | نسل فعلی ارگانیسم: {organism.generation}"
    )
    st.markdown(decision)

    # نمودار قیمت و سیگنال‌ها
    chart_data = df.tail(120)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=chart_data.index,
            y=chart_data["Close"],
            mode="lines",
            name="قیمت طلا",
            line=dict(color="#00ffcc", width=2),
        )
    )

    # پایش نقاط سیگنال
    shorts = chart_data[chart_data.get("Slaughter_Zone", False) == True]
    longs = chart_data[chart_data.get("Long_Zone", False) == True]

    if not shorts.empty:
      fig.add_trace(
          go.Scatter(
              x=shorts.index,
              y=shorts["Close"],
              mode="markers",
              name="شکار (SHORT)",
              marker=dict(color="#ff0055", size=12, symbol="triangle-down"),
          )
      )
    if not longs.empty:
      fig.add_trace(
          go.Scatter(
              x=longs.index,
              y=longs["Close"],
              mode="markers",
              name="رشد (LONG)",
              marker=dict(color="#00ff80", size=12, symbol="triangle-up"),
          )
      )

    fig.update_layout(
        template="plotly_dark",
        margin=dict(l=20, r=20, t=30, b=20),
        height=450,
    )
    st.plotly_chart(fig, use_container_width=True)

    # نمایش وضعیت‌های حیاتی ارگانیسم به صورت متریک
    col1, col2, col3, col4 = st.columns(4)
    latest = df.iloc[-1]
    col1.metric("انرژی متابولیک (ATP)", f"{latest.get('ATP_Energy', 0):.1f}%")
    col2.metric("هورمون استرس (کورتیزول)", f"{latest.get('Cortisol_Stress', 0):.1f}")
    col3.metric("کشش نوری (Optical Pull)", f"{latest.get('Optical_Pull', 0):.2f}")
    col4.metric("نسل تکاملی", organism.generation)
  else:
    st.error(
        "خطا در دریافت داده‌ها یا اجرای چرخه. لطفاً اتصال اینترنت یا دریافت"
        " داده را بررسی کنید."
    )

# بخش حمایت مالی در سایدبار (Bitcoin & EVM)
st.sidebar.markdown("---")
st.sidebar.subheader("⚡ حمایت از تکامل ارگانیسم (Donation)")
st.sidebar.markdown(
    "اگر این سیستم بیولوژیک و هوشمند برای شما الهام‌بخش است، می‌توانید با"
    " حمایت مالی به ادامه‌ی حیات و تکامل آن کمک کنید:"
)

don_tab1, don_tab2 = st.sidebar.tabs(["₿ بیت‌کوین", "Ξ اتریوم / EVM"])

with don_tab1:
  st.code("bc1qh2wwl2s2x4qzthtruj4rrphh6xkg98vfysu659", language="text")
  st.caption("شبکه Bitcoin (Mainnet)")

with don_tab2:
  st.code("0x02e71Bb3031F7926da23925111B9a5a0808f8123", language="text")
  st.caption("شبکه Ethereum / سازگار با EVM")
