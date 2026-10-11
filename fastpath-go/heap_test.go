package main

import (
	"runtime"
	"testing"
	"time"
)

// Heap must stay bounded under sustained updates (ring buffers + fixed map keys; no per-update growth).
func TestHeapBounded(t *testing.T) {
	b := NewBooks()
	tp := Top{Venue: "coinbase", Quote: "USD", Bid: 4180, Ask: 4181}
	feed := func(n int) {
		for i := 0; i < n; i++ {
			tp.RecvTS = time.Now()
			tp.ExchTS = tp.RecvTS.Add(-time.Millisecond)
			b.Update(tp)
		}
	}
	var m0, m1 runtime.MemStats
	feed(100_000)
	runtime.GC()
	runtime.ReadMemStats(&m0)
	feed(1_000_000)
	b.Health(time.Now())
	runtime.GC()
	runtime.ReadMemStats(&m1)
	if grow := int64(m1.HeapAlloc) - int64(m0.HeapAlloc); grow > 256<<10 {
		t.Fatalf("heap grew %d bytes over 1M updates", grow)
	} else {
		t.Logf("heap delta over 1M updates: %d bytes (HeapAlloc %d KB)", grow, m1.HeapAlloc>>10)
	}
}
