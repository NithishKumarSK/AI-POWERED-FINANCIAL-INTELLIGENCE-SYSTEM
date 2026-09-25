# Tastytrade Options Backtesting Integration

## The Breakthrough

After many days of testing, the correct options leg `type` value was discovered:

| Field | Correct Value | Broken Values |
|-------|--------------|---------------|
| `type` | `"equity-option"` | `"option"`, `"equity"`, `"call"`, `"put"` |
| `direction` | `"short"` or `"long"` | `"sell"`, `"buy"` |

Using the wrong `type` returns:
```json
{
  "type": "unknown",
  "statistics": null,
  "trials": null,
  "profitLoss": "0"
}
```

## Verified Working Payload

```json
{
  "startDate": "2021-06-25",
  "endDate": "2026-06-24T00:00:00Z",
  "symbol": "SPY",
  "status": "pending",
  "entryConditions": {
    "frequency": "every day"
  },
  "exitConditions": {},
  "legs": [
    {
      "type": "equity-option",
      "direction": "short",
      "quantity": 1,
      "side": "put",
      "daysUntilExpiration": 45,
      "strikeSelection": "delta",
      "delta": 30
    },
    {
      "type": "equity-option",
      "direction": "short",
      "quantity": 1,
      "side": "put",
      "daysUntilExpiration": 45,
      "strikeSelection": "delta",
      "delta": 30
    }
  ]
}
```

## API Endpoints

- **Auth:** `POST https://api.tastyworks.com/oauth/token`
- **Create Backtest:** `POST https://backtester.vast.tastyworks.com/backtests`
- **Poll Status:** `GET https://backtester.vast.tastyworks.com/backtests/{id}`
- **Get Logs:** `GET https://backtester.vast.tastyworks.com/backtests/{id}/logs`

> **Important:** Never use `https://api.cert.tastyworks.com` — that is the sandbox/cert environment and does not support this integration.

## Environment Variables

Add to `.env` (never commit):

```bash
TASTYTRADE_API_BASE_URL=https://api.tastyworks.com
TASTYTRADE_BACKTESTER_BASE_URL=https://backtester.vast.tastyworks.com
TASTYTRADE_REFRESH_TOKEN=<your_refresh_token>
TASTYTRADE_ACCESS_TOKEN=<your_access_token>  # optional, expires ~15min
TASTYTRADE_CLIENT_SECRET=<your_client_secret>  # if using client credentials flow
TASTYTRADE_USER_AGENT=ajay-ai-finance/1.0
```

## Access Token Flow

1. The service first checks for a cached token (valid for 14 minutes).
2. If expired, it calls `POST /oauth/token` with `grant_type=refresh_token`.
3. The new access token is cached and used for subsequent requests.
4. Never print, log, or expose the token value.

## Validation Gate

Every backtest result is validated before display. A result is **rejected** if:
- `leg_type == "unknown"` — wrong `type` in payload
- `statistics == null` — no statistics returned
- `trials == null / empty` — no trial data
- All `profitLoss == 0` — placeholder/unconfigured response

Only when all checks pass is the result shown as successful.

## Options vs Equities

The tastytrade Backtester API is **options-only**. For stock/equity backtesting, use the **Internal Backtesting** page which runs against `data/stock_prices_daily.csv`.

## Code Location

| Component | File |
|-----------|------|
| Auth service | `src/services/tastytrade_auth_service.py` |
| Backtester service | `src/services/tastytrade_backtester_service.py` |
| Backtest models | `src/models/backtest_models.py` |
| Payload tests | `src/tests/test_tastytrade_payload.py` |
| Parser tests | `src/tests/test_tastytrade_parser.py` |
| UI page | `streamlit_app.py` → `tastytrade_options_backtesting_interface()` |
