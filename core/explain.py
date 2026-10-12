# core/explain.py
"""
«چرا؟» — شکستن تصمیم آخر به دروازه‌ها (فقط خواندن؛ هیچ آستانه‌ای عوض نمی‌شود).
gate_breakdown(dec, ctx, cfg, raw) → dict(action, reason, profile, items=[{k, ok, v, thr}...])
k ها کلید ترجمه‌اند (داشبورد FA/DE/EN): move_1h, move_24h, market, organ_score, confidence, energy, stress,
dominance, doubt, whale, oxygen, volatility, cooldown, in_position, momentum.
"""
import numpy as np


def _f(x, nd=4):
    try:
        x = float(x)
        return None if np.isnan(x) else round(x, nd)
    except (TypeError, ValueError):
        return None


def price_moves(raw):
    c = raw["Close"].astype(float)
    out = []
    if len(c) >= 2:
        out.append(dict(k="move_1h", ok=True, v=_f(c.iloc[-1] / c.iloc[-2] - 1, 5)))
    if len(c) >= 25:
        out.append(dict(k="move_24h", ok=True, v=_f(c.iloc[-1] / c.iloc[-25] - 1, 5)))
    return out


def gate_breakdown(dec, ctx, cfg, raw, profile="normal"):
    from core.mind import mind_features
    c = dec.confirmed or dec
    items = price_moves(raw)
    items.append(dict(k="market", ok=not c.asleep, v=c.market_state))
    m = ctx.get("mind")
    if m is not None:
        b, oc = m.brain.blood, cfg.organism
        items += [dict(k="organ_score", ok=abs(b.score) >= oc.min_score, v=_f(abs(b.score)), thr=oc.min_score),
                  dict(k="confidence", ok=b.confidence >= oc.min_confidence, v=_f(b.confidence), thr=oc.min_confidence),
                  dict(k="energy", ok=b.atp >= oc.atp_floor, v=_f(b.atp, 1), thr=oc.atp_floor),
                  dict(k="stress", ok=b.cortisol <= oc.cortisol_ceiling, v=_f(b.cortisol, 1), thr=oc.cortisol_ceiling)]
    pd_ = max(c.P_bull, c.P_bear)
    items += [dict(k="dominance", ok=pd_ >= c.dominance_thr, v=_f(pd_), thr=_f(c.dominance_thr)),
              dict(k="doubt", ok=c.doubt <= c.max_doubt, v=_f(c.doubt), thr=_f(c.max_doubt))]
    j = ctx.get("journal")
    if j is not None and len(j):
        recent = j["whale"].tail(cfg.whale_caution_bars + 1)
        items.append(dict(k="whale", ok=not bool(recent.any()), v=int(recent.sum()), thr=cfg.whale_caution_bars))
        items.append(dict(k="volatility", ok=c.vol_ratio <= cfg.vol_rest_ratio, v=_f(c.vol_ratio, 2), thr=cfg.vol_rest_ratio))
        items.append(dict(k="cooldown", ok="استراحت اجباری" not in c.reason and "توقف خودکار" not in c.reason))
        items.append(dict(k="in_position", ok=not bool(j["in_position"].iloc[-1])))
    feat = ctx.get("feat")
    if feat is not None and len(feat):
        thr = mind_features(feat.tail(600), cfg)["Low_Oxygen_Thr"].iloc[-1]
        items.append(dict(k="oxygen", ok=bool(c.oxygen >= thr), v=_f(c.oxygen, 2), thr=_f(thr, 2)))
    return dict(action=c.action, reason=c.reason, profile=profile, items=items)


def momentum_breakdown(raw, mp, action):
    from core.momentum import momentum_return
    r = momentum_return(raw, mp.bars)
    items = price_moves(raw)
    items.append(dict(k="momentum", ok=action != "WAIT", v=_f(r, 5), thr=mp.pct / 100, n=mp.bars))
    return dict(action=action, reason=f"momentum {mp.bars} bars", profile="active", items=items)
