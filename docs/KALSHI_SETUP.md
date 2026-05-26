# Kalshi setup for `poly` (US traders)

You can use Kalshi today. Polymarket US is waitlist-only; global Polymarket is blocked for US order placement.

## What works without an API key

```bash
poly kalshi              # list 15m BTC/ETH/SOL markets
poly kalshi-dry          # one snapshot of signals
poly kalshi-dry --duration 300   # watch for 5 minutes
```

When you see a green **▶** line, open the **Kalshi app** and place that trade by hand.

## Phase 3: API keys (optional, for auto-trading later)

1. Log in at [kalshi.com](https://kalshi.com) (VPN off).
2. Go to **Settings → API Keys**.
3. Generate an RSA key pair on your Mac:

```bash
openssl genrsa -out kalshi_private.pem 2048
openssl rsa -in kalshi_private.pem -pubout -out kalshi_public.pem
```

4. Upload `kalshi_public.pem` to Kalshi. Copy the **API Key ID** they give you.
5. Add to `~/Projects/poly/.env` (never commit this file):

```
KALSHI_API_KEY=your-uuid-here
KALSHI_PRIVATE_KEY_PATH=/Users/you/.kalshi/kalshi_private.pem
```

6. Tell the `poly` agent when ready — we will wire signed order placement.

Until then, **kalshi-dry + manual trades** is the safe path.
