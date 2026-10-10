from core.ai_analyst import BiologicalAIAnalyst
from core.respiration_engine import RespirationEngine
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="مدار بیولوژیک و هوش مصنوعی طلا", layout="wide"
)
st.title("🧬 مانیتورینگ ارگانیک و تحلیل‌گر زنده طلا (XAU/USD)")


@st.cache_data(ttl=300)
def get_data():
  engine = RespirationEngine()
  return engine.fetch_and_process()


data = get_data()

if data is None or data.empty:
  st.error("خطا در دریافت داده‌ها.")
else:
  engine = RespirationEngine()
  latest = data.iloc[-1]
  latest_time = data.index[-1]
  is_open = engine.is_market_open(latest_time)

  # ۱. نمایش وضعیت بازار (باز/بسته)
  if is_open:
    st.success("🟢 بازار باز و زنده است.")
  else:
    st.warning("🔴 بازار بسته است. تحلیل‌ها مربوط به زمان بازگشایی است.")

  # ۲. تحلیگر هوش مصنوعی
  st.subheader("🤖 کالبدشکافی هوش مصنوعی ارگانیسم")
  st.info(BiologicalAIAnalyst.generate_diagnostic(latest))

  # ۳. نمودار تعاملی قیمت
  st.subheader("📈 نمودار قیمت و نقاط برخورد")
  chart_data = data.tail(120)
  fig = go.Figure()
  fig.add_trace(
      go.Scatter(
          x=chart_data.index,
          y=chart_data["Close"],
          mode="lines",
          name="قیمت طلا",
          line=dict(color="#00ffcc"),
      )
  )

  shorts = chart_data[chart_data["Slaughter_Zone"]]
  if not shorts.empty:
    fig.add_trace(
        go.Scatter(
            x=shorts.index,
            y=shorts["Close"],
            mode="markers",
            name="⚠️ SHORT",
            marker=dict(color="#ff0055", size=12, symbol="triangle-down"),
        )
    )

  longs = chart_data[chart_data["Long_Zone"]]
  if not longs.empty:
    fig.add_trace(
        go.Scatter(
            x=longs.index,
            y=longs["Close"],
            mode="markers",
            name="🦅 LONG",
            marker=dict(color="#00ff80", size=12, symbol="triangle-up"),
        )
    )

  st.plotly_chart(fig, use_container_width=True)
    
