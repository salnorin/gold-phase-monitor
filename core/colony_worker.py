# core/colony_worker.py
"""
One organism instance in the colony (a separate OS process, isolated memory). PAPER ONLY — no order code.
Each cycle it replays a rolling window of PAXG candles with its own mutated mind genes and writes its
paper performance + memory to a small status file. Buffers are bounded (deque maxlen) and reused.
"""
import argparse
import json
import os
import sys
import time
from collections import deque
from pathlib import Path


def rss_mb(pid=None):
    pid = pid or os.getpid()
    try:
        import psutil
        return psutil.Process(pid).memory_info().rss / 2**20
    except Exception:
        pass
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    except Exception:
        pass
    try:
        import subprocess
        return int(subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()) / 1024
    except Exception:
        return float("nan")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--genes", required=True, help="JSON dict of MindConfig overrides")
    ap.add_argument("--csv", required=True, help="PAXG candles CSV (shared read-only input)")
    ap.add_argument("--status", required=True)
    ap.add_argument("--window", type=int, default=1500)
    ap.add_argument("--cycles", type=int, default=0, help="0 = run until terminated")
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--leak-mb", type=float, default=0.0, help="TEST ONLY: deliberately grow memory per cycle")
    a = ap.parse_args(argv)
    import pandas as pd
    from core.mind import Mind, MindConfig
    from core.organism import BiologicalOrganism
    genes = json.loads(a.genes)
    raw = pd.read_csv(a.csv, index_col=0)
    raw.index = pd.to_datetime(raw.index, utc=True).tz_convert("America/New_York")
    hist = deque(maxlen=64)                     # bounded history of results
    leak = []                                   # only used by the leak test
    status = Path(a.status)
    cycle = 0
    step = max(24, a.window // 20)
    while a.cycles == 0 or cycle < a.cycles:
        end = min(len(raw), a.window + 250 + cycle * step) if len(raw) > a.window + 250 else len(raw)
        win = raw.iloc[max(0, end - a.window - 250):end]
        cfg = MindConfig(**{k: v for k, v in genes.items() if k in MindConfig.__dataclass_fields__})
        m = Mind(cfg)
        j = m.run(BiologicalOrganism().build_features(win))
        ret = float(m.equity / cfg.start_equity - 1)
        hist.append(ret)
        if a.leak_mb:
            leak.append(bytearray(int(a.leak_mb * 2**20)))
        cycle += 1
        tmp = status.with_suffix(".tmp")
        tmp.write_text(json.dumps(dict(id=a.id, pid=os.getpid(), cycle=cycle, ret=ret, mean_ret=sum(hist) / len(hist),
                                       trades=len(m.trades), rss_mb=rss_mb(), genes=genes, t=time.time())))
        tmp.replace(status)
        del m, j
        time.sleep(a.sleep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
