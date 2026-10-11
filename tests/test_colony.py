import json, time
import numpy as np
import pytest

from core.colony import Colony, ColonyConfig, MemTrack, HARD_CAP, mutate, GENE_BOUNDS
from tests.conftest import make_ohlcv


def test_hard_cap_and_no_remote_hosts():
    assert ColonyConfig(max_instances=500).max_instances == HARD_CAP == 21
    with pytest.raises(ValueError):
        ColonyConfig(hosts=["localhost", "10.0.0.5"])


def test_memtrack_detects_trend():
    m = MemTrack(10)
    for i in range(10):
        m.add(i * 6.0, 100 + i * 5.0)          # +5 MB every 6 s → 50 MB/min
    assert abs(m.slope() - 50) < 1e-6 and m.peak == 145
    m2 = MemTrack(10)
    for i in range(10):
        m2.add(i * 6.0, 100.0)
    assert m2.slope() == 0


def test_mutation_bounded():
    import random
    r = random.Random(0)
    g = {}
    for _ in range(200):
        g = mutate(g, r, scale=1.0)
        for k, (lo, hi) in GENE_BOUNDS.items():
            assert lo <= g[k] <= hi


@pytest.mark.skipif(__import__("os").name != "posix", reason="RLIMIT_AS / os.kill(pid, 0) probing are POSIX-only")
def test_colony_lifecycle_kills_spawns_and_frees(tmp_path):
    raw = make_ohlcv(900, 2)
    csv = tmp_path / "p.csv"; raw.to_csv(csv)
    cfg = ColonyConfig(initial=4, max_instances=5, csv=str(csv), window=500, min_cycles_before_judging=1, kill_fraction=0.34,
                       leak_min_span_s=3.0)
    col = Colony(cfg, root=tmp_path / "c", seed=1, worker_extra={"*": {"sleep": 0.2}, "o000": {"sleep": 0.2, "leak-mb": 40}})
    col.start()
    try:
        deadline = time.time() + 120
        while time.time() < deadline:
            rows = col.sample()
            if all(r["cycle"] >= 2 for r in rows):
                break
            time.sleep(1)
        pids = {r["id"]: r["pid"] for r in rows}
        assert len(set(pids.values())) == 4                      # separate OS processes
        for _ in range(10):                                       # build RSS history for the leak check
            col.sample(); time.sleep(0.5)
        rows = col.sample()
        leaky = {r["id"]: r for r in rows}
        assert leaky["o000"]["leak"], leaky["o000"]
        assert not any(r["leak"] for r in rows if r["id"] != "o000"), rows
        col.cfg.leak_slope_mb_per_min = 50
        col.judge()
        ev = " ".join(e for _, e in col.events)
        # the leaking instance is removed: either flagged as a leak, or it already hit its RLIMIT_AS cap (MemoryError)
        assert "terminate o000: leak suspected" in ev or "terminate o000: exited" in ev, ev
        assert "o000" not in col.procs
        assert len(col.procs) <= cfg.max_instances
        st = json.loads((tmp_path / "c" / "colony_status.json").read_text())
        assert st["cap"] == 5 and "total_rss_mb" in st
        import os
        for iid, pid in pids.items():                             # terminated processes are really gone
            if iid not in col.procs:
                with pytest.raises(OSError):
                    os.kill(pid, 0)
    finally:
        col.stop()
    assert not col.procs
