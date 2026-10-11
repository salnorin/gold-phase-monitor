package main

import (
	"sort"
	"time"
)

// Opp is a PAPER cross-venue opportunity: buy at BuyVenue's ask, sell at SellVenue's bid, net of fees on both sides.
type Opp struct {
	BuyVenue  string  `json:"buy_venue"`
	SellVenue string  `json:"sell_venue"`
	BuyAsk    float64 `json:"buy_ask"`
	SellBid   float64 `json:"sell_bid"`
	GrossPct  float64 `json:"gross_pct"`
	NetPct    float64 `json:"net_pct"` // after fee_pct per side
	Size      float64 `json:"max_size"`
	MixedQuote bool   `json:"mixed_quote"` // USD vs USDT: not a clean arb (stablecoin basis risk)
	Flag      bool    `json:"flag"`        // NetPct > 0 and not stale
	Stale     bool    `json:"stale"`
}

// ComputeArb evaluates every ordered venue pair. feePct is per side in percent (0.20 = 20 bps).
// out is reused to avoid allocations on the hot path.
func ComputeArb(tops []Top, feePct float64, now time.Time, maxAge time.Duration, out []Opp) []Opp {
	out = out[:0]
	f := feePct / 100
	for i := range tops {
		for j := range tops {
			if i == j {
				continue
			}
			a, b := &tops[i], &tops[j]
			cost := a.Ask * (1 + f)
			proceeds := b.Bid * (1 - f)
			stale := now.Sub(a.RecvTS) > maxAge || now.Sub(b.RecvTS) > maxAge
			net := (proceeds - cost) / cost * 100
			o := Opp{BuyVenue: a.Venue, SellVenue: b.Venue, BuyAsk: a.Ask, SellBid: b.Bid,
				GrossPct: (b.Bid - a.Ask) / a.Ask * 100, NetPct: net, Size: min(a.AskSize, b.BidSize),
				MixedQuote: a.Quote != b.Quote, Stale: stale}
			o.Flag = net > 0 && !stale
			out = append(out, o)
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].NetPct > out[j].NetPct })
	return out
}
