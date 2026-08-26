# NorthStar Cheat Sheet (copy & paste)

## 0. Before you start (once per session)
Log into https://kalshi.com in your browser, so the auto-opened page lets you trade.
No VPN while on Kalshi.

## 1. Start the watcher (the main one)
```bash
cd /Volumes/App/NorthStar
source .venv/bin/activate
northstar kalshi-dry --duration 600 --strategy both --alert --speak --open
```

What the flags do:
- `--duration 600`  watch for 10 minutes (use 1800 for 30 min)
- `--strategy both`  watch markov AND hedged (or use `markov` / `hedged`)
- `--alert`          chime + desktop notification when a signal fires
- `--speak`          also says the signal out loud
- `--open`           opens the Kalshi market page in your browser

## 2. Quieter versions (pick one)
```bash
# Markov only, just a chime + browser
northstar kalshi-dry --duration 600 --strategy markov --alert --open

# Notification only, no sound
northstar kalshi-dry --duration 600 --strategy both --alert --no-sound

# Just watch, no alarms
northstar kalshi-dry --duration 600 --strategy both
```

## 3. Test that alarms/browser work (no waiting)
```bash
python -c "from poly.alerts import open_url; open_url('https://kalshi.com/markets/kxbtc15m')"
```

## 4. Sync latest code (run on each Mac)
```bash
cd /Volumes/App/NorthStar
git pull origin main
```

## 5. Check practice account (fake money)
```bash
northstar practice status
northstar practice pnl
```

## 6. Walk a real Kalshi market through Steps 1–4 (no order)
```bash
northstar practice walk
northstar practice walk --asset ETH --spend 2
northstar practice walk --save
```
Prints ticket price, tiny-size P&L, edge, and a YES+NO hedge check.
`--save` appends that snapshot to `~/.poly/walk_journal.json` (a notebook, not a trade).
Always ends with: this is practice only — no live order was placed.

## 7. Read the practice journal
```bash
northstar practice journal
northstar practice journal --last 5
```
Shows recent saved walks (time, asset, YES/NO, spend, edge, hedge). Read-only.

## 8. Replay the last saved lesson
```bash
northstar practice last
northstar practice last --n 3
```
Reprints the newest walk(s) in the same Step 1–4 voice. No market fetch. No order.

---
Reminder: the bot only SUGGESTS. You click Yes/No and enter the amount yourself.
When learning, it's fine to let it fire and NOT buy. Tiny size ($2-$5) when you do.
