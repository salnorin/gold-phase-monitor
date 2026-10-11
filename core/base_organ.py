class BaseOrgan:
  """قالب ژنتیکی استاندارد برای تمام ارگان‌های ارگانیسم"""

  def __init__(self, name):
    self.name = name
    self.is_active = True

  def process(self, market_data):
    raise NotImplementedError(
        "هر ارگان جدید باید روش پردازش خود را پیاده‌سازی کند!"
    )
    
