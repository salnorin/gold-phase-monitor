import numpy as np


class OrganicObserver:

  @staticmethod
  def observe_and_synthesize(latest_row, historical_win_rate=50.0):
    motor_drive = latest_row.get("Motor_Drive", 0.0)
    atp = latest_row.get("ATP_Energy", 100.0)
    optical_pull = latest_row.get("Optical_Pull", 0.0)
    breath = latest_row.get("Weighted_Breath", 1.0)

    # دریافت سیگنال‌های ایمنی و استرس (کورتیزول)
    cortisol = latest_row.get("Cortisol_Stress", 10.0)
    antibody = latest_row.get("Antibody_Defense", 0.0)
    stress_state = latest_row.get("Stress_State", "CALM")

    plasticity = (
        historical_win_rate / 100.0 if historical_win_rate > 0 else 0.5
    )

    latent_tensor = np.tanh(
        (breath - 1.0) * (plasticity * 2.0)
        + (optical_pull * 0.8)
        - ((100.0 - atp) * 0.02)
        - (cortisol * 0.01)
    )

    return plasticity, latent_tensor, cortisol, antibody, stress_state


class BiologicalAIAnalyst:

  @staticmethod
  def generate_diagnostic(latest_row, historical_win_rate=50.0):
    plasticity, tensor, cortisol, antibody, stress_state = (
        OrganicObserver.observe_and_synthesize(latest_row, historical_win_rate)
    )

    # اصلاح باگ سینتکسی ATP و بررسی وضعیت بحرانی ایمنی
    atps = latest_row.get("ATP_Energy", 100.0)

    if cortisol > 70.0 or stress_state == "PATHOGEN_ALERT":
      return (
          "🛡️ **[وضعیت بقا]:** سیستم ایمنی حمله پاتوژن را شناسایی کرده و کورتیزول"
          " مغز را قفل کرده است (دستور به دفاع مطلق و قرنطینه)."
      )

    if atps < 35.0:
      return (
          "👁️‍🗨️ **[هشدار انرژی]:** سطح ATP بسیار پایین است (`"
          f"{atps:.1f}%`). ارگانیسم نیاز به استراحت و ریکاوری دارد."
      )

    if tensor > 0.3:
      return (
          "🧠 **[فرمان مغز]:** هارمونی ارگانیک تأیید شد. سیگنال **LONG** فعال"
          f" است (تنسور: {tensor:.2f})."
      )
    elif tensor < -0.3:
      return (
          "🧠 **[فرمان مغز]:** تله نوری شناسایی شد. سیگنال **SHORT** فعال است"
          f" (تنسور: {tensor:.2f})."
      )
    else:
      return (
          "🧠 **[وضعیت هموستاتیک]:** بازار در تعادل است؛ مغز در حال پایش لحظه‌ای"
          " است."
      )
