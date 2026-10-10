import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# تنظیمات صفحه وب
st.set_page_config(page_title="مدار معاملاتی زنده طلا (4D)", layout="wide")
st.title("🧬 مانیتورینگ زنده و پنل عملیاتی سیگنال‌های طلا (XAU/USD)")
st.write(
    "سیستم بیولوژیک ریل‌تایم: تشخیص تله نهنگ‌ها، تعیین پوزیشن (Long/Short) و"
    " سطوح مدیریت ریسک."
)


# بارگذاری داده‌های ریل‌تایم (تایم‌فریم ساعتی برای رصد زنده)
@st.cache_data(ttl=600)  # هر 10 دقیقه به‌روز می‌شود
def load_realtime_market_data():
  try:
    # دریافت داده‌های ۶۰ روز اخیر با کندل‌های ۱ ساعته (کاملاً ریل‌تایم و دقیق)
    raw_data = yf.download("GC=F", period="60d", interval="1h", progress=False)
    if raw_data.empty:
      return None

    df = pd.DataFrame()
    df["Open"] = raw_data["Open"].iloc[:, 0]
    df["High"] = raw_data["High"].iloc[:, 0]
    df["Low"] = raw_data["Low"].iloc[:, 0]
    df["Close"] = raw_data["Close"].iloc[:, 0]
    df["Volume"] = raw_data["Volume"].iloc[:, 0]

    # ۱. شعاع تنفسی و نوسان (Volatility)
    df["Volatility"] = (df["High"] - df["Low"]) / df["Close"]
    df["Breath_Radius"] = df["Volatility"].rolling(window=12).mean() * 1000

    # ۲. خواب بازار (اسکلوژن مؤسساتی)
    vol_baseline = df["Volatility"].rolling(window=50).mean()
    df["Is_Asleep"] = df["Volatility"] < (vol_baseline * 0.75)

    # ۳. منطقه کشتار نهنگ‌ها (تله FOMO)
    avg_volume = df["Volume"].rolling(window=20).mean()
    df["Retail_FOMO"] = (df["Volume"] > (avg_volume * 1.35)) & (
        df["Close"] > df["Open"]
    )
    max_radius = df["Breath_Radius"].quantile(0.88)
    df["Slaughter_Zone"] = (df["Breath_Radius"] > max_radius) & (
        df["Retail_FOMO"]
    )

    # ۴. تعیین جهت پوزیشن و مدیریت ریسک
    # در منطقه کشتار، چون نهنگ‌ها در اوج خالی می‌کنند، سیگنال «شورت (فروش)» صادر می‌شود
    df["Signal_Type"] = np.where(
        df["Slaughter_Zone"],
        "🔴 SHORT (فروش / تخلیه نهنگ)",
        np.where(
            df["Is_Asleep"],
            "🟢 آماده‌باش / انباشت پنهان",
            "⚪ عادی / گردش نقدینگی",
        ),
    )

    # محاسبه حد سود (TP) و حد ضرر (SL) پویا بر اساس نوسان
    df["Stop_Loss"] = np.where(
        df["Slaughter_Zone"], df["High"] + (df["Close"] * 0.003), 0
    )
    df["Take_Profit"] = np.where(
        df["Slaughter_Zone"], df["Close"] - (df["Close"] * 0.007), 0
    )

    # ۵. اعتبارسنچی موفقیت سیگنال (۵ کندل بعد)
    df["Future_Return_5C"] = df["Close"].shift(-5) - df["Close"]
    df["Signal_Success"] = np.where(
        df["Slaughter_Zone"] & (df["Future_Return_5C"] < 0), 1, 0
    )
    df["Signal_Attempted"] = np.where(df["Slaughter_Zone"], 1, 0)

    # ۶. ابعاد مومنتوم و زمان
    df["Returns"] = df["Close"].pct_change()
    df["Theta"] = df["Returns"].cumsum() * 25
    df["Z_Time"] = np.arange(len(df))

    df.dropna(subset=["Close", "Volume"], inplace=True)
    return df
  except Exception as e:
    return None


data = load_realtime_market_data()

if data is None or data.empty:
  st.error(
      "خطا در دریافت داده‌های زنده. لطفاً چند لحظه دیگر صفحه را رفرش کنید."
  )
else:
  # آخرین وضعیت کندل زنده بازار
  latest = data.iloc[-1]
  latest_time = data.index[-1].strftime("%m-%d %H:%M")

  # تعیین موجود زنده بازار
  if latest["Slaughter_Zone"]:
    creature_emoji = "👹⚡"
    creature_name = "«بزکوهیِ خونخوار / تله نهنگ فعال!»"
    creature_mood = (
        "بازار در اوج هیجان کاذب است. نهنگ‌ها در حال توزیع و شکار پوزیشن‌های"
        " خریدِ خرده‌پاها هستند."
    )
    bg_color = "rgba(255, 0, 85, 0.15)"
    border_color = "#ff0055"
  elif latest["Is_Asleep"]:
    creature_emoji = "💤🐼"
    creature_name = "«تپلوِ خواب‌آلود / سکوت مؤسساتی»"
    creature_mood = (
        "بازار در خوابِ نوسان است؛ مؤسسات در پشت صحنه در حال انباشت پنهان"
        " هستند."
    )
    bg_color = "rgba(0, 255, 204, 0.1)"
    border_color = "#00ffcc"
  else:
    creature_emoji = "✨🦊"
    creature_name = "«روباهِ هوشیار / تنفس روان»"
    creature_mood = (
        "جریان نقدینگی به آرامی در بافت ارگانیسم در حال گردش و تنفس است."
    )
    bg_color = "rgba(0, 180, 255, 0.1)"
    border_color = "#00b4ff"

  # نمایش کارت موجود زنده
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
        margin-bottom: 20px;
    }}
    .creature-emoji {{ font-size: 50px; }}
    .creature-title {{ font-size: 18px; font-weight: bold; color: #ffffff; margin-top: 5px; }}
    .creature-desc {{ font-size: 13px; color: #dddddd; margin-top: 5px; }}
    </style>
    <div class="creature-box">
        <div class="creature-emoji">{creature_emoji}</div>
        <div class="creature-title">وضعیت زنده ارگانیسم: {creature_name}</div>
        <div class="creature-desc">{creature_mood} (آخرین بروزرسانی کندل: {latest_time})</div>
    </div>
    """,
      unsafe_allow_html=True,
  )

  # 🚨 پنل سیگنال عملیاتی لحظه‌ای برای ترید
  st.subheader("🎯 فرمان لحظه‌ای ترید و مدیریت ریسک")
  if latest["Slaughter_Zone"]:
    st.error(
        f"🚨 **سیگنال فعال (SHORT / فروش):** قیمت در مقاومت حیاتی و تله نهنگ"
        f" قرار دارد!\n\n"
        f"* **قیمت ورود پیشنهادی:** `{latest['Close']:.2f}`\n"
        f"* **حد ضرر (Stop Loss):** `{latest['Stop_Loss']:.2f}`\n"
        f"* **حد سود (Take Profit):** `{latest['Take_Profit']:.2f}`"
    )
  elif latest["Is_Asleep"]:
    st.info(
        "💤 **وضعیت ان
      
