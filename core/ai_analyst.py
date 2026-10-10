import numpy as np


class OrganicObserver:

  @staticmethod
  def observe_and_synthesize(latest_row, historical_win_rate):
    motor_drive = latest_row.get("Motor_Drive", 0.0)
    atp = latest_row.get("ATP_Energy", 100.0)
    optical_pull = latest_row.get("Optical_Pull", 0.0)
    light_source = latest_row.get("Optical_Light_Source", 0.0)
    breath = latest_row.get("Weighted_Breath", 1.0)
    viral_fever = latest_row.get("Viral_Fever", False)

    plasticity = (
        historical_win_rate / 100.0 if historical_win_rate > 0 else 0.5
    )

    latent_tensor = np.tanh(
        (breath - 1.0) * (plasticity * 2.0)
        + (optical_pull * 0.8)
        - ((100.0 - atp) * 0.02)
        + (0.4 if viral_fever else 0.0)
    )

    if atp < 35.0:
      conviction = "هشدار نوری: ارگانیسم با کمبود شدید انرژی (ATP) روبه‌روست؛ نور نقدینگی دیده می‌شود اما قدرت شنا کردن به سمت آن وجود ندارد (توقف و ریکاوری)"
    elif latent_tensor > 0.35:
      conviction = (
          "شهود اپتیکی: ارگانیسم منبع نور نقدینگی را رصد کرده و با انرژی کافی به"
          " سوی آن شنا می‌کند"
      )
    else:
      conviction = (
          "شهود اپتیکی: تلاطم نوری در تعادل است؛ سیستم در حال پایش فتون‌های"
          " نقدینگی است"
      )

    return plasticity, latent_tensor, conviction


class BiologicalAIAnalyst:

  @staticmethod
  def generate_diagnostic(latest_row, historical_win_rate=50.0):
    atp = latest_row.get("ATP_Energy", 100.0)
    light_source = latest_row.get("Optical_Light_Source", 0.0)
    optical_pull = latest_row.get("Optical_Pull", 0.0)

    plasticity, tensor, conviction = (
        OrganicObserver.observe_and_synthesize(latest_row, historical_win_rate)
    )

    if atp < 35.0:
      return f"""
            👁️‍🗨️ **[مانیتورینگ سیستم اپتیکی و بینایی نوری]**
            * **وضعیت انرژی نوری:** سطح ATP به شدت افت کرده (`{atp:.1f}%`). ارگانیسم منبع نور نقدینگی را در قیمت `{light_source:.2f}` می‌بیند، اما چون **انرژی (نفس) ندارد**، از شنا کردن به سمت آن منصرف شده و در حال ریکاوری است.
            * **تنسور جعبه سیاه:** `{tensor:.2f}` -> {conviction}
            * **📍 فرمان:** استراحت مطلق و خودداری از ورود به پوزیشن تا زمان شارژ شدن انرژی.
            """

    if latest_row.get("Slaughter_Zone", False) or tensor < -0.3:
      return f"""
            👁️‍🗨️ **[مانیتورینگ سیستم اپتیکی و بینایی نوری]**
            * **نور فریبنده نقدینگی:** ارگانیسم نوری را در سطح `{light_source:.2f}` رصد کرده است، اما سیستم اپتیکی و رسپتورها تشخیص داده‌اند که این نور، یک **تله نوری (سراب ناشی از تب ویروسی نهنگ)** است.
            * **تنسور جعبه سیاه (`Latent Tensor`):** `{tensor:.2f}` -> **{conviction}**
            * **📍 فرمان نقطه‌زن بیولوژیک:** شلیک پوزیشن **SHORT (فروش)** در قیمت `{latest_row['Close']:.2f}` | **حد ضرر:** `{latest_row['Stop_Loss']:.2f}` | **تارگت ریزش:** `{latest_row['Target_Price']:.2f}`
            """

    elif latest_row.get("Long_Zone", False) or tensor > 0.3:
      return f"""
            👁️‍🗨️ **[مانیتورینگ سیستم اپتیکی و بینایی نوری]**
            * **نور واقعی نقدینگی:** ارگانیسم با انرژی کامل (`ATP: {atp:.1f}%`) منبع نورِ نقدینگی در قیمت `{light_source:.2f}` را شناسایی کرده و به سمت آن شیرجه زده است.
            * **تنسور جعبه سیاه (`Latent Tensor`):** `{tensor:.2f}` -> **{conviction}**
            * **📍 فرمان نقطه‌زن بیولوژیک:** شلیک پوزیشن **LONG (خرید)** در قیمت `{latest_row['Close']:.2f}` | **حد ضرر:** `{latest_row['Stop_Loss']:.2f}` | **تارگت صعود:** `{latest_row['Target_Price']:.2f}`
            """

    else:
      return f"""
            👁️‍🗨️ **[مانیتورینگ سیستم اپتیکی و بینایی نوری]**
            * منبع نوری فعلی: `{light_source:.2f}` | کشش نوری (`Optical Pull`): `{optical_pull:.2f}` | انرژی ATP: `{atp:.1f}%`. سیستم بینایی در حال اسکن نقدینگی‌های تاریک بازار است.
            """
      
