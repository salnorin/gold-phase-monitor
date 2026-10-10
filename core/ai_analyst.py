class BiologicalAIAnalyst:

  @staticmethod
  def generate_diagnostic(latest_row):
    if latest_row['Slaughter_Zone']:
      return f"""
            * **علت سیگنال SHORT:** شعاع تنفسی (`{latest_row['Breath_Radius']:.1f}`) به ناحیه بیش‌تنشی رسیده و پمپاژ حجم رخ داده است (تله نهنگ‌ها برای خریداران هیجانی).
            * **هدف قیمتی ریزش:** پیش‌بینی می‌شود قیمت تا محدوده **`{latest_row['Target_Price']:.2f}`** اصلاح کند.
            * **نقطه ورود و استاپ:** ورود در `{latest_row['Close']:.2f}` و حد ضرر محافظتی در `{latest_row['Stop_Loss']:.2f}`.
            """
    elif latest_row['Long_Zone']:
      return f"""
            * **علت سیگنال LONG:** ارگانیسم از فاز انباشت/خواب بیدار شده و مومنتوم تتا رو به بالا شلیک شده است.
            * **هدف قیمتی صعود:** هدف صعودی ارگانیسم محدوده **`{latest_row['Target_Price']:.2f}`** است.
            * **نقطه ورود و استاپ:** ورود در `{latest_row['Close']:.2f}` و حد ضرر در `{latest_row['Stop_Loss']:.2f}`.
            """
    elif latest_row['Is_Asleep']:
      return '* **وضعیت زیستی:** ارگانیسم در خواب عمیق است. نهنگ‌ها در حال انباشت پنهان هستند. منتظر بیداری بمانید.'
    else:
      return '* **وضعیت زیستی:** جریان نقدینگی با ریتم روان و طبیعی در حال گردش است.'
      
