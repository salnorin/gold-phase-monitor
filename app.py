import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# تنظیمات صفحه وب
st.set_page_config(page_title="مدار ۴بعدی و ارگانیسم زنده طلا", layout="wide")
st.title("🧬 مانیتورینگ ارگانیک طلا + موجود زنده‌ی فاز بازار")
st.write("سیستم بیولوژیک طلا: از تنفس بازار تا حالت‌های زنده و احساسیِ ارگانیسم.")


# بارگذاری و پردازش مدل ارگانیک
@st.cache_data
def load_organic_market_model():
  try:
    raw_data = yf.download("GC=F", start="2024-01-01", progress=False)
    if raw_data.empty:
      return None

    df = pd.DataFrame()
    df["Open"] = raw_data["Open"].iloc[:, 0]
    df["High"] = raw_data["High"].iloc[:, 0]
    df["Low"] = raw_data["Low"].iloc[:, 0]
    df["Close"] = raw_data["Close"].iloc[:, 0]
    df["Volume"] = raw_data["Volume"].iloc[:, 0]

    # ۱. شعاع تنفسی (Volatility)
    df["Volatility"] = (df["High"] - df["Low"]) / df["Close"]
    df["Breath_Radius"] = df["Volatility"].rolling(window=12).mean() * 1000

    # ۲. خواب بازار و بیداری مؤسسات
    vol_baseline = df["Volatility"].rolling(window=50).mean()
    df["Is_Asleep"] = df["Volatility"] < (vol_baseline * 0.75)

    # ۳. منطقه کشتار نهنگ‌ها (Slaughter Zone)
    avg_volume = df["Volume"].rolling(window=20).mean()
    df["Retail_FOMO"] = (df["Volume"] > (avg_volume * 1.4)) & (
        df["Close"] > df["Open"]
    )
    max_radius = df["Breath_Radius"].quantile(0.88)
    df["Slaughter_Zone"] = (df["Breath_Radius"] > max_radius) & (
        df["Retail_FOMO"]
    )

    # ۴. اعتبارسنجی سیگنال‌ها (۵ کندل بعد)
    df["Future_Return_5C"] = df["Close"].shift(-5) - df["Close"]
    df["Signal_Success"] = np.where(
        df["Slaughter_Zone"] & (df["Future_Return_5C"] < 0), 1, 0
    )
    df["Signal_Attempted"] = np.where(df["Slaughter_Zone"], 1, 0)

    # ۵. ابعاد مومنتوم و زمان
    df["Returns"] = df["Close"].pct_change()
    df["Theta"] = df["Returns"].cumsum() * 25
    df["Z_Time"] = np.arange(len(df))

    df.dropna(subset=["Close", "Volume"], inplace=True)
    return df
  except Exception as e:
    return None


data = load_organic_market_model()

if data is None or data.empty:
  st.error("خطا در دریافت داده‌ها. لطفاً صفحه را رفرش کنید.")
else:
  # وضعیت لحظه‌ای آخرین کندل برای موجود زنده
  latest = data.iloc[-1]

  # تعیین حالت، قیافه و رنگ موجود زنده بازار بر اساس شرایط فیزیولوژیک
  if latest["Slaughter_Zone"]:
    creature_emoji = "👹⚡"
    creature_name = "«بَزکوهیِ خونخوار / کمین نهنگ»"
    creature_mood = (
        "عصبانی و در حال درویدنِ ریتل‌ها! بازار در منطقه کشتار است."
    )
    bg_color = "rgba(255, 0, 85, 0.15)"
    border_color = "#ff0055"
  elif latest["Is_Asleep"]:
    creature_emoji = "💤🐼"
    creature_name = "«تپلوِ خواب‌آلود / خرپف ممتد»"
    creature_mood = (
        "در خواب عمیقِ سکوت است. مؤسسات دارند در تاریکی انباشت می‌کنند."
    )
    bg_color = "rgba(0, 255, 204, 0.1)"
    border_color = "#00ffcc"
  else:
    creature_emoji = "✨🦊"
    creature_name = "«روباهِ هوشیار / تنفس طبیعی»"
    creature_mood = "سر حال، در حال تنفس و هدایت جریان نقدینگی در بافت بازار."
    bg_color = "rgba(0, 180, 255, 0.1)"
    border_color = "#00b4ff"

  # نمایش کارت متحرک موجود زنده بازار با CSS
  st.markdown(
      f"""
    <style>
    @keyframes pulse-anim {{
        0% {{ transform: scale(1); }}
        50% {{ transform: scale(1.02); }}
        100% {{ transform: scale(1); }}
    }}
    .creature-box {{
        background-color: {bg_color};
        border: 2px solid {border_color};
        padding: 20px;
        border-radius: 15px;
        text-align: center;
        animation: pulse-anim 2s infinite;
        margin-bottom: 25px;
    }}
    .creature-emoji {{
        font-size: 55px;
    }}
    .creature-title {{
        font-size: 19px;
        font-weight: bold;
        color: #ffffff;
        margin-top: 8px;
    }}
    .creature-desc {{
        font-size: 14px;
        color: #dddddd;
        margin-top: 5px;
    }}
    </style>
    <div class="creature-box">
        <div class="creature-emoji">{creature_emoji}</div>
        <div class="creature-title">موجود زنده بازار: {creature_name}</div>
        <div class="creature-desc">وضعیت فیزیولوژیک: {creature_mood}</div>
    </div>
    """,
      unsafe_allow_html=True,
  )

  # متریک‌های کلیدی وین‌ریت
  total_signals = data["Signal_Attempted"].sum()
  successful_signals = data["Signal_Success"].sum()
  win_rate = (
      (successful_signals / total_signals * 100) if total_signals > 0 else 0
  )

  col1, col2, col3 = st.columns(3)
  col1.metric("کل سیگنال‌ها", int(total_signals))
  col2.metric("سیگنال‌های موفق", int(successful_signals))
  col3.metric("دقت سیستم (Win Rate)", f"{win_rate:.1f}%")

  st.divider()

  # جدول سیگنال‌ها
  st.subheader("📋 جدول نقاط عطف و سیگنال‌های ورود/خروج")
  recent_events = data[data["Slaughter_Zone"] | data["Is_Asleep"]].tail(8)
  signal_table = pd.DataFrame({
      "زمان": recent_events.index.strftime("%m-%d %H:%M"),
      "قیمت طلا": recent_events["Close"].round(2),
      "وضعیت فاز ارگانیسم": np.where(
          recent_events["Slaughter_Zone"],
          "⚠️ Slaughter Zone (تله نهنگ)",
          "💤 خواب بازار (انباشت)",
      ),
      "نتیجه تست": np.where(
          recent_events["Signal_Success"] == 1, "✅ تایید شد", "⏳ در حال بررسی"
      ),
  })
  st.dataframe(signal_table, use_container_width=True)

  st.divider()

  # نماهای دوبعدی تخصصی برای موبایل
  st.subheader("📈 تحلیل ابعاد تفکیک‌شده بازار")
  st.write("**۱. بعد قیمت و زمان (Price Action):**")
  st.line_chart(data["Close"].tail(120))

  st.write("**۲. بعد شعاع تنفسی و نوسان (Breath Radius):**")
  st.line_chart(data["Breath_Radius"].tail(120))

  st.write("**۳. بعد مومنتوم جریان سرمایه (Momentum Theta):**")
  st.line_chart(data["Theta"].tail(120))

  st.divider()

  # مدار ۳بعدی
  st.subheader("🌐 مدار جامع ۳بعدی فازسنج طلا")
  normal_data = data[~data["Slaughter_Zone"]]
  slaughter_data = data[data["Slaughter_Zone"]]

  X_norm = normal_data["Breath_Radius"] * np.cos(normal_data["Theta"])
  Y_norm = normal_data["Breath_Radius"] * np.sin(normal_data["Theta"])
  Z_norm = normal_data["Z_Time"]

  X_slg = slaughter_data["Breath_Radius"] * np.cos(slaughter_data["Theta"])
  Y_slg = slaughter_data["Breath_Radius"] * np.sin(slaughter_data["Theta"])
  Z_slg = slaughter_data["Z_Time"]

  fig = go.Figure()
  fig.add_trace(
      go.Scatter3d(
          x=X_norm,
          y=Y_norm,
          z=Z_norm,
          mode="lines",
          line=dict(color="#00ffcc", width=3),
          name="مسیر تنفسی ارگانیسم",
      )
  )
  if not slaughter_data.empty:
    fig.add_trace(
        go.Scatter3d(
            x=X_slg,
            y=Y_slg,
            z=Z_slg,
            mode="markers",
            marker=dict(size=6, color="#ff0055", symbol="diamond"),
            name="⚠️ منطقه کشتار نهنگ‌ها",
        )
    )

  fig.update_layout(
      scene=dict(
          xaxis_title="فاز افقی (X)",
          yaxis_title="فاز عمودی (Y)",
          zaxis_title="زمان (Z)",
      ),
      margin=dict(l=0, r=0, b=0, t=20),
      height=500,
  )
  st.plotly_chart(fig, use_container_width=True)
