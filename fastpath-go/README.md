# fastpath-go — PAXG top-of-book daemon (paper only)

Read-only public websockets for Coinbase `PAXG-USD`, Kraken `PAXG/USD`, Binance `PAXGUSDT` and OKX `PAXG-USDT`. It keeps the top of book for each venue and computes cross-venue spreads net of the 0.20%-per-side energy fee. Positive net spreads are flagged as **paper** arbitrage opportunities. It has **no order code and uses no keys**.

USDT venues are marked `mixed_quote`: a USD/USDT gap is stablecoin basis risk, not a clean arb. Binance and OKX are geo-blocked in some regions, and the daemon just keeps retrying them with backoff.

```bash
cd fastpath-go && go run .                 # listens on 127.0.0.1:8787
curl 127.0.0.1:8787/health                 # per-venue age, latency p50/p99, update count
curl 127.0.0.1:8787/book                   # top of book per venue
curl 127.0.0.1:8787/arb                    # paper opportunities net of fees
curl -N 127.0.0.1:8787/sse                 # server-sent events (coalesced, ≤ 4/s)
go tool pprof http://127.0.0.1:8787/debug/pprof/heap
go test -race ./... && go test -bench . -benchmem
```

The Python side (`core/fastpath.py`) uses the daemon when it is up. Otherwise it falls back to the Python fetch (`core/gold_price.py`).

**Streamlit Cloud cannot run this daemon**, so the hosted app always uses the Python fallback. Run the binary on your own PC or VPS next to a local `streamlit run app.py`. Prebuilt binaries for Linux, macOS and Windows are attached to each CI run.
