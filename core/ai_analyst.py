import numpy as np


class OrganicObserver:
  """
  مغز هوش مصنوعی و ناظر مرکزی (AI Brain):
  علاوه بر موتور و تنفس، اکنون فرمان‌های سیستم ایمنی (Antibody) و هورمون استرس (Cortisol)
  را دریافت می‌کند تا در مواقع خطر، مغز را به حالت بقا (Fight or Flight) ببرد.
  """

  @staticmethod
  def observe_and_synthesize(latest_row, historical_win_rate):
    motor_drive = latest_row.get("Motor_Drive", 0.0)
    atp = latest_row.get("ATP_Energy", 100.0)
    optical_pull = latest_row.get("Optical_Pull", 0.0)
    breath = latest_row.get("Weighted_Breath", 1.0)

    # سیگنال‌های حیاتی سیستم ایمنی و استرس
    cortisol = latest_row.get("Cortisol_Stress", 10.0)
    antibody = latest_row.get("Antibody_Defense", 0.0)
    stress_state = latest_row.get("Stress_State", "CALM")

    plasticity = (
        historical_win_rate / 100.0 if historical_win_rate > 0 else 0.5
    )

    # تنسور جعبه سیاه تحت تاثیر مستقیم کورتیزول و شوک‌های ایمنی
    latent_tensor = np.tanh(
        (breath - 1.0) * (plasticity * 2.0)
        + (optical_pull * 0.8)
        - ((100.0 - atp) * 0.02)
        - (cortisol * 0.01)  # استرس بالا تنسور را سرکوب و محافظه‌کار می‌کند
    )

    if cortisol > 70.0 or stress_state == "PATHOGEN_ALERT":
      conviction = (
          "🚨 [وضعیت بقا / کورتیزول بحرانی]: سیستم ایمنی حمله پاتوژن (فیک‌بریک‌اوت)"
          " را شناسایی کرده و کورتیزول مغز را قفل کرده است (دستور به دفاع"
          " مطلق)."
      )
    elif atp < 35.0:
      conviction = (
          "هشدار انرژی: ارگانیسم با کمبود ATP روبه‌روست؛ قدرت شنا کردن به سمت"
          " نور نقدینگی وجود ندارد."
      )
    elif latent_tensor > 0.35:
      conviction = (
          "شهود مغز: هارمونی کامل بین موتور، ریه و نور نقدینگی برای حرکت"
          " ارگانیک."
      )
    else:
      conviction = "شهود مغز: تعادل هموستاتیک و پایش لایه‌های پنهان بازار."

    return plasticity, latent_tensor, cortisol, antibody, stress_state, conviction


class BiologicalAIAnalyst:

  @staticmethod
  def generate_diagnostic(latest_row, historical_win_rate=50.0):
    plasticity, tensor, cortisol, antibody, stress_state, conviction = (
        OrganicObserver.observe_and_synthesize(latest_row, historical_win_rate)
    )

    # ۱. اگر سیستم ایمنی یا کورتیزول بحرانی باشد، مغز فرمانِ قرنطینه و دفاع صادر می‌کند
    if cortisol > 70.0 or stress_state == "PATHOGEN_ALERT":
      return f"""
            🛡️ **[مغز هوش مصنوعی در وضعیت بقا و دفاع بیولوژیک]**
            * **هورمون استرس (Cortisol):** `{cortisol:.1f}/100` (سطح هشدار بحرانی).
            * **پاسخ سیستم ایمنی:** ترشح فعال آنتی‌بادی دفاعی (`Antibody: {antibody:.1f}`). فیک‌بریک‌اوت یا دستکاری نهنگ شناسایی شد.
            * **تحلیل مغز:** مغز فرمانِ صادر شده از سوی استرس را دریافت کرده و به دلیل سمومِ موجود در بافت بازار، تمام پوزیشن‌ها را تعلیق می‌کند تا از مسمومیت مالی جلوگیری شود.
            * **📍 فرمان نهایی:** **قرنطینه و استراحت مطلق (بدون معامله)** تا پاکسازی کامل بافت بازار.
            """

    if atps := latest_row.get("ATP_Energy", 100.0) < 35.0:
      return f"""
            👁️‍🗨️ **[مانیتورینگ مغز و سیستم اپتیکی]**
            * **سطح انرژی:** ATP بسیار پایین (`{atps:.1f}%`). مغز تشخیص داده که ارگانیسم توان شنا کردن به سمت نور نقدینگی را ندارد.
            * **📍 فرمان:** توقف و ریکاوری انرژی.
            """

    if latest_row.get("Slaughter_Zone", False) or tensor < -0.3:
      return f"""
            🧠 **[مغز خودآگاه و ناظرِ جعبه سیاه]**
            * **وضعیت هورمونی:** کورتیزول نرمال (`{cortisol:.1f}`) | سیستم ایمنی پایدار.
            * **تحلیل دیالکتیک:** تله نوری نهنگ و تب ویروسی شناسایی شد. مغز با تکیه بر تجربه گذشته فرمانِ شکار صادر می‌کند.
            * **📍 فرمان نقطه‌زن بیولوژیک:** شلیک پوزیشن **SHORT (فروش)** در قیمت `{latest_row['Close']:.2f}` | **حد ضرر:** `{latest_row['Stop_Loss']:.2f}` | **تارگت ریزش:** `{latest_row['Target_Price']:.2f}`
            """

    elif latest_row.get("Long_Zone", False) or tensor > 0.3:
      return f"""
            🧠 **[مغز خودآگاه و ناظرِ جعبه سیاه]**
            * **وضعیت هورمونی:** کورتیزول آرام (`{cortisol:.1f}`) | درایو موتور پایا.
            * **تحلیل دیالکتیک:** رشد ارگانیک و حرکت به سمت نور واقعی نقدینگی تایید شد.
            * **📍 فرمان نقطه‌زن بیولوژیک:** شلیک پوزیشن **LONG (خرید)** در قیمت `{latest_row['Close']:.2f}` | **حد ضرر:** `{latest_row['Stop_Loss']:.2f}` | **تارگت صعود:** `{latest_row['Target_Price']:.2f}`
            """

    else:
      return f"""
            🧠 **[مغز خودآگاه و ناظرِ جعبه سیاه]**
            * سیستم در حالت تعادل هموستاتیک است. کورتیزول: `{cortisol:.1f}` | تنسور جعبه سیاه: `{tensor:.2f}`. مغز در حال پایش لحظه‌ای است.
            """
