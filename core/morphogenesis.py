import importlib
import os
import re


class MorphogenesisManager:
    """مدیر ریخت‌زایی. نوشتن و اجرای کد دلخواه به‌صورت پیش‌فرض غیرفعال است (ریسک اجرای کد)."""

    ENV_FLAG = "GPM_ALLOW_DYNAMIC_ORGANS"

    def __init__(self, organs_dir="core/organs"):
        self.organs_dir = organs_dir
        self.active_organs = {}

    def spawn_new_organ(self, organ_name, organ_code_string):
        if os.getenv(self.ENV_FLAG) != "1":
            raise PermissionError(
                "spawn_new_organ غیرفعال است: اجرای کد دلخواه خطرناک است. "
                f"فقط برای توسعه‌ی محلی با {self.ENV_FLAG}=1 فعال کنید."
            )
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", organ_name):
            raise ValueError("نام ارگان نامعتبر است")
        os.makedirs(self.organs_dir, exist_ok=True)
        with open(os.path.join(self.organs_dir, f"{organ_name}.py"), "w", encoding="utf-8") as f:
            f.write(organ_code_string)
        module = importlib.import_module(f"core.organs.{organ_name}")
        instance = getattr(module, organ_name)()
        self.active_organs[organ_name] = instance
        return instance

    def run_all_organs(self, market_data):
        return {n: o.process(market_data) for n, o in self.active_organs.items() if o.is_active}
