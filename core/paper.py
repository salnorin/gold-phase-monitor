# core/paper.py
"""
موتور معامله‌ی کاغذی با اهرم (فقط شبیه‌سازی — هیچ سفارش واقعی، هیچ کلید صرافی).
مدل سخت‌گیرانه‌ی اهرم ۲۰x:
  - مارجین ایزوله = notional / leverage  (۲۰x → ۵٪)
  - لیکوئید وقتی حرکت مخالف به (1/leverage − maintenance) برسد (≈ ۵٪ − ۰٫۵٪ = ۴٫۵٪)
  - بررسی درون‌کندلی با High/Low (فتیله‌ها هم لیکوئید می‌کنند)؛ اگر استاپ و لیکوئید هر دو لمس شوند،
    نزدیک‌ترین به ورود اول رخ داده فرض می‌شود؛ گپ Open فراتر از هر دو → در Open بسته/لیکوئید
  - کارمزد روی notional در ورود و خروج، فاندینگ/هزینه‌ی شبانه به نسبت زمان، اسپرد+اسلیپیج متناسب با نوسان
  - بدون میانگین‌گیری کاهشی (یک پوزیشن، بدون افزودن)
"""
from dataclasses import dataclass, field
import numpy as np

MAX_LEVERAGE = 20.0


@dataclass
class CostModel:
    leverage: float = 20.0
    maintenance: float = 0.005        # ۰٫۵٪ مارجین نگهداری
    fee_rate: float = 0.0005          # ۰٫۰۵٪ کارمزد taker روی notional در هر طرف
    funding_rate_8h: float = 0.0001   # ۰٫۰۱٪ هر ۸ ساعت روی notional
    base_spread: float = 0.0001       # نیم‌اسپرد پایه ۰٫۰۱٪
    vol_slippage: float = 0.10        # اسلیپیج = ۰٫۱ × (ATR/قیمت)
    bar_hours: float = 1.0

    def __post_init__(self):
        if not (1.0 <= self.leverage <= MAX_LEVERAGE):
            raise ValueError(f"اهرم باید بین ۱ و {MAX_LEVERAGE} باشد")

    def slip(self, price, atr):
        return price * self.base_spread + atr * self.vol_slippage

    @property
    def liq_move(self):
        return 1.0 / self.leverage - self.maintenance


@dataclass
class Position:
    direction: int
    entry: float
    qty: float
    margin: float
    stop: float
    target: float
    liq: float
    open_index: int
    open_time: object = None
    fees: float = 0.0
    funding: float = 0.0
    bars: int = 0
    context: dict = field(default_factory=dict)
    exit: float = None
    exit_index: int = None
    exit_time: object = None
    reason: str = ""
    pnl: float = 0.0
    risk_cash: float = 0.0

    @property
    def notional(self):
        return self.qty * self.entry

    @property
    def r_multiple(self):
        return self.pnl / self.risk_cash if self.risk_cash else 0.0


def open_position(cm: CostModel, equity, direction, raw_open, atr, stop_dist, target_dist,
                  risk_frac=None, margin_frac=None, index=0, time=None, context=None):
    """اندازه‌ی پوزیشن: یا با ریسک (risk_frac از equity تا استاپ) یا با سهم مارجین؛ هرگز بیش از equity مارجین."""
    if equity <= 0 or stop_dist <= 0:
        return None
    entry = raw_open + direction * cm.slip(raw_open, atr)
    if margin_frac is not None:
        margin = equity * min(1.0, margin_frac)
        qty = margin * cm.leverage / entry
    else:
        qty = equity * risk_frac / stop_dist
        margin = qty * entry / cm.leverage
        if margin > equity:  # سقف اهرم
            margin = equity
            qty = margin * cm.leverage / entry
    fee = qty * entry * cm.fee_rate
    liq = entry * (1 - direction * cm.liq_move)
    p = Position(direction, entry, qty, margin, entry - direction * stop_dist, entry + direction * target_dist,
                 liq, index, time, fees=fee, context=context or {})
    p.risk_cash = qty * stop_dist + 2 * fee
    return p


def step_position(cm: CostModel, p: Position, o, h, l, c, atr, max_hold, index=0, time=None):
    """یک کندل را روی پوزیشن اعمال می‌کند. True اگر بسته شد."""
    p.bars += 1
    p.funding += p.qty * c * cm.funding_rate_8h * cm.bar_hours / 8.0
    d = p.direction
    adverse = l if d > 0 else h
    favorable = h if d > 0 else l

    def beyond(level, px):  # آیا px از سطح مخالف رد شده؟
        return (px <= level) if d > 0 else (px >= level)

    exit_px, why = None, None
    # سطحی که زودتر لمس می‌شود (نزدیک‌تر به ورود در جهت ضرر)
    first_px, first_why = max([(p.stop, "stop"), (p.liq, "liquidation")], key=lambda t: d * t[0])
    if beyond(first_px, o):                       # گپ در Open
        exit_px = o
        why = "liquidation" if beyond(p.liq, o) else ("gap_stop" if first_why == "stop" else "liquidation")
    elif beyond(first_px, adverse):               # فتیله‌ی درون‌کندلی (محافظه‌کارانه: قبل از تارگت)
        exit_px, why = first_px, first_why
    elif (favorable >= p.target) if d > 0 else (favorable <= p.target):
        exit_px, why = p.target, "target"
    elif p.bars >= max_hold:
        exit_px, why = c, "time"
    if exit_px is None:
        return False
    p.exit_index, p.exit_time, p.reason = index, time, why
    if why == "liquidation":
        p.exit = p.liq
        p.pnl = -p.margin - p.fees - p.funding
    else:
        fill = exit_px - d * cm.slip(exit_px, atr)
        p.exit = fill
        exit_fee = p.qty * fill * cm.fee_rate
        p.fees += exit_fee
        gross = p.qty * (fill - p.entry) * d
        p.pnl = max(gross, -p.margin) - p.fees - p.funding
    return True
