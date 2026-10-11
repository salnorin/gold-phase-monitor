# core/arena.py
"""
میدان انتخاب طبیعی (فقط شبیه‌سازی کاغذی).
جمعیت تا ۱۰٬۰۰۰ ژنوم (قانون ساده‌ی خطی روی رأی ارگان‌ها) به‌صورت برداری در اهرم ۲۰x/۱۰x/اسپات معامله می‌کنند.
  - تکامل فقط روی داده‌ی IS و پنجره‌به‌پنجره (walk-forward): هر نسل روی پنجره‌ی بعدی زمان آزموده می‌شود.
  - لیکوئیدشده‌ها حذف می‌شوند؛ فقط بازماندگان تکثیر و جهش می‌کنند (کران‌دار).
  - کنترل آزمون چندگانه: قهرمانان در برابر همان تعداد ژنوم تصادفی، و آزمون مجدد یک‌باره روی OOS دست‌نخورده.
اجرا: python -m core.arena --symbol GC=F --interval 1h --cross SI=F --csv-dir /tmp/gd --pop 10000
"""
import argparse
import numpy as np
import pandas as pd

from core.mind import MindConfig, mind_features
from core.organism import BiologicalOrganism
from core.paper import CostModel

FEATURES = ["V_resp", "Optical_Pull", "Motor_Drive", "Cross_Drive", "V_state"]
BOUNDS = {  # کران هر ژن
    "w": (-1.0, 1.0), "threshold": (0.05, 0.8), "target": (0.5, 4.0), "stop": (0.3, 3.0),
    "hold": (4, 96), "margin": (0.02, 1.0),
}
# ۲۰x: حد سود/ضرر تنگ و نگهداری کوتاه (سود و زیان سریع بسته شوند)؛ آرنا فقط داخل این کران‌ها تکامل می‌یابد
TIER_BOUNDS = {20.0: {**BOUNDS, "target": (0.6, 2.0), "stop": (0.3, 1.0), "hold": (2, 12)},
               10.0: {**BOUNDS, "target": (0.8, 3.0), "stop": (0.4, 1.5), "hold": (4, 24)}}


def bounds_for(lev):
    return TIER_BOUNDS.get(float(lev), BOUNDS)


GENES = ["w0", "w1", "w2", "w3", "w4", "threshold", "target", "stop", "hold", "margin"]


def feature_matrix(feat):
    f = mind_features(feat, MindConfig())
    if "Cross_Drive" not in f:
        f["Cross_Drive"] = 0.0
    f["V_resp"] = np.where(f["Long_Zone"], 1.0, np.where(f["Slaughter_Zone"], -1.0, 0.0))
    f["V_state"] = f["P_bull"] - f["P_bear"]
    return f, np.nan_to_num(f[FEATURES].values.astype(float))


def random_genomes(n, rng, B=BOUNDS):
    g = np.empty((n, len(GENES)))
    g[:, :5] = rng.uniform(*BOUNDS["w"], (n, 5))
    for k, name in enumerate(["threshold", "target", "stop", "hold", "margin"], start=5):
        lo, hi = B[name]
        g[:, k] = rng.uniform(lo, hi, n) if name != "margin" else np.exp(rng.uniform(np.log(lo), np.log(hi), n))
    return clip(g, B)


def clip(g, B=BOUNDS):
    g[:, :5] = np.clip(g[:, :5], *B["w"])
    for k, name in enumerate(["threshold", "target", "stop", "hold", "margin"], start=5):
        g[:, k] = np.clip(g[:, k], *B[name])
    g[:, 8] = np.round(g[:, 8])
    return g


def mutate(parents, n, rng, scale=0.1, B=BOUNDS):
    idx = rng.integers(0, len(parents), n)
    kids = parents[idx].copy()
    span = np.array([2] * 5 + [b[1] - b[0] for b in (B[k] for k in ["threshold", "target", "stop", "hold", "margin"])])
    kids += rng.normal(0, scale, kids.shape) * span
    # کراس‌اوور یکنواخت با والد دیگر
    other = parents[rng.integers(0, len(parents), n)]
    mask = rng.random(kids.shape) < 0.3
    kids[mask] = other[mask]
    return clip(kids, B)


def counterfactual_table(df, cm: CostModel):
    """دفتر تصمیم آرنا: آب‌میوه‌ی LONG/SHORT در هر کندل با قواعد tier (شامل انرژی) و کندلی که نتیجه معلوم شد."""
    from core.ledger import resolve, tier_rules
    o, h, l, c, atr = (df[k].values for k in ("Open", "High", "Low", "Close", "ATR"))
    rules, n = tier_rules(cm.leverage), len(df)
    juice = np.zeros((n, 2)); at = np.full((n, 2), n + 10**9, dtype=np.int64)
    for i in range(n):
        for k, d in enumerate((1, -1)):
            r = resolve(o, h, l, c, atr, i, d, rules, cm)
            if r is not None:
                at[i, k], juice[i, k] = r[0], r[3]
    return juice, at


def simulate_population(G, F, df, a, b, cm: CostModel, start_equity=10_000.0, risk_cap=None, kill_equity=None, cf=None):
    """risk_cap: حداکثر ضرر تا استاپ به‌صورت سهم از سرمایه (مثلاً ۰٫۰۱). kill_equity: زیر این سطح ژنوم حذف می‌شود."""
    """همه‌ی ژنوم‌ها در پنجره‌ی [a, b) با سرمایه‌ی تازه؛ بدون نگاه به آینده (سیگنال در Close، ورود Open بعدی)."""
    o, h, l, c, atr = (df[k].values for k in ("Open", "High", "Low", "Close", "ATR"))
    N = len(G)
    W = G[:, :5]; thr = G[:, 5]; tm = G[:, 6]; sm = G[:, 7]; hold = G[:, 8]; mf = G[:, 9]
    wnorm = np.abs(W).sum(1) + 1e-9
    eq = np.full(N, start_equity); alive = np.ones(N, bool); liquidated = np.zeros(N, bool)
    inpos = np.zeros(N, bool); d = np.zeros(N); entry = np.zeros(N); qty = np.zeros(N); margin = np.zeros(N)
    stop = np.zeros(N); target = np.zeros(N); liq = np.zeros(N); bars = np.zeros(N); cost = np.zeros(N)
    pend = np.zeros(N); energy = np.zeros(N)
    trades = np.zeros(N); wins = np.zeros(N); peak = eq.copy(); maxdd = np.zeros(N)
    credit = np.zeros(N); declined = np.zeros(N)   # اعتبار «عدم معامله‌ی درست» از دفتر تصمیم
    lm = cm.liq_move
    mopen = df["Market_Open"].values if "Market_Open" in df else np.ones(len(df), bool)
    el = np.r_[cm.bar_hours, np.diff(df.index.values).astype("timedelta64[s]").astype(float) / 3600]
    el = np.clip(el, cm.bar_hours, 96)   # آخر هفته → سواپ بیشتر
    for i in range(a, b):
        # ورود
        op = (pend != 0) & ~inpos & alive
        if op.any():
            dd_ = pend[op]
            slip = o[i] * cm.base_spread + atr[i - 1] * cm.vol_slippage
            e = o[i] + dd_ * slip
            m = eq[op] * mf[op]
            if risk_cap is not None:
                sd = atr[i - 1] * sm[op] / e
                m = np.minimum(m, risk_cap * eq[op] / (cm.leverage * np.maximum(sd, 1e-9)))
            q = m * cm.leverage / e
            entry[op] = e; qty[op] = q; margin[op] = m; d[op] = dd_
            stop[op] = e - dd_ * atr[i - 1] * sm[op]; target[op] = e + dd_ * atr[i - 1] * tm[op]
            en = cm.energy(m, q * e)
            energy[op] += en
            liq[op] = e * (1 - dd_ * lm); bars[op] = 0; cost[op] = q * e * cm.fee_rate + en; inpos[op] = True
        pend[:] = 0
        # خروج
        ip = inpos
        if ip.any():
            bars[ip] += 1
            cost[ip] += qty[ip] * c[i] * cm.funding_rate_8h * el[i] / 8
            long = d > 0
            first = np.where(long, np.maximum(stop, liq), np.minimum(stop, liq))
            first_is_liq = np.where(long, liq >= stop, liq <= stop)
            adverse = np.where(long, l[i], h[i]); fav = np.where(long, h[i], l[i])
            beyond = lambda lvl, px: np.where(long, px <= lvl, px >= lvl)
            gap = ip & beyond(first, o[i])
            wick = ip & ~gap & beyond(first, adverse)
            tgt = ip & ~gap & ~wick & np.where(long, fav >= target, fav <= target)
            tme = ip & ~gap & ~wick & ~tgt & (bars >= hold)
            liq_hit = (gap & (beyond(liq, o[i]) | first_is_liq)) | (wick & first_is_liq)
            px = np.where(gap, o[i], np.where(wick, first, np.where(tgt, target, c[i])))
            closing = gap | wick | tgt | tme
            if closing.any():
                fill = px - d * (px * cm.base_spread + atr[i] * cm.vol_slippage)
                gross = qty * (fill - entry) * d
                en_x = cm.energy(margin, qty * np.abs(fill))
                pnl = np.maximum(gross, -margin) - cost - qty * np.abs(fill) * cm.fee_rate - en_x
                pnl = np.where(liq_hit, -margin - cost - en_x, pnl)
                energy[closing] += en_x[closing]
                eq[closing] += pnl[closing]
                trades[closing] += 1; wins[closing & (pnl > 0)] += 1
                inpos[closing] = False
                liquidated |= closing & liq_hit
                alive &= ~liquidated & (eq > (kill_equity if kill_equity is not None else start_equity * 0.1))
                peak = np.maximum(peak, eq); maxdd = np.maximum(maxdd, 1 - eq / peak)
        # سیگنال
        if i < b - 1:
            s = (W @ F[i]) / wnorm
            can = alive & ~inpos & bool(mopen[i])
            pend[can] = np.where(np.abs(s[can]) >= thr[can], np.sign(s[can]), 0)
            if cf is not None:   # نزدیک‌سیگنال‌های ردشده: فقط اگر نتیجه داخل پنجره (گذشته) حل شده باشد
                near = can & (pend == 0) & (np.abs(s) >= thr / 2)
                k = np.where(s > 0, 0, 1)
                ok = near & (cf[1][i, k] < b)
                credit[ok] -= cf[0][i, k[ok]]     # ضرر اجتناب‌شده + / برد ازدست‌رفته −
                declined[ok] += 1
    # پوزیشن باز در پایان پنجره در Close بسته می‌شود
    if inpos.any():   # بستن اجباری در پایان پنجره، با اسلیپیج و کارمزد
        px = c[b - 1] - d * (c[b - 1] * cm.base_spread + atr[b - 1] * cm.vol_slippage)
        gross = qty * (px - entry) * d
        en_x = cm.energy(margin, qty * np.abs(px))
        energy[inpos] += en_x[inpos]
        eq[inpos] += (np.maximum(gross, -margin) - cost - qty * np.abs(px) * cm.fee_rate - en_x)[inpos]
        trades[inpos] += 1
    eq = np.maximum(eq, 0)
    return dict(equity=eq, ret=eq / start_equity - 1, liquidated=liquidated, alive=alive & ~liquidated,
                trades=trades, credit=credit, declined=declined, energy=energy, energy_frac=energy / start_equity, win_rate=np.divide(wins, trades, out=np.zeros(N), where=trades > 0), maxdd=maxdd)


def fitness(r, rank="return"):
    """return: بازده خام بازماندگان ۲۰x (حالت کاربر). risk_adj: امید ریاضی تعدیل‌شده با افت (برای اسپات)."""
    surv = r["alive"] & (r["trades"] > 0)
    if rank == "risk_adj":
        score = r["ret"] / (r["maxdd"] + 0.02) * np.sqrt(np.minimum(r["trades"], 50) / 50)
    else:
        score = r["ret"]
    if "credit" in r:      # اعتبار دفتر تصمیم، کران‌دار (حداکثر ±۰٫۰۵ بازده)
        score = score + 0.05 * np.tanh(r["credit"] / 10)
    return np.where(surv, score, -np.inf), surv


def evolve(F, df, is_end, cm, pop=10_000, generations=8, elite_frac=0.2, seed=0, warmup=250, rank="return", sim_kw=None, B=None):
    """تکامل walk-forward روی [warmup, is_end): هر نسل روی پنجره‌ی زمانی بعدی."""
    rng = np.random.default_rng(seed)
    B = B or bounds_for(cm.leverage)
    G = random_genomes(pop, rng, B)
    edges = np.linspace(warmup, is_end, generations + 1).astype(int)
    history = []
    for g in range(generations):
        r = simulate_population(G, F, df, edges[g], edges[g + 1], cm, **(sim_kw or {}))
        surv = r["alive"] & (r["trades"] > 0)
        history.append(dict(generation=g + 1, start=df.index[edges[g]], end=df.index[edges[g + 1] - 1],
                            survival=float(surv.mean()), liquidated=float(r["liquidated"].mean()),
                            profitable=float((surv & (r["ret"] > 0)).mean()),
                            median_ret_survivors=float(np.median(r["ret"][surv])) if surv.any() else np.nan,
                            traded=float((r["trades"] > 0).mean())))
        if not surv.any():
            G = random_genomes(pop, rng, B); continue
        if g == generations - 1:
            break
        order = np.argsort(-fitness(r, rank)[0])
        n_elite = max(1, min(int(pop * elite_frac), int(surv.sum())))
        elite = G[order[:n_elite]]
        G = np.vstack([elite, mutate(elite, pop - n_elite, rng, B=B)])
    # بازامتیازدهی نهایی روی کل IS (نه فقط آخرین پنجره) برای انتخاب قهرمانان
    final = simulate_population(G, F, df, edges[0], is_end, cm, **(sim_kw or {}))
    return G, final, pd.DataFrame(history)


def deflation_test(G, final, F, df, a, b, cm, k=50, n_random=2000, seed=1, rank="return", champs=None, sim_kw=None):
    """قهرمانان (k بهترین بازمانده‌ی IS) در برابر k ژنوم تصادفی؛ آزمون مجدد روی OOS."""
    rng = np.random.default_rng(seed)
    if champs is None:
        score, surv = fitness(final, rank)
        champs = G[np.argsort(-score)[:min(k, int(surv.sum()))]]
    rc = simulate_population(champs, F, df, a, b, cm, **(sim_kw or {}))
    R = random_genomes(n_random, rng, bounds_for(cm.leverage))
    rr = simulate_population(R, F, df, a, b, cm, **(sim_kw or {}))
    # توزیع میانه‌ی بازده k ژنوم تصادفی (بوت‌استرپ)
    boots = np.array([np.median(rr["ret"][rng.integers(0, n_random, len(champs))]) for _ in range(2000)])
    champ_med = float(np.median(rc["ret"])) if len(champs) else np.nan
    return dict(
        champions=len(champs),
        champ_oos_survival=float(rc["alive"].mean()) if len(champs) else np.nan,
        champ_oos_liquidated=float(rc["liquidated"].mean()) if len(champs) else np.nan,
        champ_oos_median_ret=champ_med,
        champ_oos_profitable=float((rc["ret"] > 0).mean()) if len(champs) else np.nan,
        champ_oos_median_trades=float(np.median(rc["trades"])) if len(champs) else np.nan,
        random_oos_survival=float(rr["alive"].mean()),
        random_oos_liquidated=float(rr["liquidated"].mean()),
        random_oos_median_ret=float(np.median(rr["ret"])),
        random_oos_profitable=float((rr["ret"] > 0).mean()),
        champ_pctile_vs_random=float((boots < champ_med).mean() * 100),
    ), champs


def run_arena(raw, cross_raw=None, interval_hours=1.0, pop=10_000, generations=8, tiers=(20.0, 10.0, 1.0),
              is_frac=0.7, seed=0, embargo=96, use_ledger=True):
    feat = BiologicalOrganism().build_features(raw)
    if cross_raw is not None:
        from core.research import add_cross
        feat = add_cross(feat, cross_raw)
    df, F = feature_matrix(feat)
    is_end = int(len(df) * is_frac)
    oos_start = min(len(df) - 2, is_end + embargo)     # embargo بین IS و OOS
    out = {}
    for lev in tiers:
        cm = CostModel(leverage=lev, bar_hours=interval_hours)
        kw = dict(cf=counterfactual_table(df, cm)) if use_ledger else None
        G, final, hist = evolve(F, df, is_end, cm, pop=pop, generations=generations, seed=seed, sim_kw=kw)
        defl, champs = deflation_test(G, final, F, df, oos_start, len(df), cm, sim_kw=kw)
        defl["energy_frac_median"] = float(np.median(final["energy_frac"]))
        out[lev] = dict(history=hist, deflation=defl, champions=champs)
    return out, df.index[oos_start]


if __name__ == "__main__":
    from core.research import load
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="GC=F"); ap.add_argument("--interval", default="1h")
    ap.add_argument("--cross"); ap.add_argument("--csv-dir"); ap.add_argument("--pop", type=int, default=10_000)
    ap.add_argument("--generations", type=int, default=8)
    a = ap.parse_args()
    hours = {"5m": 5 / 60, "15m": 0.25, "1h": 1.0}[a.interval]
    raw = load(a.symbol, a.interval, a.csv_dir)
    cross = load(a.cross, a.interval, a.csv_dir) if a.cross else None
    res, cut = run_arena(raw, cross, hours, a.pop, a.generations)
    print("OOS starts", cut)
    for lev, r in res.items():
        print(f"\n=== tier {lev:g}x ===")
        print(r["history"].round(3).to_string(index=False))
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r["deflation"].items()})
