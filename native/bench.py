"""Speed comparison of the arena hot loop: numpy vs native Rust (synthetic data if no CSV is given)."""
import sys, time
import numpy as np
from core import arena as A
from core.organism import BiologicalOrganism
from core.paper import CostModel
from tests.conftest import make_ohlcv

raw = make_ohlcv(int(sys.argv[1]) if len(sys.argv) > 1 else 6000, 1)
df, F = A.feature_matrix(BiologicalOrganism().build_features(raw))
cm = CostModel(leverage=20.0); cf = A.counterfactual_table(df, cm)
G = A.random_genomes(10_000, np.random.default_rng(0), A.bounds_for(20))
for be in ("numpy", "native"):
    s = time.perf_counter(); A.simulate_population(G, F, df, 250, len(df), cm, cf=cf, backend=be)
    print(f"{be:7s} {time.perf_counter() - s:8.3f}s  ({len(df) - 250} bars × 10,000 genomes)")
