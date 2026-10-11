import importlib
import os


class MorphogenesisManager:
  """مدیر تکامل و ریخت‌زایی (تولد ارگان‌های جدید بر اساس نیاز محیطی)"""

  def __init__(self, organs_dir="core/organs"):
    self.organs_dir = organs_dir
    os.makedirs(self.organs_dir, exist_ok=True)
    self.active_organs = {}

  def spawn_new_organ(self, organ_name, organ_code_string):
    """
    تولد یک ارگان جدید: کد پایتون آن را روی دیسک می‌نویسد،
    آن را بارگذاری کرده و به عنوان عضو جدید به ارگانیسم پیوند می‌زند.
    """
    file_path = os.path.join(self.organs_dir, f"{organ_name}.py")

    # ۱. تولید کالبد فیزیکی ارگان (نوشتن فایل کد روی دیسک)
    with open(file_path, "w", encoding="utf-8") as f:
      f.write(organ_code_string)

    # ۲. بارگذاری پویا و زنده کردن ارگان (Dynamic Import)
    module_name = f"core.organs.{organ_name}"
    if module_name in globals():
      module = importlib.reload(globals()[module_name])
    else:
      module = importlib.import_module(module_name)

    # ۳. متولد کردن کلاس ارگان
    organ_class = getattr(module, organ_name)
    new_organ_instance = organ_class()

    # ۴. اتصال به شبکه عصبی ارگانیسم
    self.active_organs[organ_name] = new_organ_instance
    print(
        f"✨ [تکامل پویا]: ارگان جدیدِ '{organ_name}' با موفقیت متولد شد و به"
        " شبکه متصل گردید!"
    )
    return new_organ_instance

  def run_all_organs(self, market_data):
    """اجرای هم‌زمان تمام ارگان‌های بدن (قدیمی و جدید)"""
    results = {}
    for name, organ in self.active_organs.items():
      if organ.is_active:
        results[name] = organ.process(market_data)
    return results
