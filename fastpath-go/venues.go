package main

import (
	"encoding/json"
	"log"
	"strconv"
	"time"

	"github.com/gorilla/websocket"
)

// Venue describes a public websocket feed (no keys, read-only).
type Venue struct {
	Name, URL, Symbol, Quote string
	Subscribe             any
	Parse                 func(msg []byte, recv time.Time) (Top, bool)
}

func pf(s string) float64 { v, _ := strconv.ParseFloat(s, 64); return v }

func Venues() []Venue {
	return []Venue{
		{Name: "coinbase", URL: "wss://ws-feed.exchange.coinbase.com", Symbol: "PAXG-USD", Quote: "USD",
			Subscribe: map[string]any{"type": "subscribe", "product_ids": []string{"PAXG-USD"}, "channels": []string{"ticker"}},
			Parse: ParseCoinbase},
		{Name: "kraken", URL: "wss://ws.kraken.com/v2", Symbol: "PAXG/USD", Quote: "USD",
			Subscribe: map[string]any{"method": "subscribe", "params": map[string]any{"channel": "ticker", "symbol": []string{"PAXG/USD"}, "event_trigger": "bbo"}},
			Parse: ParseKraken},
		{Name: "binance", URL: "wss://stream.binance.com:9443/ws/paxgusdt@bookTicker", Symbol: "PAXGUSDT", Quote: "USDT",
			Parse: ParseBinance},
		{Name: "okx", URL: "wss://ws.okx.com:8443/ws/v5/public", Symbol: "PAXG-USDT", Quote: "USDT",
			Subscribe: map[string]any{"op": "subscribe", "args": []map[string]string{{"channel": "tickers", "instId": "PAXG-USDT"}}},
			Parse: ParseOKX},
	}
}

func ParseCoinbase(m []byte, recv time.Time) (Top, bool) {
	var x struct {
		Type, BestBid, BestAsk, BestBidSize, BestAskSize, Time string
	}
	var raw map[string]any
	if json.Unmarshal(m, &raw) != nil || raw["type"] != "ticker" {
		return Top{}, false
	}
	x.BestBid, _ = raw["best_bid"].(string)
	x.BestAsk, _ = raw["best_ask"].(string)
	x.BestBidSize, _ = raw["best_bid_size"].(string)
	x.BestAskSize, _ = raw["best_ask_size"].(string)
	x.Time, _ = raw["time"].(string)
	ts, _ := time.Parse(time.RFC3339Nano, x.Time)
	return Top{Venue: "coinbase", Symbol: "PAXG-USD", Quote: "USD", Bid: pf(x.BestBid), Ask: pf(x.BestAsk),
		BidSize: pf(x.BestBidSize), AskSize: pf(x.BestAskSize), ExchTS: ts, RecvTS: recv}, true
}

func ParseKraken(m []byte, recv time.Time) (Top, bool) {
	var x struct {
		Channel string `json:"channel"`
		Data    []struct {
			Bid, BidQty, Ask, AskQty float64
		} `json:"data"`
	}
	var raw struct {
		Channel string `json:"channel"`
		Data    []map[string]any `json:"data"`
	}
	if json.Unmarshal(m, &raw) != nil || raw.Channel != "ticker" || len(raw.Data) == 0 {
		return Top{}, false
	}
	_ = x
	d := raw.Data[0]
	g := func(k string) float64 { v, _ := d[k].(float64); return v }
	return Top{Venue: "kraken", Symbol: "PAXG/USD", Quote: "USD", Bid: g("bid"), Ask: g("ask"),
		BidSize: g("bid_qty"), AskSize: g("ask_qty"), RecvTS: recv}, true // ticker v2 has no exchange ts
}

func ParseBinance(m []byte, recv time.Time) (Top, bool) {
	var x struct {
		B, BQ, A, AQ string
	}
	var raw map[string]any
	if json.Unmarshal(m, &raw) != nil {
		return Top{}, false
	}
	x.B, _ = raw["b"].(string)
	x.BQ, _ = raw["B"].(string)
	x.A, _ = raw["a"].(string)
	x.AQ, _ = raw["A"].(string)
	if x.B == "" {
		return Top{}, false
	}
	return Top{Venue: "binance", Symbol: "PAXGUSDT", Quote: "USDT", Bid: pf(x.B), Ask: pf(x.A),
		BidSize: pf(x.BQ), AskSize: pf(x.AQ), RecvTS: recv}, true
}

func ParseOKX(m []byte, recv time.Time) (Top, bool) {
	var raw struct {
		Data []struct {
			BidPx, BidSz, AskPx, AskSz, Ts string
		} `json:"data"`
	}
	if json.Unmarshal(m, &raw) != nil || len(raw.Data) == 0 {
		return Top{}, false
	}
	d := raw.Data[0]
	ms, _ := strconv.ParseInt(d.Ts, 10, 64)
	var ts time.Time
	if ms > 0 {
		ts = time.UnixMilli(ms)
	}
	return Top{Venue: "okx", Symbol: "PAXG-USDT", Quote: "USDT", Bid: pf(d.BidPx), Ask: pf(d.AskPx),
		BidSize: pf(d.BidSz), AskSize: pf(d.AskSz), ExchTS: ts, RecvTS: recv}, true
}

// Run keeps one venue connected with capped exponential backoff. Read-only.
func Run(v Venue, books *Books, stop <-chan struct{}) {
	backoff := time.Second
	for {
		select {
		case <-stop:
			return
		default:
		}
		c, _, err := websocket.DefaultDialer.Dial(v.URL, nil)
		if err != nil {
			log.Printf("%s: dial: %v (retry in %s)", v.Name, err, backoff)
			time.Sleep(backoff)
			backoff = min(backoff*2, 60*time.Second)
			continue
		}
		c.SetReadLimit(1 << 20) // bounded message size
		if v.Subscribe != nil {
			if err := c.WriteJSON(v.Subscribe); err != nil {
				c.Close()
				continue
			}
		}
		backoff = time.Second
		for {
			c.SetReadDeadline(time.Now().Add(90 * time.Second))
			_, msg, err := c.ReadMessage()
			if err != nil {
				log.Printf("%s: read: %v", v.Name, err)
				break
			}
			if t, ok := v.Parse(msg, time.Now()); ok {
				books.Update(t)
			}
		}
		c.Close()
	}
}
