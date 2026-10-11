# core/evaluate_v3.py
"""
ارزیابی صادقانه‌ی v3 (فقط شبیه‌سازی): IS قفل‌شده / OOS دست‌نخورده با embargo.
  A) ذهن: کامل، بدون جعبه‌سیاه، شهود منجمد، و مغز v2
  B) میدان: «بازماندگان ۲۰x تکثیر می‌شوند» در برابر «رتبه‌بندی اسپات تعدیل‌ریسک + اندازه‌ی کسری کلی» → OOS در ۲۰x
  C) مونت‌کارلو بلوک‌بوت‌استرپ: احتمال لیکوئید هر سطح اهرم
اجرا: python -m core.evaluate_v3 --csv-dir /tmp/gd --pop 10000
"""
import argparse
from dataclasses import replace
import numpy as np
import pandas as pd

from core import arena as A
from core.backtest import metrics
from core.brain import Brain
from core.mind import Mind, MindConfig
from core.organism import BiologicalOrganism
from core.paper import CostModel
from core.research import add_cross, load


def seg_stats(m: Mind, j: pd.DataFrame, a, b):
    tr = [p for p in m.trades if a <= p.open_time and (b is None or p.exit_time < b)]
    r = np.array([p.r_multiple for p in tr]) if tr else np.array([])
    eq = j.loc[(j.index >= a) & ((j.index < b) if b is not None else True), "juice"]
    dd = float((1 - eq / eq.cummax()).max()) if len(eq) else 0.0
    gains, losses = r[r > 0].sum(), -r[r <= 0].sum()
    return dict(trades=len(r), win_rate=round(100 * float((r > 0).mean()), 1) if len(r) else 0.0,
                avg_R=round(float(r.mean()), 3) if len(r) else 0.0,
                profit_factor=round(float(gains / losses), 2) if losses > 0 else None,
                ret_pct=round(100 * float(eq.iloc[-1] / eq.iloc[0] - 1), 1) if len(eq) else 0.0,
                max_dd_pct=round(100 * dd, 1), liquidations=sum(p.reason == "liquidation" for p in tr))


def mind_ablations(feat, cut, emb):
    rows = []
    variants = {
        "mind full": MindConfig(),
        "mind no black box": MindConfig(bb_distance=0.0),
        "mind frozen intuition": MindConfig(trust_lr=0.0),
        "mind no blackbox + frozen": MindConfig(bb_distance=0.0, trust_lr=0.0),
    }
    for name, cfg in variants.items():
        m = Mind(cfg); j = m.run(feat)
        rows.append({"variant": name, "set": "IS", **seg_stats(m, j, j.index[0], cut)})
        rows.append({"variant": name, "set": "OOS", **seg_stats(m, j, emb, None)})
    oc = replace(MindConfig().organism, cost_frac=0.0001)
    _, t = Brain(oc).run(feat)
    rows.append({"variant": "v2 brain (R only, 0.01% cost)", "set": "IS", **metrics([x for x in t if x.exit_time < cut])})
    rows.append({"variant": "v2 brain (R only, 0.01% cost)", "set": "OOS", **metrics([x for x in t if x.signal_time >= emb])})
    return pd.DataFrame(rows)


def kelly_resize(champs, final_is, df, is_end, lev, frac=0.25):
    """کسری کلی از آمار IS هر ژنوم → ریسک → سهم مارجین در اهرم lev."""
    G = champs.copy()
    atr_frac = float(np.median((df["ATR"] / df["Close"]).values[:is_end]))
    W = final_is["win_rate"]; b = G[:, 6] / G[:, 7]
    f = np.clip(W - (1 - W) / b, 0, None)
    risk = np.clip(frac * f, 0.0, 0.02)
    G[:, 9] = np.clip(risk / (G[:, 7] * atr_frac * lev), 0.02, 1.0)
    G[risk == 0, 9] = 0.02
    return G, risk


def arena_modes(df, F, is_end, oos_start, pop, hours, seed=0):
    out = {}
    cm20 = CostModel(leverage=20, bar_hours=hours)
    cm1 = CostModel(leverage=1, bar_hours=hours)
    # حالت کاربر: بقا در ۲۰x
    G, final, hist = A.evolve(F, df, is_end, cm20, pop=pop, seed=seed, rank="return")
    d20, champs20 = A.deflation_test(G, final, F, df, oos_start, len(df), cm20, rank="return")
    out["20x-survivor replication"] = dict(history=hist, oos=d20, champs=champs20)
    # مقایسه: رتبه‌بندی اسپات تعدیل‌ریسک، سپس کسری کلی در ۲۰x
    G1, final1, hist1 = A.evolve(F, df, is_end, cm1, pop=pop, seed=seed, rank="risk_adj")
    score, surv = A.fitness(final1, "risk_adj")
    order = np.argsort(-score)[:min(50, int(surv.sum()))]
    champs1 = G1[order]
    final_sel = {k: v[order] for k, v in final1.items()}
    Gk, risk = kelly_resize(champs1, final_sel, df, is_end, 20)
    dk, _ = A.deflation_test(None, None, F, df, oos_start, len(df), cm20, champs=Gk)
    dk["kelly_median_risk"] = float(np.median(risk))
    out["spot risk-adj + 1/4 Kelly @20x"] = dict(history=hist1, oos=dk, champs=Gk)
    return out


def block_bootstrap(raw, n_bars, n_paths=30, block=48, seed=0):
    rng = np.random.default_rng(seed)
    pc = raw["Close"].shift(1)
    rel = pd.DataFrame({k: np.log(raw[k] / pc) for k in ("Open", "High", "Low", "Close")}).iloc[1:]
    vol = raw["Volume"].values[1:]
    R = rel.values; n = len(R)
    paths = []
    for _ in range(n_paths):
        idx = np.concatenate([np.arange(s, s + block) for s in rng.integers(0, n - block, n_bars // block + 1)])[:n_bars]
        r = R[idx]; c = raw["Close"].iloc[0] * np.exp(np.cumsum(r[:, 3]))
        prev = np.r_[raw["Close"].iloc[0], c[:-1]]
        o, h, l = prev * np.exp(r[:, 0]), prev * np.exp(r[:, 1]), prev * np.exp(r[:, 2])
        h = np.maximum.reduce([h, o, c]); l = np.minimum.reduce([l, o, c])
        paths.append(pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": vol[idx]}, index=raw.index[-n_bars:]))
    return paths


def monte_carlo(raw, tier_champs, hours, n_paths=30):
    res = {}
    paths = block_bootstrap(raw, min(len(raw), 3000), n_paths)
    rng = np.random.default_rng(5)
    rand = A.random_genomes(200, rng)
    for lev, champs in tier_champs.items():
        cm = CostModel(leverage=lev, bar_hours=hours)
        liq_c, liq_r, ret_c = [], [], []
        for p in paths:
            df, F = A.feature_matrix(BiologicalOrganism().build_features(p))
            rc = A.simulate_population(champs, F, df, 1, len(df), cm)
            rr = A.simulate_population(rand, F, df, 1, len(df), cm)
            liq_c.append(rc["liquidated"].mean()); liq_r.append(rr["liquidated"].mean()); ret_c.append(np.median(rc["ret"]))
        res[lev] = dict(champ_liq_prob=round(float(np.mean(liq_c)), 3), random_liq_prob=round(float(np.mean(liq_r)), 3),
                        champ_median_ret=round(float(np.median(ret_c)), 3))
    return res


def main(csv_dir=None, pop=10_000, interval="1h", n_paths=30):
    hours = {"1h": 1.0, "15m": 0.25, "5m": 5 / 60}[interval]
    raw = load("GC=F", interval, csv_dir); cross = load("SI=F", interval, csv_dir)
    feat = add_cross(BiologicalOrganism().build_features(raw), cross)
    df, F = A.feature_matrix(feat)
    is_end = int(len(df) * 0.7); oos_start = is_end + 96
    cut, emb = df.index[is_end], df.index[oos_start]
    print(f"bars={len(df)} IS {df.index[0]} → {cut} | embargo → OOS {emb} → {df.index[-1]}\n")
    print("== A) Mind ablations ==")
    print(mind_ablations(feat, cut, emb).to_string(index=False))
    print("\n== B) Arena ranking modes (OOS at 20x) ==")
    modes = arena_modes(df, F, is_end, oos_start, pop, hours)
    for k, v in modes.items():
        print(k, {a: (round(b, 3) if isinstance(b, float) else b) for a, b in v["oos"].items()})
    print("\n== Tier survival (user mode) ==")
    tiers, champs = A.run_arena(raw, cross, hours, pop=pop)
    for lev, r in tiers.items():
        h = r["history"]
        print(f"{lev:g}x IS survival per gen: {h.survival.round(2).tolist()} | liquidated: {h.liquidated.round(3).tolist()}")
        print("   OOS:", {a: (round(b, 3) if isinstance(b, float) else b) for a, b in r["deflation"].items()})
    print("\n== C) Monte Carlo block bootstrap (liquidation probability) ==")
    mc = monte_carlo(raw, {lev: r["champions"] for lev, r in tiers.items()}, hours, n_paths)
    for lev, v in mc.items():
        print(f"{lev:g}x", v)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-dir"); ap.add_argument("--pop", type=int, default=10_000)
    ap.add_argument("--interval", default="1h"); ap.add_argument("--paths", type=int, default=30)
    a = ap.parse_args()
    main(a.csv_dir, a.pop, a.interval, a.paths)
