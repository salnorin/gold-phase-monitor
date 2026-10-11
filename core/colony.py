# core/colony.py
"""
Organism colony supervisor — PAPER ONLY, on THIS machine.

- Spawns N organism instances as separate OS processes (core.colony_worker), each with isolated memory and an
  address-space limit (RLIMIT_AS on POSIX). No cgroup writes, so it needs no root.
- Hosts: only 'localhost' is supported. Other hosts must be listed explicitly by the owner in colony.json and are
  currently REFUSED (not implemented). There is never any discovery, scanning or self-spreading.
- Survival: every check, instances are ranked by paper performance. The bottom fraction is terminated (process
  exits → memory returned to the OS). Survivors spawn mutated children up to a hard cap (default 21, absolute
  max 21 unless the owner raises HARD_CAP in code).
- Memory monitor: per-instance RSS, peak, and RSS trend (MB/min) over a bounded ring of samples → leak flag.
CLI:  python -m core.colony run --n 6 --checks 5      |   python -m core.colony status
"""
import argparse
import json
import os
import random
import signal
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from pathlib import Path

from core.colony_worker import rss_mb
from core.live_account import DATA_DIR

HARD_CAP = 21
COLONY_DIR = DATA_DIR / "colony"
GENE_BOUNDS = {"dominance": (0.45, 0.75), "max_doubt": (0.3, 0.8), "low_oxygen": (0.3, 0.8), "base_risk": (0.002, 0.01)}


@dataclass
class ColonyConfig:
    max_instances: int = 21
    initial: int = 6
    rss_limit_mb: int = 1024          # RLIMIT_AS per instance (address space; generous because numpy maps a lot)
    check_every_s: float = 20.0
    kill_fraction: float = 0.34
    children_per_survivor: int = 1
    min_cycles_before_judging: int = 2
    leak_slope_mb_per_min: float = 20.0
    leak_min_span_s: float = 60.0     # trend needs at least this much history (after the first finished cycle)
    csv: str = ""
    window: int = 1500
    hosts: list = field(default_factory=lambda: ["localhost"])

    def __post_init__(self):
        self.max_instances = max(1, min(int(self.max_instances), HARD_CAP))
        bad = [h for h in self.hosts if h not in ("localhost", "127.0.0.1")]
        if bad:
            raise ValueError(f"remote hosts are not supported (explicit list only, not implemented): {bad}")


class MemTrack:
    """Bounded RSS history per instance → peak and linear trend (MB/min)."""

    def __init__(self, n=120):
        self.s = deque(maxlen=n)
        self.peak = 0.0

    def add(self, t, mb):
        if mb == mb:  # not NaN
            self.s.append((t, mb))
            self.peak = max(self.peak, mb)

    def span(self):
        return self.s[-1][0] - self.s[0][0] if len(self.s) > 1 else 0.0

    def slope(self):
        if len(self.s) < 4:
            return 0.0
        ts = [t for t, _ in self.s]; ys = [y for _, y in self.s]
        mt, my = sum(ts) / len(ts), sum(ys) / len(ys)
        den = sum((t - mt) ** 2 for t in ts) or 1e-9
        return sum((t - mt) * (y - my) for t, y in zip(ts, ys)) / den * 60.0


def _limit(mb):
    def f():
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (mb * 2**20, mb * 2**20))
        except Exception:
            pass
        os.setsid() if hasattr(os, "setsid") else None
    return f


def mutate(genes, rng, scale=0.15):
    out = {}
    for k, (lo, hi) in GENE_BOUNDS.items():
        v = genes.get(k, (lo + hi) / 2) + rng.gauss(0, scale * (hi - lo))
        out[k] = round(min(hi, max(lo, v)), 4)
    return out


class Colony:
    def __init__(self, cfg: ColonyConfig, root: Path = COLONY_DIR, seed=0, worker_extra=None):
        self.cfg, self.root, self.rng = cfg, Path(root), random.Random(seed)
        self.root.mkdir(parents=True, exist_ok=True)
        self.procs, self.mem, self.genes, self.events = {}, {}, {}, deque(maxlen=200)
        self.next_id = 0
        self.worker_extra = worker_extra or {}

    def spawn(self, genes, parent=None):
        if len(self.procs) >= self.cfg.max_instances:
            return None
        iid = f"o{self.next_id:03d}"; self.next_id += 1
        st = self.root / f"{iid}.json"
        cmd = [sys.executable, "-m", "core.colony_worker", "--id", iid, "--genes", json.dumps(genes), "--csv", self.cfg.csv,
               "--status", str(st), "--window", str(self.cfg.window)]
        for k, v in self.worker_extra.get(iid, self.worker_extra.get("*", {})).items():
            cmd += [f"--{k}", str(v)]
        kw = dict(cwd=str(Path(__file__).resolve().parent.parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.name == "posix":
            kw["preexec_fn"] = _limit(self.cfg.rss_limit_mb)
        self.procs[iid] = subprocess.Popen(cmd, **kw)
        self.mem[iid], self.genes[iid] = MemTrack(), genes
        self.events.append((time.time(), f"spawn {iid}" + (f" from {parent}" if parent else "")))
        return iid

    def kill(self, iid, why):
        p = self.procs.pop(iid, None)
        if p is None:
            return
        p.terminate()
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            p.kill(); p.wait()
        self.events.append((time.time(), f"terminate {iid}: {why}"))
        (self.root / f"{iid}.json").unlink(missing_ok=True)

    def status_of(self, iid):
        try:
            return json.loads((self.root / f"{iid}.json").read_text())
        except Exception:
            return None

    def sample(self):
        now = time.time()
        rows = []
        for iid, p in list(self.procs.items()):
            alive = p.poll() is None
            mb = rss_mb(p.pid) if alive else float("nan")
            st = self.status_of(iid) or {}
            if st.get("cycle", 0) >= 1:            # skip start-up ramp (imports, first data load)
                self.mem[iid].add(now, mb)
            slope = self.mem[iid].slope()
            enough = self.mem[iid].span() >= self.cfg.leak_min_span_s and len(self.mem[iid].s) >= 6
            rows.append(dict(id=iid, pid=p.pid, alive=alive, exit=p.returncode, cycle=st.get("cycle", 0),
                             ret=st.get("ret"), mean_ret=st.get("mean_ret"), trades=st.get("trades"),
                             rss_mb=round(mb, 1) if mb == mb else None, peak_mb=round(self.mem[iid].peak, 1),
                             trend_mb_min=round(slope, 2), leak=bool(enough and slope > self.cfg.leak_slope_mb_per_min),
                             genes=self.genes[iid]))
        return rows

    def judge(self):
        rows = self.sample()
        for r in rows:                                  # crashed (e.g. hit memory limit) or leaking → removed
            if not r["alive"]:
                self.kill(r["id"], f"exited ({r['exit']})")
            elif r["leak"]:
                self.kill(r["id"], f"leak suspected ({r['trend_mb_min']} MB/min)")
        ready = [r for r in rows if r["alive"] and not r["leak"] and r["cycle"] >= self.cfg.min_cycles_before_judging
                 and r["mean_ret"] is not None]
        if len(ready) >= 3:
            ready.sort(key=lambda r: r["mean_ret"])
            for r in ready[:max(1, int(len(ready) * self.cfg.kill_fraction))]:
                self.kill(r["id"], f"underperformer (mean paper ret {r['mean_ret']:+.2%})")
            for r in reversed(ready[int(len(ready) * self.cfg.kill_fraction):]):
                for _ in range(self.cfg.children_per_survivor):
                    if self.spawn(mutate(r["genes"], self.rng), parent=r["id"]) is None:
                        break
        self.write_status()
        return rows

    def write_status(self):
        rows = self.sample()
        data = dict(t=time.time(), cap=self.cfg.max_instances, n=len(self.procs), instances=rows,
                    total_rss_mb=round(sum(r["rss_mb"] or 0 for r in rows), 1),
                    events=[dict(t=t, e=e) for t, e in self.events])
        (self.root / "colony_status.json").write_text(json.dumps(data, default=str))
        return data

    def start(self):
        for _ in range(min(self.cfg.initial, self.cfg.max_instances)):
            self.spawn(mutate({}, self.rng, scale=0.3))

    def stop(self):
        for iid in list(self.procs):
            self.kill(iid, "colony stop")
        self.write_status()


def load_config(path=None, **over):
    d = {}
    p = Path(path) if path else Path("colony.json")
    if p.exists():
        d = json.loads(p.read_text())
    d.update({k: v for k, v in over.items() if v is not None})
    return ColonyConfig(**d)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Organism colony (paper only, local processes)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--n", type=int); r.add_argument("--max", type=int)
    r.add_argument("--checks", type=int, default=5); r.add_argument("--every", type=float)
    r.add_argument("--csv"); r.add_argument("--config")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        p = COLONY_DIR / "colony_status.json"
        print(p.read_text() if p.exists() else "no colony status yet"); return 0
    cfg = load_config(a.config, initial=a.n, max_instances=a.max, check_every_s=a.every, csv=a.csv)
    if not cfg.csv:
        from core import gold_price
        d = gold_price.candles("1h", 3000); COLONY_DIR.mkdir(parents=True, exist_ok=True)
        cfg.csv = str(COLONY_DIR / "paxg_1h.csv"); d.to_csv(cfg.csv)
    col = Colony(cfg)
    signal.signal(signal.SIGTERM, lambda *_: (col.stop(), sys.exit(0)))
    col.start()
    try:
        for k in range(a.checks):
            time.sleep(cfg.check_every_s)
            rows = col.judge()
            print(f"check {k + 1}: n={len(col.procs)} total_rss={sum(r['rss_mb'] or 0 for r in rows):.0f} MB "
                  f"best={max((r['mean_ret'] or -9) for r in rows):+.2%}")
            for r in rows:
                print(f"  {r['id']} pid={r['pid']} cycle={r['cycle']} ret={r['mean_ret']} rss={r['rss_mb']} "
                      f"peak={r['peak_mb']} trend={r['trend_mb_min']}MB/min leak={r['leak']}")
    finally:
        col.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
