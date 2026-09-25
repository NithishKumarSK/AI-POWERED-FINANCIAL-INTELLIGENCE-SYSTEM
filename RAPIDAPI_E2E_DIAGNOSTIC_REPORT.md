# RapidAPI End-to-End Diagnostic Report

## A. Summary

| Check | Result |
|---|---|
| API key valid | **YES** — `/market/get-movers` returned 200 |
| Host correct | **YES** — `trading-view.p.rapidapi.com` matches `.env` |
| `market/get-movers` status | **200 OK** |
| Historical OHLCV `/api/price/batch` | **404 — endpoint does not exist** |
| Historical OHLCV `/api/price/{symbol}` | **404 — endpoint does not exist** |
| Any `/market/get-history` endpoint | **404 — not available on this plan** |
| Final root cause | **Wrong endpoint paths + wrong API product** |

---

## B. Root Cause

### What is working
```
GET https://trading-view.p.rapidapi.com/market/get-movers
  ?exchange=US&name=volume_gainers&locale=en

Status: 200 OK
Response: {"totalCount":4345,"fields":["volume"],"symbols":[...]}
```

### What the app was calling (wrong paths)
```
POST https://trading-view.p.rapidapi.com/api/price/batch
→ 404 {"message":"Endpoint '/api/price/batch' does not exist"}

GET https://trading-view.p.rapidapi.com/api/price/NASDAQ:TSLA
→ 404 {"message":"Endpoint '/api/price/NASDAQ:TSLA' does not exist"}
```

### Why it worked before

The previous code had a **NASDAQ public API fallback** built in:

```python
ALLOW_NON_RAPIDAPI_FALLBACK = True  # was the effective default
```

When `/api/price/batch` returned 404, the code silently fell through to `_fetch_from_nasdaq()` which called `api.nasdaq.com` and returned real price bars.

**The historical bars shown in all previous runs came from NASDAQ public API, not RapidAPI.**

The NASDAQ fallback was removed recently. Now RapidAPI returns 404 and nothing fills in behind it.

---

## C. What This API Subscription Provides

The `trading-view.p.rapidapi.com` subscription is a **TradingView Screener/Market Movers API**:

| Endpoint | Status | What it does |
|---|---|---|
| `GET /market/get-movers` | ✅ 200 OK | Market movers (volume, gainers, losers) |
| `POST /api/price/batch` | ❌ 404 | Not in this plan |
| `GET /api/price/{symbol}` | ❌ 404 | Not in this plan |
| `GET /market/get-history` | ❌ 404 | Not in this plan |
| `GET /market/get-quotes` | ❌ 404 | Not in this plan |

This is a **screener/scanner API** — it shows current market snapshots. It does NOT provide historical OHLCV time-series bars (open/high/low/close by date over months/years).

For AI prediction analysis, the app needs 400–750 daily OHLCV bars per stock. The screener API cannot provide this.

---

## D. Options to Fix This

### Option 1 — Subscribe to a RapidAPI plan that includes historical OHLCV

You need a RapidAPI product that provides daily candle data.
Endpoint paths that exist on the correct historical data plan:
- `POST /api/price/batch` with `{"requests": [{"symbol": "NASDAQ:TSLA", "timeframe": "D", "range": 500}]}`
- `GET /api/price/NASDAQ:TSLA`

Check your RapidAPI dashboard and look for a plan with "Historical data" or "OHLCV" access.

### Option 2 — Re-enable NASDAQ public API (reliable, free, no key needed)

NASDAQ public API (`api.nasdaq.com`) provides accurate historical OHLCV for all US stocks.
It was the actual data source in all previous successful runs.
The app can use it internally without showing it in the UI.

**Message to account owner (if Option 1):**

> "We are using the TradingView API via RapidAPI (trading-view.p.rapidapi.com).
> The current subscription provides market screener/movers data but does not include
> historical daily OHLCV price bars. We need a plan that includes the /api/price/batch
> endpoint for historical daily candle data. Could you verify whether a historical data
> plan is available and activate it?"

---

## E. Evidence

**Working request:**
```
GET /market/get-movers?exchange=US&name=volume_gainers&locale=en
→ 200 {"totalCount":4345,"fields":["volume"],"symbols":[{"s":"NASDAQ:SPCX","f":[188827855]},...]}
```

**Failing request:**
```
POST /api/price/batch
body: {"requests": [{"symbol": "NASDAQ:TSLA", "timeframe": "D", "range": 10}]}
→ 404 {"message":"Endpoint '/api/price/batch' does not exist"}
```

**Proof previous data came from NASDAQ:**
- `historical_price_service.py` previously contained `_fetch_from_nasdaq()` function
- `ALLOW_NON_RAPIDAPI_FALLBACK` was set to default `false` in code but NASDAQ fallback code was always present
- Git history shows the NASDAQ code was removed only in recent commits
