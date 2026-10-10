import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# تنظیمات صفحه وب
st.set_page_config(page_title="مدار معاملاتی پیشرفته طلا (4D Quant)", layout="wide")
st.title("🧬 مانیتورینگ کمّی و ارگانیک طلا (XAU/USD - Pro)")
st.write(
    "سیستم پیشرفته تریدینگ: تلفیق مدل تنفس بیولوژیک، باندهای بولینگر، RSI و"
    " مدیریت ریسک خودکار."
)


# بارگذاری و پردازش پیشرفته داده‌ها (تایم‌فریم ساعتی ریل‌تایم)
@st.cache_data(ttl=600)
def load_advanced_market_model():
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

    # ۱. شعاع تنفسی و نوسان (Volatility & Breath Radius)
    df["Volatility"] = (df["High"] - df["Low"]) / df["Close"]
    df["Breath_Radius"] = df["Volatility"].rolling(window=12).mean() * 1000

    # ۲. محاسبه RSI پیشرفته برای تأیید مومنتوم
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    # ۳. باندهای بولینگر (Bollinger Bands) برای تشخیص انبساط و فشرده‌سازی
    df["BB_Middle"] = df["Close"].rolling(window=20).mean()
    bb_std = df["Close"].rolling(window=20).std()
    df["BB_Upper"] = df["BB_Middle"] + (bb_std * 2)
    df["BB_Lower"] = df["BB_Middle"] - (bb_std * 2)

    # ۴. تشخیص خواب بازار (Market Sleep / Accumulation)
    vol_baseline = df["Volatility"].rolling(window=50).mean()
    df["Is_Asleep"] = df["Volatility"] < (vol_baseline * 0.75)

    # ۵. شناسایی منطقه کشتار نهنگ‌ها (Slaughter Zone + تایید RSI و حجم)
    avg_volume = df["Volume"].rolling(window=20).mean()
    df["Retail_FOMO"] = (df["Volume"] > (avg_volume * 1.35)) & (
        df["Close"] > df["Open"]
    )
    max_radius = df["Breath_Radius"].quantile(0.85)

    # شرط ترکیبی پیشرفته برای ورود به تله نهنگ (Short / Sell)
    df["Slaughter_Zone"] = (
        (df["Breath_Radius"] > max_radius)
        & df["Retail_FOMO"]
        & (df["RSI"] > 68)
    )

    # ۶. شرط ورود لانگ (Long / Buy) در انتهای اصلاح‌ها
    df["Long_Zone"] = (df["Close"] <= df["BB_Lower"]) & (df["RSI"] < 32)

    # ۷. تعیین نوع سیگنال و مدیریت ریسک (SL / TP)
    df["Signal_Type"] = np.where(
        df["Slaughter_Zone"],
        "🔴 SHORT (تله نهنگ / فروش)",
        np.where(
            df["Long_Zone"],
            "🟢 LONG (کف حمایتی / خرید)",
            np.where(df["Is_Asleep"], "💤 انباشت / خواب بازار", "⚪ عادی"),
        ),
    )

    # تعیین حد سود و حد ضرر پویا
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

    # ۸. اعتبارسنجی سودآوری سیگنال (بعد از ۵ کندل)
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

    df.dropna(subset=["Close", "Volume", "RSI"], inplace=True)
    return df
  except Exception as e:
    return None


data = load_advanced_market_model()

if data is None or data.empty:
  st.error("خطا در بارگذاری دیتای بازار. لطفاً صفحه را مجدد بارگذاری کنید.")
else:
  latest = data.iloc[-1]
  latest_time = data.index[-1].strftime("%m-%d %H:%M")

  # حالت‌های ارگانیسم و احساسات موجود زنده
  if latest["Slaughter_Zone"]:
    c_emoji = "👹⚡"
    c_name = "«بزکوهیِ خونخوار / تله نهنگ (Short)»"
    c_desc = (
        "بازار در اشباع خرید (RSI بالا) و هیجان کاذب است. فرصت طلایی فروش."
    )
    c_bg = "rgba(255, 0, 85, 0.12)"
    c_border = "#ff0055"
  elif latest["Long_Zone"]:
    c_emoji = "🟢🦅"
    c_name = "«عقابِ شکارچی / کف حمایتی (Long)»"
    c_desc = "قیمت به باند پایینی بولینگر رسیده و اشباع فروش است. فرصت خرید."
    c_bg = "rgba(0, 255, 128, 0.12)"
    c_border = "#00ff80"
  elif latest["Is_Asleep"]:
    c_emoji = "💤🐼"
    c_name = "«تپلوِ خواب‌آلود / سکوت مؤسساتی»"
    c_desc = "نوسان کم است؛ نهنگ‌ها در حال انباشت پنهان هستند."
    c_bg = "rgba(0, 255, 204, 0.08)"
    c_border = "#00ffcc"
  else:
    c_emoji = "✨🦊"
    c_name = "«روباهِ هوشیار / جریان طبیعی»"
    c_desc = "نقدینگی در حال گردش نرمال در بافت بازار است."
    c_bg = "rgba(0, 180, 255, 0.08)"
    c_border = "#00b4ff"

  # نمایش کارت موجود زنده با استایل امن
  st.markdown(
      f"""
    <div style="background-color: {c_bg}; border: 2px solid {c_border}; padding: 18px; border-radius: 12px; text-align: center; margin-bottom: 20px;">
        <div style="font-size: 45px;">{c_emoji}</div>
        <div style="font-size: 17px; font-weight: bold; color: #ffffff; margin-top: 6px;">وضعیت بیولوژیک: {c_name}</div>
        <div style="font-size: 13px; color: #cccccc; margin-top: 4px;">{c_desc} (زمان کندل: {latest_time})</div>
    </div>
    """,
      unsafe_allow_html=True,
  )

  # 🎯 پنل فرمان ترید و مدیریت ریسک حرفه‌ای
  st.subheader("🎯 فرمان معاملاتی پیشرفته (ترید استراتژیک)")
  if latest["Slaughter_Zone"] or latest["Long_Zone"]:
    st.warning(
        f"🚨 **سیگنال فعال:** `{latest['Signal_Type']}`\n\n"
        f"* **نقطه ورود (Entry):** `{latest['Close']:.2f}`\n"
        f"* **حد ضرر (Stop Loss):** `{latest['Stop_Loss']:.2f}`\n"
        f"* **حد سود (Take Profit):** `{latest['Take_Profit']:.2f}`\n"
        f"* **مقدار RSI فعلی:** `{latest['RSI']:.1f}`"
    )
  else:
    st.info(
        "⏳ در حال رصد ساختار بازار... منتظر فعال شدن تله نهنگ یا کف حمایتی"
        " بمانید."
    )

  st.divider()

  # متریک‌های ارزیابی عملکرد و Win Rate
  tot_sig = int(data["Signal_Attempted"].sum())
  succ_sig = int(data["Signal_Success"].sum())
  w_rate = (succ_sig / tot_sig * 100) if tot_sig > 0 else 0

  col1, col2, col3 = st.columns(3)
  col1.metric("کل سیگنال‌های صادرشده", tot_sig)
  col2.metric("سیگنال‌های موفق", succ_sig)
  col3.metric("دقت الگوریتم (Win Rate)", f"{w_rate:.1f}%")

  st.divider()

  # جدول سوابق
  st.subheader("📋 سابقه سیگنال‌های کمّی و نتایج آن‌ها")
  history_df = data[data["Signal_Attempted"] == 1].tail(10)
  if not history_df.empty:
    tbl = pd.DataFrame({
        "زمان": history_df.index.strftime("%m-%d %H:%M"),
        "قیمت": history_df["Close"].round(2),
        "نوع سیگنال": history_df["Signal_Type"],
        "RSI": history_df["RSI"].round(1),
        "نتیجه (۵ کندل بعد)": np.where(
            history_df["Signal_Success"] == 1,
            "✅ موفق (هدف محقق شد)",
            "❌ ناموفق",
        ),
    })
    st.dataframe(tbl, use_container_width=True)
  else:
    st.write("هنوز سیگنالی در این بازه ثبت نشده است.")

  st.divider()

  # چارت‌های تحلیل تکنیکال و قیمت
  st.subheader("📈 نمودار قیمت و باندهای نوسان (Bollinger & Price)")
  st.line_chart(data[["Close", "BB_Upper", "BB_Lower"]].tail(120))

  st.subheader("📊 اندیکاتور مومنتوم (RSI)")
  st.line_chart(data["RSI"].tail(120))
    
