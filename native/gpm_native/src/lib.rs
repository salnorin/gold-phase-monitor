//! Native port of `core.arena.simulate_population` — the measured hottest loop (≈76 % of arena time).
//! PAPER SIMULATION ONLY. Semantics mirror the numpy version bar-by-bar; genomes are independent,
//! so the loop is genome-major (cache friendly) and parallel over genomes with rayon.
use numpy::{PyArray1, PyReadonlyArray1, PyReadonlyArray2, PyUntypedArrayMethods};
use pyo3::prelude::*;
use pyo3::types::PyDict;
use rayon::prelude::*;

#[derive(Clone, Copy)]
struct Cm {
    lev: f64,
    lm: f64,
    fee: f64,
    fund8: f64,
    spread: f64,
    vslip: f64,
    epct: f64,      // energy fraction per side (pct / 100)
    notional: bool, // energy on notional instead of margin
}

#[inline(always)]
fn energy(cm: &Cm, margin: f64, notional: f64) -> f64 {
    (if cm.notional { notional } else { margin }) * cm.epct
}

#[derive(Default, Clone, Copy)]
struct Out {
    eq: f64,
    liquidated: bool,
    alive: bool,
    trades: f64,
    wins: f64,
    maxdd: f64,
    energy: f64,
    credit: f64,
    declined: f64,
}

#[allow(clippy::too_many_arguments)]
fn sim_one(
    g: &[f64], f: &[f64], nf: usize, o: &[f64], h: &[f64], l: &[f64], c: &[f64], atr: &[f64], mopen: &[bool],
    el: &[f64], a: usize, b: usize, cm: &Cm, start: f64, risk_cap: Option<f64>, kill: f64,
    cfj: Option<&[f64]>, cfa: Option<&[i64]>,
) -> Out {
    let w = &g[..5];
    let (thr, tm, sm, hold, mf) = (g[5], g[6], g[7], g[8], g[9]);
    let wnorm: f64 = w.iter().map(|x| x.abs()).sum::<f64>() + 1e-9;
    let mut eq = start;
    let mut alive = true;
    let mut liquidated = false;
    let mut inpos = false;
    let (mut d, mut entry, mut qty, mut margin, mut stop, mut target, mut liq, mut bars, mut cost) =
        (0.0f64, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0);
    let mut pend = 0.0f64;
    let (mut trades, mut wins, mut peak, mut maxdd, mut en_tot, mut credit, mut declined) =
        (0.0f64, 0.0f64, start, 0.0f64, 0.0f64, 0.0f64, 0.0f64);
    for i in a..b {
        // entry
        if pend != 0.0 && !inpos && alive {
            let dd = pend;
            let slip = o[i] * cm.spread + atr[i - 1] * cm.vslip;
            let e = o[i] + dd * slip;
            let mut m = eq * mf;
            if let Some(rc) = risk_cap {
                let sd = atr[i - 1] * sm / e;
                m = m.min(rc * eq / (cm.lev * sd.max(1e-9)));
            }
            let q = m * cm.lev / e;
            entry = e; qty = q; margin = m; d = dd;
            stop = e - dd * atr[i - 1] * sm;
            target = e + dd * atr[i - 1] * tm;
            let en = energy(cm, m, q * e);
            en_tot += en;
            liq = e * (1.0 - dd * cm.lm);
            bars = 0.0;
            cost = q * e * cm.fee + en;
            inpos = true;
        }
        pend = 0.0;
        // exit
        if inpos {
            bars += 1.0;
            cost += qty * c[i] * cm.fund8 * el[i] / 8.0;
            let long = d > 0.0;
            let first = if long { stop.max(liq) } else { stop.min(liq) };
            let first_is_liq = if long { liq >= stop } else { liq <= stop };
            let (adverse, fav) = if long { (l[i], h[i]) } else { (h[i], l[i]) };
            let beyond = |lvl: f64, px: f64| if long { px <= lvl } else { px >= lvl };
            let gap = beyond(first, o[i]);
            let wick = !gap && beyond(first, adverse);
            let tgt = !gap && !wick && (if long { fav >= target } else { fav <= target });
            let tme = !gap && !wick && !tgt && bars >= hold;
            let liq_hit = (gap && (beyond(liq, o[i]) || first_is_liq)) || (wick && first_is_liq);
            if gap || wick || tgt || tme {
                let px = if gap { o[i] } else if wick { first } else if tgt { target } else { c[i] };
                let fill = px - d * (px * cm.spread + atr[i] * cm.vslip);
                let gross = qty * (fill - entry) * d;
                let en_x = energy(cm, margin, qty * fill.abs());
                let mut pnl = gross.max(-margin) - cost - qty * fill.abs() * cm.fee - en_x;
                if liq_hit {
                    pnl = -margin - cost - en_x;
                }
                en_tot += en_x;
                eq += pnl;
                trades += 1.0;
                if pnl > 0.0 { wins += 1.0; }
                inpos = false;
                liquidated |= liq_hit;
                alive = alive && !liquidated && eq > kill;
                peak = peak.max(eq);
                maxdd = maxdd.max(1.0 - eq / peak);
            }
        }
        // signal
        if i < b - 1 {
            let fi = &f[i * nf..i * nf + 5];
            let mut s = 0.0;
            for k in 0..5 { s += w[k] * fi[k]; }
            s /= wnorm;
            if alive && !inpos && mopen[i] {
                pend = if s.abs() >= thr { s.signum() } else { 0.0 };
                if let (Some(j), Some(at)) = (cfj, cfa) {
                    if pend == 0.0 && s.abs() >= thr / 2.0 {
                        let k = if s > 0.0 { 0 } else { 1 };
                        if at[i * 2 + k] < b as i64 {
                            credit -= j[i * 2 + k];
                            declined += 1.0;
                        }
                    }
                }
            }
        }
    }
    if inpos {
        let px = c[b - 1] - d * (c[b - 1] * cm.spread + atr[b - 1] * cm.vslip);
        let gross = qty * (px - entry) * d;
        let en_x = energy(cm, margin, qty * px.abs());
        en_tot += en_x;
        eq += gross.max(-margin) - cost - qty * px.abs() * cm.fee - en_x;
        trades += 1.0;
    }
    Out { eq: eq.max(0.0), liquidated, alive: alive && !liquidated, trades, wins, maxdd, energy: en_tot, credit, declined }
}

/// simulate(G, F, o, h, l, c, atr, mopen, el, a, b, cm_tuple, start, risk_cap, kill, cf_juice, cf_at) -> dict
#[pyfunction]
#[pyo3(signature = (g, f, o, h, l, c, atr, mopen, el, a, b, cm, start, risk_cap=None, kill=None, cf_juice=None, cf_at=None))]
#[allow(clippy::too_many_arguments)]
fn simulate<'py>(
    py: Python<'py>, g: PyReadonlyArray2<f64>, f: PyReadonlyArray2<f64>, o: PyReadonlyArray1<f64>,
    h: PyReadonlyArray1<f64>, l: PyReadonlyArray1<f64>, c: PyReadonlyArray1<f64>, atr: PyReadonlyArray1<f64>,
    mopen: PyReadonlyArray1<bool>, el: PyReadonlyArray1<f64>, a: usize, b: usize,
    cm: (f64, f64, f64, f64, f64, f64, f64, bool), start: f64, risk_cap: Option<f64>, kill: Option<f64>,
    cf_juice: Option<PyReadonlyArray2<f64>>, cf_at: Option<PyReadonlyArray2<i64>>,
) -> PyResult<Bound<'py, PyDict>> {
    let cm = Cm { lev: cm.0, lm: cm.1, fee: cm.2, fund8: cm.3, spread: cm.4, vslip: cm.5, epct: cm.6, notional: cm.7 };
    let ga = g.as_slice()?;
    let nf = f.shape()[1];
    let (fa, oa, ha, la, ca, aa, ma, ea) =
        (f.as_slice()?, o.as_slice()?, h.as_slice()?, l.as_slice()?, c.as_slice()?, atr.as_slice()?, mopen.as_slice()?, el.as_slice()?);
    let cj = match &cf_juice { Some(x) => Some(x.as_slice()?), None => None };
    let ct = match &cf_at { Some(x) => Some(x.as_slice()?), None => None };
    let ng = g.shape()[0];
    let ncol = g.shape()[1];
    let kill = kill.unwrap_or(start * 0.1);
    let outs: Vec<Out> = py.allow_threads(|| {
        (0..ng).into_par_iter().map(|k| {
            sim_one(&ga[k * ncol..(k + 1) * ncol], fa, nf, oa, ha, la, ca, aa, ma, ea, a, b, &cm, start, risk_cap, kill, cj, ct)
        }).collect()
    });
    let d = PyDict::new_bound(py);
    let col = |fun: &dyn Fn(&Out) -> f64| outs.iter().map(fun).collect::<Vec<f64>>();
    let colb = |fun: &dyn Fn(&Out) -> bool| outs.iter().map(fun).collect::<Vec<bool>>();
    d.set_item("equity", PyArray1::from_vec_bound(py, col(&|x| x.eq)))?;
    d.set_item("liquidated", PyArray1::from_vec_bound(py, colb(&|x| x.liquidated)))?;
    d.set_item("alive", PyArray1::from_vec_bound(py, colb(&|x| x.alive)))?;
    d.set_item("trades", PyArray1::from_vec_bound(py, col(&|x| x.trades)))?;
    d.set_item("wins", PyArray1::from_vec_bound(py, col(&|x| x.wins)))?;
    d.set_item("maxdd", PyArray1::from_vec_bound(py, col(&|x| x.maxdd)))?;
    d.set_item("energy", PyArray1::from_vec_bound(py, col(&|x| x.energy)))?;
    d.set_item("credit", PyArray1::from_vec_bound(py, col(&|x| x.credit)))?;
    d.set_item("declined", PyArray1::from_vec_bound(py, col(&|x| x.declined)))?;
    Ok(d)
}

#[pymodule]
fn gpm_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(simulate, m)?)?;
    Ok(())
}
