import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# تنظیمات صفحه وب
st.set_page_config(page_title="مدار پادشکننده تکاملی طلا", layout="wide")
st.title("🧬 مانیتورینگ ۳بعدی فازسنج و اعتبارسنجهای هوشمند طلا")
st.write(
    "سیستمِ بیولوژیکِ بازار: تحلیل تنفس، تله‌های نهنگ‌ها و **ارزیابی خودکار"
    " صحت سیگنال‌ها**."
)


# بارگذاری، پردازش و اعتبارسنجی سیگنال‌ها
@st.cache_data
def load_and_validate_model():
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

    # ۱. شعاع تنفسی بازار (Volatility)
    df["Volatility"] = (df["High"] - df["Low"]) / df["Close"]
    df["Breath_Radius"] = df["Volatility"].rolling(window=12).mean() * 1000

    # ۲. خواب بازار و بیداری مؤسسات
    vol_baseline = df["Volatility"].rolling(window=50).mean()
    df["Is_Asleep"] = df["Volatility"] < (vol_baseline * 0.75)

    # ۳. شناسایی منطقه کشتار نهنگ‌ها (Slaughter Zone)
    avg_volume = df["Volume"].rolling(window=20).mean()
    df["Retail_FOMO"] = (df["Volume"] > (avg_volume * 1.4)) & (
        df["Close"] > df["Open"]
    )
    max_radius = df["Breath_Radius"].quantile(0.88)
    df["Slaughter_Zone"] = (df["Breath_Radius"] > max_radius) & (
        df["Retail_FOMO"]
    )

    # ۴. اعتبارسنجی سیگنال‌ها (آیا سیگنال درست بوده یا غلط؟)
    # بررسی قیمت ۵ کندل بعد از صدور سیگنال کشتار (آیا قیمت افت کرده؟)
    df["Future_Return_5C"] = df["Close"].shift(-5) - df["Close"]
    # اگر در منطقه کشتار بودیم و قیمت بعد از ۵ کندل منفی شد -> سیگنال درست (1)، در غیر این صورت خطا (0)
    df["Signal_Success"] = np.where(
        df["Slaughter_Zone"] & (df["Future_Return_5C"] < 0), 1, 0
    )
    df["Signal_Attempted"] = np.where(df["Slaughter_Zone"], 1, 0)

    # ۵. ساخت مختصات مارپیچی (Helical Phase-Space)
    df["Returns"] = df["Close"].pct_change()
    df["Theta"] = df["Returns"].cumsum() * 25
    df["Z_Time"] = np.arange(len(df))

    df.dropna(subset=["Close", "Volume"], inplace=True)
    return df
  except Exception as e:
    return None


data = load_and_validate_model()

if data is None or data.empty:
  st.error(
      "خطا در پردازش داده‌ها. لطفاً چند لحظه دیگر صفحه را مجدد بارگذاری کنید."
  )
else:
  # محاسبه آمار دقت سیگنال‌ها
  total_signals = data["Signal_Attempted"].sum()
  successful_signals = data["Signal_Success"].sum()
  win_rate = (
      (successful_signals / total_signals * 100) if total_signals > 0 else 0
  )

  # نمایش متریک‌های ارزیابی در بالای صفحه
  col1, col2, col3 = st.columns(3)
  col1.metric(
      label="تعداد کل سیگنال‌های صادر شده", value=int(total_signals)
  )
  col2.metric(label="سیگنال‌های موفق (تاییدشده)", value=int(successful_signals))
  col3.metric(label="نرخ دقت سیستم (Win Rate)", value=f"{win_rate:.1f}%")

  st.divider()

  # تفکیک نقاط برای نمودار سه‌بعدی
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
          line=dict(color="#00ffcc", width=4),
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
            marker=dict(size=7, color="#ff0055", symbol="diamond"),
            name="⚠️ منطقه کشتار نهنگ‌ها",
        )
    )

  fig.update_layout(
      title="مدار ۳بعدی فازسنج طلا و نقاط ارزیابی‌شده",
      scene=dict(
          xaxis_title="فاز افقی (X)",
          yaxis_title="فاز عمودی (Y)",
          zaxis_title="محور زمان (Z)",
      ),
      margin=dict(l=0, r=0, b=0, t=40),
      height=650,
  )

  st.plotly_chart(fig, use_container_width=True)

  # گزارش وضعیت زنده
  st.subheader("📊 تحلیل وضعیت لحظه‌ای سیستم")
  latest = data.iloc[-1]
  if latest["Slaughter_Zone"]:
    st.error(
        "⚠️ هشدار حیاتی: ارگانیسم در اوج هیجان است و بازار در «منطقه کشتار"
        " نهنگ‌ها» قرار دارد!"
    )
  elif latest["Is_Asleep"]:
    st.info(
        "💤 وضعیت: بازار در خواب عمیق و سکوت است؛ مؤسسات در حال انباشت پنهان"
        " هستند."
    )
  else:
    st.success(
        "✅ وضعیت: ارگانیسم در فاز تنفس طبیعی و گردش جریان نقدینگی است."
    )
