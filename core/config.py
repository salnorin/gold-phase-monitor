# core/config.py
"""تمام آستانه‌ها و پارامترهای ارگانیسم در یک جا (قابل تنظیم)."""
from dataclasses import dataclass, field

# ---- سرمایه‌ی مجازی (فقط کاغذی) — برای تغییر، فقط همین سه عدد را عوض کنید ----
# «مصرف انرژی»: کارمزد هر باز و هر بستن، از سرمایه‌ی کاغذی کم می‌شود (همه‌ی tierها)، روی اسلیپیج/کارمزد قبلی
ENERGY_FEE_PCT = 0.20          # درصد در هر طرف (۲۰ واحد پایه باز + ۲۰ بستن ≈ ۰٫۴۰٪ رفت‌وبرگشت)
ENERGY_FEE_MODE = "margin"     # margin: درصدی از مارجین/سرمایه‌ی درگیر | notional: درصدی از ارزش اسمی
# پیش‌تنظیم «آزمون دستی» کاغذی: ریسک ثابت ۲ یورو، نسبت سود به ضرر ۱:۱ (SL ≈ ۲ €، TP ≈ ۲ €) — فقط شبیه‌سازی
MANUAL_TEST_RISK_EUR = 2.0
MANUAL_TEST_RR = 1.0
PAPER_CAPITAL_EUR = 540.16        # سقف پایه به یورو؛ دلار با نرخ زنده‌ی EUR/USD محاسبه می‌شود (core/fx.py)
MAX_RISK_PER_TRADE = 0.01         # حداکثر ریسک هر معامله = ۱٪ سقف
AUTO_STOP_FRACTION = 0.70         # توقف خودکار در ۷۰٪ سقف


@dataclass
class OrganismConfig:
    # --- داده ---
    symbol: str = "GC=F"
    interval: str = "1h"
    lookback_days: int = 60

    # --- اندازه‌گیری ---
    atr_period: int = 14
    target_atr_mult: float = 1.8   # تارگت = 1.8 × ATR
    stop_atr_mult: float = 1.0     # استاپ = 1.0 × ATR
    max_hold_bars: int = 24        # حداکثر نگهداری پوزیشن (کندل)

    # --- تصمیم‌گیری مغز ---
    require_respiration: bool = True  # فقط وقتی تنفس منطقه‌ی فعال دارد
    cost_frac: float = 0.0001         # هزینه‌ی رفت‌وبرگشت ≈ ۰٫۰۱٪ قیمت (~۰٫۴ دلار در طلا)
    min_score: float = 0.35        # حداقل قدرت رأی وزن‌دار ارگان‌ها
    min_confidence: float = 0.20   # حداقل اطمینان پس از هموستاز
    atp_floor: float = 30.0        # زیر این ATP سیگنال نمی‌دهد
    cortisol_ceiling: float = 75.0 # بالای این کورتیزول سیگنال نمی‌دهد

    # --- هموستاز ---
    atp_stress_point: float = 40.0     # کمتر از این ATP → کورتیزول بالا می‌رود
    atp_to_cortisol: float = 0.5
    cortisol_to_atp: float = 0.005     # هر واحد کورتیزول ATP مؤثر را کم می‌کند

    # --- یادگیری (فقط از معاملات بسته‌شده گذشته) ---
    learning_rate: float = 0.15        # ضریب EWMA عملکرد هر ارگان
    weight_min: float = 0.2
    weight_max: float = 2.0
    initial_weights: dict = field(default_factory=lambda: {
        "respiration": 1.0, "optical": 0.6, "motor": 0.8, "cross": 0.0,
    })

    # --- خستگی / خواب ---
    fatigue_per_loss: float = 0.2
    fatigue_recovery: float = 0.02     # بهبود خستگی در هر کندل
    losses_to_sleep: int = 3
    sleep_bars: int = 12

    # --- رابط کاربری ---
    refresh_seconds: int = 240


DEFAULT_CONFIG = OrganismConfig()
