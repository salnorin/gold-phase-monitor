# core/research.py
"""
تحقیق پارامتر بدون نشت:
  ۱. داده به IS (۷۰٪ اول) و OOS (۳۰٪ آخر) تقسیم می‌شود. OOS تا انتها دست‌نخورده می‌ماند.
  ۲. جستجوی شبکه‌ای فقط روی IS؛ IS به ۳ بخش زمانی پیاپی تقسیم و هر ترکیب روی هر بخش سنجیده می‌شود.
     امتیاز = میانه‌ی avg R بخش‌ها (پایداری) با حداقل تعداد معامله.
  ۳. بهترین ترکیب یک بار روی OOS اجرا می‌شود (مغز از ابتدای داده آنلاین گرم می‌شود، ولی فقط معاملات OOS شمرده می‌شوند).
  ۴. مبنا: خرید و نگهداری، و ورود تصادفی با همان خروج‌ها (همان تعداد معامله، ۵۰۰ بار).
اجرا: python -m core.research --symbol GC=F --interval 15m [--cross SI=F] [--csv-dir /tmp/gd]
"""
import argparse, itertools, os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import numpy as np
import pandas as pd

from core.backtest import metrics, simulate
from core.brain import Brain
from core.config import OrganismConfig
from core.organism import BiologicalOrganism

BAR_HOURS = {"1m": 1 / 60, "5m": 5 / 60, "15m": 0.25, "30m": 0.5, "1h": 1.0, "1d": 24.0}
PERIOD = {"1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d", "1h": "730d", "1d": "max"}

GRID = {
    "min_score": [0.2, 0.35, 0.5],
    "min_confidence": [0.05, 0.2],
    "target_atr_mult": [1.0, 1.8, 3.0],
    "stop_atr_mult": [0.75, 1.5],
    "max_hold_bars": [12, 48],
    "require_respiration": [True, False],
    "cross_weight": [0.0, 0.6],
}


def load(symbol, interval, csv_dir=None):
    path = os.path.join(csv_dir, f"{symbol}_{interval}.csv") if csv_dir else None
    if path and os.path.exists(path):
        df = pd.read_csv(path, index_col=0)
    elif symbol in ("PAXG-USD", "GOLD"):
        from core import gold_price
        return gold_price.candles(interval, 13_000 if interval == "1h" else 3000)
    else:
        import yfinance as yf
        df = yf.download(symbol, period=PERIOD[interval], interval=interval, progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.index = pd.to_datetime(df.index, utc=True).tz_convert("America/New_York")
    from core.market_hours import drop_forming_candle
    return drop_forming_candle(df, BAR_HOURS[interval])


def add_cross(feat, cross_raw, lookback=4, tolerance=None):
    """رأی متقاطع علّی: z-score بازده lookback کندلی نماد دیگر، فقط کندل‌های بسته‌شده (merge_asof به عقب)."""
    c = cross_raw["Close"]
    r = np.log(c / c.shift(lookback))
    z = (r / r.rolling(200, min_periods=20).std()).rename("cz").to_frame()
    m = pd.merge_asof(feat[[]].reset_index(), z.reset_index(), left_on=feat.index.name or "index",
                      right_on=z.index.name or "index", direction="backward",
                      tolerance=tolerance if tolerance is not None else _bar_len(feat.index))
    feat = feat.copy()
    feat["Cross_Drive"] = np.tanh(m["cz"].fillna(0).values / 2)
    return feat


def _bar_len(idx):
    return pd.Series(idx).diff().median() if len(idx) > 1 else pd.Timedelta(hours=1)


def make_cfg(base, p):
    p = dict(p); cw = p.pop("cross_weight")
    w = dict(base.initial_weights); w["cross"] = cw
    return replace(base, initial_weights=w, **p)


def _eval(args):
    feat, cut_points, base, p = args
    _, trades = Brain(make_cfg(base, p)).run(feat)
    folds = [[t for t in trades if a <= t.signal_time < b] for a, b in zip(cut_points[:-1], cut_points[1:])]
    ms = [metrics(f) for f in folds]
    return p, ms


def search(feat_is, base, min_trades_per_fold=5, workers=None):
    idx = feat_is.index
    cuts = [idx[0]] + [idx[int(len(idx) * k / 3)] for k in (1, 2)] + [pd.Timestamp(idx[-1]) + pd.Timedelta(seconds=1)]
    keys = list(GRID)
    combos = [dict(zip(keys, v)) for v in itertools.product(*GRID.values())]
    with ProcessPoolExecutor(workers) as ex:
        res = list(ex.map(_eval, [(feat_is, cuts, base, p) for p in combos], chunksize=4))
    rows = []
    for p, ms in res:
        ok = all(m["trades"] >= min_trades_per_fold for m in ms)
        score = float(np.median([m["avg_R"] for m in ms])) if ok else -np.inf
        rows.append({**p, "score": score, "worst_fold_avgR": min(m["avg_R"] for m in ms),
                     "is_trades": sum(m["trades"] for m in ms)})
    table = pd.DataFrame(rows).sort_values("score", ascending=False)
    best = {k: table.iloc[0][k] for k in keys}
    best = {k: (bool(v) if k == "require_respiration" else (int(v) if k == "max_hold_bars" else float(v))) for k, v in best.items()}
    return best, table


def random_baseline(feat, n_trades, cfg, start, n_runs=500, seed=0):
    """ورود تصادفی (جهت و زمان) با همان خروج‌های ATR و هزینه، در همان بازه."""
    rng = np.random.default_rng(seed)
    pos = np.where(feat.index >= start)[0]
    c, a = feat["Close"].values, feat["ATR"].values
    tot, pf = [], []
    for _ in range(n_runs):
        d = np.zeros(len(feat), int)
        k = min(len(pos) - 1, max(1, n_trades * 3))  # بیش‌نمونه چون ورودها روی هم نمی‌افتند
        d[rng.choice(pos[:-1], k, replace=False)] = rng.choice([-1, 1], k)
        tr = simulate(feat, d, c + d * a * cfg.target_atr_mult, np.where(d != 0, c - d * a * cfg.stop_atr_mult, 0),
                      cfg.max_hold_bars, cfg.cost_frac) if n_trades else []
        if len(tr) > n_trades:   # زیرنمونه‌ی تصادفی (نه اولین‌ها → بدون سوگیری به ابتدای OOS)
            tr = [tr[k] for k in sorted(rng.choice(len(tr), n_trades, replace=False))]
        m = metrics(tr); tot.append(m["total_R"]); pf.append(m["avg_R"])
    return np.array(tot), np.array(pf)


def run(symbol, interval, cross=None, csv_dir=None, is_frac=0.7, workers=None):
    raw = load(symbol, interval, csv_dir)
    feat = BiologicalOrganism().build_features(raw)
    if cross:
        feat = add_cross(feat, load(cross, interval, csv_dir))
    cut = feat.index[int(len(feat) * is_frac)]
    base = OrganismConfig()
    # جستجو فقط روی IS (معاملات باز در پایان IS در فولد آخر شمرده نمی‌شوند چون Brain روی همان برش اجرا می‌شود)
    best, table = search(feat[feat.index < cut], base, workers=workers)
    cfg = make_cfg(base, best)
    _, trades = Brain(cfg).run(feat)                      # یک بار، روی کل داده (آنلاین)
    # purge: معاملات IS که بعد از cut بسته می‌شوند حذف؛ embargo: OOS از cut + max_hold شروع می‌شود
    emb = feat.index[min(len(feat) - 1, feat.index.get_loc(cut) + cfg.max_hold_bars)]
    is_m = metrics([t for t in trades if t.exit_time is not None and t.exit_time < cut])
    oos_tr = [t for t in trades if t.signal_time >= emb]
    oos_m = metrics(oos_tr)
    default_oos = metrics([t for t in Brain(base).run(feat)[1] if t.signal_time >= emb])
    tot, avg = random_baseline(feat, len(oos_tr), cfg, emb)
    oos_close = feat.loc[feat.index >= emb, "Close"]
    bh = 100 * (oos_close.iloc[-1] / oos_close.iloc[0] - 1)
    return dict(symbol=symbol, interval=interval, cross=cross, bars=len(feat), start=feat.index[0], cut=cut,
                end=feat.index[-1], best=best, is_metrics=is_m, oos_metrics=oos_m, default_oos=default_oos,
                random_oos_totalR_mean=round(float(tot.mean()), 2),
                random_oos_totalR_p95=round(float(np.percentile(tot, 95)), 2),
                strategy_pctile_vs_random=round(float((tot < oos_m["total_R"]).mean() * 100), 1),
                buy_hold_oos_pct=round(float(bh), 2), grid_top=table.head(5))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="GC=F"); ap.add_argument("--interval", default="15m")
    ap.add_argument("--cross"); ap.add_argument("--csv-dir")
    a = ap.parse_args()
    r = run(a.symbol, a.interval, a.cross, a.csv_dir)
    top = r.pop("grid_top")
    for k, v in r.items():
        print(f"{k}: {v}")
    print(top.to_string(index=False))
