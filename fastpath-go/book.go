// Package main: Gold Phase Monitor fast path — PAXG top-of-book from public websockets.
// PAPER ONLY: read-only market data. There is no order code and no API keys.
package main

import (
	"sort"
	"sync"
	"time"
)

// Top is the top of book for one venue.
type Top struct {
	Venue    string    `json:"venue"`
	Symbol   string    `json:"symbol"`
	Quote    string    `json:"quote"` // USD or USDT (USDT basis is flagged in /arb)
	Bid      float64   `json:"bid"`
	Ask      float64   `json:"ask"`
	BidSize  float64   `json:"bid_size"`
	AskSize  float64   `json:"ask_size"`
	ExchTS   time.Time `json:"exchange_ts"`
	RecvTS   time.Time `json:"recv_ts"`
	LatencyM float64   `json:"latency_ms"` // recv - exchange timestamp (includes clock skew)
}

// Ring is a fixed-size ring buffer of float64 samples (no allocation after creation).
type Ring struct {
	buf  []float64
	n, i int
}

func NewRing(size int) *Ring { return &Ring{buf: make([]float64, size)} }

func (r *Ring) Add(v float64) {
	r.buf[r.i] = v
	r.i = (r.i + 1) % len(r.buf)
	if r.n < len(r.buf) {
		r.n++
	}
}

// Quantiles returns p50 and p99 using a reusable scratch slice.
func (r *Ring) Quantiles(scratch []float64) (p50, p99 float64, n int) {
	if r.n == 0 {
		return 0, 0, 0
	}
	s := append(scratch[:0], r.buf[:r.n]...)
	sort.Float64s(s)
	return s[r.n/2], s[(r.n*99)/100], r.n
}

// Books holds the latest top per venue plus latency rings.
type Books struct {
	mu      sync.RWMutex
	tops    map[string]Top
	lat     map[string]*Ring
	updates map[string]uint64
	subs    map[chan struct{}]struct{}
	scratch []float64
}

func NewBooks() *Books {
	return &Books{tops: map[string]Top{}, lat: map[string]*Ring{}, updates: map[string]uint64{},
		subs: map[chan struct{}]struct{}{}, scratch: make([]float64, 0, 4096)}
}

func (b *Books) Update(t Top) {
	if t.Bid <= 0 || t.Ask <= 0 || t.Ask < t.Bid {
		return
	}
	if t.RecvTS.IsZero() {
		t.RecvTS = time.Now()
	}
	if !t.ExchTS.IsZero() {
		t.LatencyM = float64(t.RecvTS.Sub(t.ExchTS).Microseconds()) / 1000
	}
	b.mu.Lock()
	b.tops[t.Venue] = t
	r := b.lat[t.Venue]
	if r == nil {
		r = NewRing(4096)
		b.lat[t.Venue] = r
	}
	if !t.ExchTS.IsZero() && t.LatencyM >= 0 && t.LatencyM < 30_000 { // ignore snapshot messages carrying old trade times
		r.Add(t.LatencyM)
	}
	b.updates[t.Venue]++
	for c := range b.subs { // non-blocking fan-out (bounded: each subscriber channel has cap 1)
		select {
		case c <- struct{}{}:
		default:
		}
	}
	b.mu.Unlock()
}

func (b *Books) Snapshot() []Top {
	b.mu.RLock()
	defer b.mu.RUnlock()
	out := make([]Top, 0, len(b.tops))
	for _, t := range b.tops {
		out = append(out, t)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Venue < out[j].Venue })
	return out
}

type VenueHealth struct {
	Venue   string  `json:"venue"`
	AgeMs   float64 `json:"age_ms"`
	P50Ms   float64 `json:"latency_p50_ms"`
	P99Ms   float64 `json:"latency_p99_ms"`
	Samples int     `json:"samples"`
	Updates uint64  `json:"updates"`
}

func (b *Books) Health(now time.Time) []VenueHealth {
	b.mu.Lock()
	defer b.mu.Unlock()
	out := []VenueHealth{}
	for v, t := range b.tops {
		p50, p99, n := b.lat[v].Quantiles(b.scratch)
		out = append(out, VenueHealth{v, float64(now.Sub(t.RecvTS).Microseconds()) / 1000, p50, p99, n, b.updates[v]})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Venue < out[j].Venue })
	return out
}

func (b *Books) Subscribe() chan struct{} {
	c := make(chan struct{}, 1)
	b.mu.Lock()
	b.subs[c] = struct{}{}
	b.mu.Unlock()
	return c
}

func (b *Books) Unsubscribe(c chan struct{}) {
	b.mu.Lock()
	delete(b.subs, c)
	b.mu.Unlock()
}
