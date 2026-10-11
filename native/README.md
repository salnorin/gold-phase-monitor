# native/ — optional Rust hot loop (PyO3 + maturin)

**Profiling first.** cProfile on the PAXG 1h arena showed `core.arena.simulate_population`, the per-bar genome tick/PnL loop, taking about 76% of arena time. Only that loop was ported. In the mind replay the ledger is the biggest cost, but it's spread over many small calls with no single hot loop, so it stays in Python.

`gpm_native.simulate` mirrors the numpy version bar by bar. It runs genome-major and in parallel over genomes (rayon).

| PAXG 1h, 11,989 bars × 10,000 genomes | time |
|---|---|
| numpy (reference) | 10.52 s |
| Rust, 1 thread | 0.52 s (≈20×) |
| Rust, 8 threads | 0.071 s (≈149×) |
| full `run_arena` 10k × 6 generations × 3 tiers | 47.0 s → 1.2 s (≈39×) |

Equivalence: `tests/test_native.py` compares against numpy (100% of genomes matched exactly in the benchmark).

No Assembly: the loop is branchy, per-genome scalar code. SIMD would not help much, and the compiler handles the arithmetic.

```bash
pip install maturin && make native      # builds and installs into the active venv
make native-test                        # equivalence tests
GPM_NATIVE=0 ...                        # force the numpy path
```

The module is **optional**. If `gpm_native` isn't installed (e.g. Streamlit Cloud has no Rust toolchain), `core.arena` falls back to numpy automatically. `requirements.txt` is unchanged.
