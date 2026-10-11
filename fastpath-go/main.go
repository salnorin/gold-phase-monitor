package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	_ "net/http/pprof" // heap/CPU profiles on the same localhost listener
	"strings"
	"time"
)

type Server struct {
	books  *Books
	feePct float64
	maxAge time.Duration
	start  time.Time
}

func (s *Server) json(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	json.NewEncoder(w).Encode(v)
}

func (s *Server) arb() map[string]any {
	opps := ComputeArb(s.books.Snapshot(), s.feePct, time.Now(), s.maxAge, nil)
	return map[string]any{"paper_only": true, "fee_pct_per_side": s.feePct, "opportunities": opps,
		"note": "PAPER ONLY. USDT venues are flagged mixed_quote (stablecoin basis risk); no orders are ever placed."}
}

func (s *Server) Routes() *http.ServeMux {
	m := http.DefaultServeMux
	m.HandleFunc("/book", func(w http.ResponseWriter, r *http.Request) {
		s.json(w, map[string]any{"paper_only": true, "books": s.books.Snapshot()})
	})
	m.HandleFunc("/arb", func(w http.ResponseWriter, r *http.Request) { s.json(w, s.arb()) })
	m.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		s.json(w, map[string]any{"ok": true, "uptime_s": time.Since(s.start).Seconds(), "venues": s.books.Health(time.Now())})
	})
	m.HandleFunc("/sse", func(w http.ResponseWriter, r *http.Request) {
		fl, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "no flush", 500)
			return
		}
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		c := s.books.Subscribe()
		defer s.books.Unsubscribe(c)
		tick := time.NewTicker(250 * time.Millisecond) // coalesce bursts: at most 4 events/s
		defer tick.Stop()
		for {
			select {
			case <-r.Context().Done():
				return
			case <-tick.C:
				select {
				case <-c:
					b, _ := json.Marshal(map[string]any{"books": s.books.Snapshot(), "arb": s.arb()})
					fmt.Fprintf(w, "data: %s\n\n", b)
					fl.Flush()
				default:
				}
			}
		}
	})
	return m
}

func main() {
	addr := flag.String("addr", "127.0.0.1:8787", "listen address (localhost only by default)")
	fee := flag.Float64("fee", 0.20, "fee percent per side (energy)")
	venues := flag.String("venues", "coinbase,kraken,binance,okx", "comma-separated venues")
	flag.Parse()
	if !strings.HasPrefix(*addr, "127.0.0.1:") && !strings.HasPrefix(*addr, "localhost:") {
		log.Printf("warning: listening on non-loopback %s", *addr)
	}
	s := &Server{books: NewBooks(), feePct: *fee, maxAge: 10 * time.Second, start: time.Now()}
	stop := make(chan struct{})
	want := map[string]bool{}
	for _, v := range strings.Split(*venues, ",") {
		want[strings.TrimSpace(v)] = true
	}
	for _, v := range Venues() {
		if want[v.Name] {
			go Run(v, s.books, stop)
		}
	}
	log.Printf("fastpath (paper only) on http://%s  /book /arb /health /sse /debug/pprof", *addr)
	log.Fatal(http.ListenAndServe(*addr, s.Routes()))
}
