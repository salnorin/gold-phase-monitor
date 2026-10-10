import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# تنظیمات صفحه وب
st.set_page_config(
    page_title="مدار بیولوژیک و فازسنج طلا (Organic Respiration)", layout="wide"
)
st.title("🧬 مانیتورینگ ارگانیک و تنفس زنده بازار طلا (XAU/USD)")
st.write(
    "استراتژی اختصاصی سالار: مدل تنفس بازار، شعاع نوسان، مومنتوم تتا (Theta) و"
    " تله‌های کشتار نهنگ."
)


# بارگذاری و پردازش مدل کاملاً بیولوژیک و ارگانیسم بازار
@st.cache_data(ttl=600)
def load_pure_biological_model():
  try:
    raw_data = yf.download("GC=F", period="60d", interval="1h", progress=False)
    if raw_data.empty:
      return None

    df = pd.DataFrame()
    df["Open"] = raw_data["Open"].iloc[:, 0]
    df["High"] = raw_data["High"].iloc[:, 0]
    df["Low"] = raw_data["Low"].iloc[:, 0]
    df["Close"] = raw_data["Close"].iloc[:, 0]
    df["Volume"] = raw_data["Volume"].iloc[:, 0]

    # ۱. مدل تنفس ارگانیسم: شعاع تنفسی (Breath Radius) بر اساس نوسان و حجم بافت بازار
    df["Volatility"] = (df["High"] - df["Low"]) / df["Close"]
    df["Breath_Radius"] = df["Volatility"].rolling(window=12).mean() * 1000

    # ۲. مومنتوم زاویه‌ای و جریان چرخش سرمایه (Theta)
    df["Returns"] = df["Close"].pct_change()
    df["Theta"] = df["Returns"].cumsum() * 50
    df["Z_Time"] = np.arange(len(df))

    # ۳. فاز خواب ارگانیسم (Market Sleep / انباشت خاموش مؤسسات در تاریکی)
    radius_baseline = df["Breath_Radius"].rolling(window=40).mean()
    df["Is_Asleep"] = df["Breath_Radius"] < (radius_baseline * 0.75)

    # ۴. منطقه کشتار نهنگ‌ها (Slaughter Zone -> فرمان SHORT)
    # وقتی تنفس بازار در اوج انبساط است و گله‌ی ریتل‌ها دچار FOMO شده‌اند
    high_radius_threshold = df["Breath_Radius"].quantile(0.85)
    avg_volume = df["Volume"].rolling(window=20).mean()

    df["Slaughter_Zone"] = (
        (df["Breath_Radius"] > high_radius_threshold)
        & (df["Volume"] > avg_volume * 1.3)
        & (df["Close"] > df["Open"])
    )

    # ۵. بیداری و جهش ارگانیسم (Long Zone -> فرمان LONG)
    # خروج ارگانیسم از خواب عمیق همراه با چرخش رو به بالای مومنتوم تتا
    df["Long_Zone"] = (df["Is_Asleep"].shift(1) == True) & (
        df["Breath_Radius"] > radius_baseline
    ) & (df["Theta"].diff() > 0)

    # ۶. فرمان‌های عملیاتی و مدیریت ریسک ارگانیک
    df["Signal_Type"] = np.where(
        df["Slaughter_Zone"],
        "🔴 SHORT (تله نهنگ / تخلیه پوزیشن)",
        np.where(
            df["Long_Zone"],
            "🟢 LONG (جهش از خواب / انباشت موفق)",
            np.where(df["Is_Asleep"], "💤 خواب ارگانیسم (انباشت پنهان)", "⚪ تنفس طبیعی"),
        ),
    )

    df["Stop_Loss"] = np.where(
        df["Slaughter_Zone"],
        df["High"] + (df["Close"] * 0.0035),
        np.where(df["Long_Zone"], df["Low"] - (df["Close"] * 0.0035), 0),
    )
    df["Take_Profit"] = np.where(
        df["Slaughter_Zone"],
        df["Close"] - (df["Close"] * 0.008),
        np.where(df["Long_Zone"], df["Close"] + (df["Close"] * 0.008), 0),
    )

    # ۷. موتور اعتبارسنجی (سنجش موفقیت رفتار ارگانیسم پس از ۵ کندل)
    df["Future_Return_5C"] = df["Close"].shift(-5) - df["Close"]
    df["Signal_Success"] = np.where(
        (df["Slaughter_Zone"] & (df["Future_Return_5C"] < 0))
        | (df["Long_Zone"] & (df["Future_Return_5C"] > 0)),
        1,
        0,
    )
    df["Signal_Attempted"] = np.where(
        df["Slaughter_Zone"] | df["Long_Zone"], 1, 0
    )

    df.dropna(subset=["Close", "Volume"], inplace=True)
    return df
  except Exception as e:
    return None


data = load_pure_biological_model()

if data is None or data.empty:
  st.error("خطا در بارگذاری مدار ارگانیک بازار. لطفاً صفحه را رفرش کنید.")
else:
  latest = data.iloc[-1]
  latest_time = data.index[-1].strftime("%m-%d %H:%M")

  # حالت‌های زیستی موجود زنده بازار
  if latest["Slaughter_Zone"]:
    c_emoji = "👹⚡"
    c_name = "«بزکوهیِ خونخوار / تله نهنگ فعال (Short)»"
    c_desc = (
        "ارگانیسم در اوج تنش و انبساط تنفسی است؛ نهنگ‌ها در حال درو کردن"
        " خرده‌پاهای FOMO هستند."
    )
    c_bg = "rgba(255, 0, 85, 0.12)"
    c_border = "#ff0055"
  elif latest["Long_Zone"]:
    c_emoji = "🟢🦅"
    c_name = "«عقابِ شکارچی / جهش از انباشت (Long)»"
    c_desc = (
        "ارگانیسم از خواب عمیق بیدار شد؛ موج نقدینگی با چرخش تتا به سمت بالا"
        " شلیک شد."
    )
    c_bg = "rgba(0, 255, 128, 0.12)"
    c_border = "#00ff80"
  elif latest["Is_Asleep"]:
    c_emoji = "💤🐼"
    c_name = "«تپلوِ خواب‌آلود / سکوت مؤسساتی»"
    c_desc = (
        "تنش بازار خوابیده است؛ مؤسسات در تاریکی و سکوت در حال انباشت پنهان"
        " هستند."
    )
    c_bg = "rgba(0, 255, 204, 0.08)"
    c_border = "#00ffcc"
  else:
    c_emoji = "✨🦊"
    c_name = "«روباهِ هوشیار / تنفس روان»"
    c_desc = "جریان نقدینگی با ریتم و تنفس طبیعی در بافت بازار در حال گردش است."
    c_bg = "rgba(0, 180, 255, 0.08)"
    c_border = "#00b4ff"

  # کارت موجود زنده بازار
  st.markdown(
      f"""
    <div style="background-color: {c_bg}; border: 2px solid {c_border}; padding: 18px; border-radius: 12px; text-align: center; margin-bottom: 20px;">
        <div style="font-size: 45px;">{c_emoji}</div>
        <div style="font-size: 17px; font-weight: bold; color: #ffffff; margin-top: 6px;">وضعیت ارگانیسم: {c_name}</div>
        <div style="font-size: 13px; color: #cccccc; margin-top: 4px;">{c_desc} (زمان کندل: {latest_time})</div>
    </div>
    """,
      unsafe_allow_html=True,
  )

  # 🎯 فرمان معاملاتی ارگانیک
  st.subheader("🎯 فرمان معاملاتی مدل بیولوژیک (Long / Short)")
  if latest["Slaughter_Zone"] or latest["Long_Zone"]:
    st.warning(
        f"🚨 **سیگنال فعال:** `{latest['Signal_Type']}`\n\n"
        f"* **نقطه ورود (Entry):** `{latest['Close']:.2f}`\n"
        f"* **حد ضرر (Stop Loss):** `{latest['Stop_Loss']:.2f}`\n"
        f"* **حد سود (Take Profit):** `{latest['Take_Profit']:.2f}`\n"
        f"* **شعاع تنفسی ارگانیسم:** `{latest['Breath_Radius']:.1f}`"
    )
  else:
    st.info(
        "⏳ ارگانیسم در حال تنفس عادی است... منتظر شکل‌گیری تله نهنگ یا جهش"
        " انباشت بمانید."
    )

  st.divider()

  # متریک‌ها و Win Rate سیستم
  tot_sig = int(data["Signal_Attempted"].sum())
  succ_sig = int(data["Signal_Success"].sum())
  w_rate = (succ_sig / tot_sig * 100) if tot_sig > 0 else 0

  col1, col2, col3 = st.columns(3)
  col1.metric("کل فرمان‌های ارگانیک", tot_sig)
  col2.metric("فرمان‌های موفق", succ_sig)
  col3.metric("دقت بیولوژیک مدل (Win Rate)", f"{w_rate:.1f}%")

  st.divider()

  # 📈 چارت تعاملی قیمت و نقاط برخورد مدل بیولوژیک
  st.subheader(
      "📈 نمودار قیمت و سیگنال‌های تنفس ارگانیسم (با قابلیت زوم و بررسی دقیق)"
  )

  chart_data = data.tail(120)
  fig_price = go.Figure()

  fig_price.add_trace(
      go.Scatter(
          x=chart_data.index,
          y=chart_data["Close"],
          mode="lines",
          name="قیمت طلا (Close)",
          line=dict(color="#00ffcc", width=2),
      )
  )

  # نمایش نقاط تله نهنگ (Short) روی چارت
  shorts = chart_data[chart_data["Slaughter_Zone"]]
  if not shorts.empty:
    fig_price.add_trace(
        go.Scatter(
            x=shorts.index,
            y=shorts["Close"],
            mode="markers",
            name="⚠️ تله نهنگ (Short)",
            marker=dict(color="#ff0055", size=13, symbol="triangle-down"),
        )
    )

  # نمایش نقاط جهش انباشت (Long) روی چارت
  longs = chart_data[chart_data["Long_Zone"]]
  if not longs.empty:
    fig_price.add_trace(
        go.Scatter(
            x=longs.index,
            y=longs["Close"],
            mode="markers",
            name="🦅 جهش انباشت (Long)",
            marker=dict(color="#00ff80", size=13, symbol="triangle-up"),
        )
    )

  fig_price.update_layout(
      xaxis_title="زمان (ساعتی)",
      yaxis_title="قیمت (USD)",
      margin=dict(l=0, r=0, b=0, t=30),
      height=450,
      legend=dict(
          orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
      ),
  )
  st.plotly_chart(fig_price, use_container_width=True)

  # چارت ریتم تنفس (Breath Radius)
  st.subheader("🫁 ریتم تنفس و شعاع نوسان ارگانیسم (Breath Radius)")
  fig_rad = go.Figure()
  fig_rad.add_trace(
      go.Scatter(
          x=chart_data.index,
          y=chart_data["Breath_Radius"],
          mode="lines",
          name="شعاع تنفس",
          line=dict(color="#ff00ff", width=2),
      )
  )
  fig_rad.update_layout(
      margin=dict(l=0, r=0, b=0, t=20),
      height=250,
      yaxis_title="شدت تنفس بازار",
  )
  st.plotly_chart(fig_rad, use_container_width=True)

  st.divider()

  # جدول سوابق ارگانیک
  st.subheader("📋 سابقه فرمان‌های بیولوژیک و بررسی نتایج")
  history_df = data[data["Signal_Attempted"] == 1].tail(10)
  if not history_df.empty:
    tbl_data = {
        "زمان": history_df.index.strftime("%m-%d %H:%M"),
        "قیمت": history_df["Close"].round(2),
        "نوع فرمان": history_df["Signal_Type"],
        "شعاع تنفس": history_df["Breath_Radius"].round(1),
        "نتیجه (۵ کندل بعد)": np.where(
            history_df["Signal_Success"] == 1,
            "✅ موفق (همسو با ارگانیسم)",
            "❌ ناموفق",
        ),
    }
    tbl = pd.DataFrame(tbl_data)
    st.dataframe(tbl, use_container_width=True)
  else:
    st.write("هنوز فرمانی در این بازه ثبت نشده است.")
      
