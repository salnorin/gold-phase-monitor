package main

import (
	"encoding/json"
	"math"
	"net/http/httptest"
	"testing"
	"time"
)

func top(v, q string, bid, ask float64, now time.Time) Top {
	return Top{Venue: v, Quote: q, Bid: bid, Ask: ask, BidSize: 1, AskSize: 2, RecvTS: now}
}

func TestArbNetOfFees(t *testing.T) {
	now := time.Now()
	tops := []Top{top("a", "USD", 3999, 4000, now), top("b", "USD", 4020, 4021, now)}
	opps := ComputeArb(tops, 0.20, now, 10*time.Second, nil)
	best := opps[0]
	if best.BuyVenue != "a" || best.SellVenue != "b" {
		t.Fatalf("wrong direction %+v", best)
	}
	want := (4020*(1-0.002) - 4000*(1+0.002)) / (4000 * 1.002) * 100
	if math.Abs(best.NetPct-want) > 1e-9 || !best.Flag {
		t.Fatalf("net %v want %v", best.NetPct, want)
	}
	// gross 0.5% < 0.4% fees? 0.5% gross minus ~0.4% fees > 0 → flagged; a 0.3% gap must not be
	tops[1] = top("b", "USD", 4012, 4013, now)
	if ComputeArb(tops, 0.20, now, 10*time.Second, nil)[0].Flag {
		t.Fatal("0.3% gross gap must not clear 0.4% round-trip fees")
	}
}

func TestStaleAndMixedQuote(t *testing.T) {
	now := time.Now()
	tops := []Top{top("a", "USD", 3999, 4000, now.Add(-time.Minute)), top("b", "USDT", 4100, 4101, now)}
	o := ComputeArb(tops, 0.20, now, 10*time.Second, nil)[0]
	if !o.Stale || o.Flag || !o.MixedQuote {
		t.Fatalf("%+v", o)
	}
}

func TestBooksRejectCrossedAndRing(t *testing.T) {
	b := NewBooks()
	b.Update(Top{Venue: "x", Bid: 10, Ask: 9})
	if len(b.Snapshot()) != 0 {
		t.Fatal("crossed book accepted")
	}
	r := NewRing(3)
	for _, v := range []float64{1, 2, 3, 4, 5} {
		r.Add(v)
	}
	p50, _, n := r.Quantiles(nil)
	if n != 3 || p50 != 4 {
		t.Fatalf("ring %v %v", p50, n)
	}
}

func TestParsers(t *testing.T) {
	now := time.Now()
	cb := []byte(`{"type":"ticker","product_id":"PAXG-USD","best_bid":"4180.1","best_ask":"4180.9","best_bid_size":"0.5","best_ask_size":"0.7","time":"2026-10-11T23:20:00.123456Z"}`)
	if tp, ok := ParseCoinbase(cb, now); !ok || tp.Bid != 4180.1 || tp.ExchTS.IsZero() {
		t.Fatalf("coinbase %+v", tp)
	}
	kr := []byte(`{"channel":"ticker","type":"update","data":[{"symbol":"PAXG/USD","bid":4179.5,"bid_qty":1.2,"ask":4181.0,"ask_qty":0.3}]}`)
	if tp, ok := ParseKraken(kr, now); !ok || tp.Ask != 4181.0 {
		t.Fatalf("kraken %+v", tp)
	}
	bn := []byte(`{"u":1,"s":"PAXGUSDT","b":"4182.00","B":"0.1","a":"4182.50","A":"0.2"}`)
	if tp, ok := ParseBinance(bn, now); !ok || tp.Quote != "USDT" || tp.AskSize != 0.2 {
		t.Fatalf("binance %+v", tp)
	}
	ok := []byte(`{"arg":{"channel":"tickers","instId":"PAXG-USDT"},"data":[{"bidPx":"4181","bidSz":"1","askPx":"4182","askSz":"2","ts":"1791847200000"}]}`)
	if tp, good := ParseOKX(ok, now); !good || tp.Bid != 4181 || tp.ExchTS.IsZero() {
		t.Fatalf("okx %+v", tp)
	}
}

func TestHTTP(t *testing.T) {
	s := &Server{books: NewBooks(), feePct: 0.2, maxAge: 10 * time.Second, start: time.Now()}
	s.books.Update(top("coinbase", "USD", 4180, 4181, time.Now()))
	s.books.Update(top("kraken", "USD", 4179, 4182, time.Now()))
	ts := httptest.NewServer(s.Routes())
	defer ts.Close()
	for _, p := range []string{"/book", "/arb", "/health"} {
		r, err := ts.Client().Get(ts.URL + p)
		if err != nil || r.StatusCode != 200 {
			t.Fatalf("%s %v", p, err)
		}
		var v map[string]any
		if json.NewDecoder(r.Body).Decode(&v) != nil {
			t.Fatalf("%s not json", p)
		}
	}
}

func BenchmarkComputeArb4Venues(b *testing.B) {
	now := time.Now()
	tops := []Top{top("a", "USD", 3999, 4000, now), top("b", "USD", 4001, 4002, now),
		top("c", "USDT", 4000, 4003, now), top("d", "USDT", 3998, 4001, now)}
	out := make([]Opp, 0, 16)
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		out = ComputeArb(tops, 0.2, now, 10*time.Second, out)
	}
}

func BenchmarkParseCoinbase(b *testing.B) {
	cb := []byte(`{"type":"ticker","product_id":"PAXG-USD","best_bid":"4180.1","best_ask":"4180.9","best_bid_size":"0.5","best_ask_size":"0.7","time":"2026-10-11T23:20:00.123456Z"}`)
	now := time.Now()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		ParseCoinbase(cb, now)
	}
}

func BenchmarkBooksUpdate(b *testing.B) {
	bk := NewBooks()
	t0 := top("coinbase", "USD", 4180, 4181, time.Now())
	t0.ExchTS = t0.RecvTS.Add(-time.Millisecond)
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		bk.Update(t0)
	}
}
