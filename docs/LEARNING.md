# NorthStar Learning Notes (start here, no jargon)

A plain-words guide for learning Kalshi/Polymarket before risking any money.
Re-read this anytime. There is no rush.

---

## Step 1 — What you're actually buying ✅

Every market is just a **yes/no question** that gets answered soon, like:

> "Will Bitcoin be above $60,340 in 15 minutes?"

The answer ends up **YES** or **NO**.

You buy a **ticket** for the side you believe:

- Think the answer is YES → buy a **YES ticket**
- Think the answer is NO → buy a **NO ticket**

**Every winning ticket pays exactly $1. A losing ticket pays $0.**

### The price = the odds

The price of a ticket tells you how likely the crowd thinks that side is:

| Price you pay | Crowd is saying | If you WIN | If you LOSE |
| ------------- | --------------- | ---------- | ----------- |
| 20¢           | "unlikely"      | get $1 (big win) | lose 20¢ |
| 50¢           | "coin flip"     | get $1     | lose 50¢    |
| 80¢           | "very likely"   | get $1 (small win) | lose 80¢ |

**Cheap ticket = long shot, big reward. Expensive ticket = safe-ish, small reward.**

### Real-life analogy

A rain bet with a friend: "Pay me 30¢ now. If it rains, I pay you $1. If not, I
keep your 30¢." The **30¢ is the price**, the **$1 is the payout**. That's the
whole game.

### Quick self-check

- Buy a NO ticket for 25¢, answer is NO → ticket is worth **$1** (you profit 75¢).
- A YES ticket costs 80¢ → the crowd thinks YES is **very likely (~80%)**.

---

## Step 2 — Profit & Loss ✅

How to know what you'll make or lose *before* you click buy.

You only need two numbers:

1. **Ticket price** — what one ticket costs (from Step 1)
2. **Dollars in** — how much you are about to spend

Do this math *before* you click. After you click, wait until the question is
answered. Until then you have not won or lost yet.

### Per ticket (always)

Every winning ticket still pays **$1**. Every losing ticket still pays **$0**.

| You pay | If you WIN | If you LOSE |
| ------- | ---------- | ----------- |
| 20¢     | keep $1, profit **80¢** | lose **20¢** |
| 50¢     | keep $1, profit **50¢** | lose **50¢** |
| 80¢     | keep $1, profit **20¢** | lose **80¢** |

Same pattern every time:

- **Win** = `$1 − price` per ticket
- **Lose** = `price` per ticket

Cheap tickets: small loss if you're wrong, big gain if you're right.
Expensive tickets: the opposite. Your **whole dollars in** is still at risk
either way.

Real venues take a small cut (fees). Ignore that while learning — your real
win will be a little smaller than these numbers.

### How many tickets does $5 buy?

Tickets = dollars in ÷ price.

**$5 on a 25¢ ticket** → 20 tickets

| If you… | You get back | Profit / loss |
| ------- | ------------ | ------------- |
| WIN     | $20          | **+$15**      |
| LOSE    | $0           | **−$5**       |

**$5 on an 80¢ ticket** → 6.25 tickets

| If you… | You get back | Profit / loss |
| ------- | ------------ | ------------- |
| WIN     | $6.25        | **+$1.25**    |
| LOSE    | $0           | **−$5**       |

Same $5 at risk. The cheap ticket pays a lot more when it hits. The expensive
ticket barely pays extra when it hits — and you still lose the full $5 when
it misses.

### Rain bet, continued

You paid your friend 30¢. If it rains, they pay you $1 (you are up 70¢). If it
stays dry, they keep the 30¢ (you are down 30¢). You can know both numbers
*before* the sky does anything. That's profit and loss.

### Quick self-check

- You spend **$2** on YES at **40¢**. That's 5 tickets. If YES wins, you get
  $5 back → profit **$3**. If YES loses, you get $0 → lose **$2**.
- You buy one NO ticket at **70¢**. If NO wins, profit **30¢**. If YES wins
  instead, you lose **70¢**.

### After the fact (not this step)

`northstar practice pnl` shows whether the *practice account* is up or down
after trades settle. This step is the opposite: the two numbers *before* you
click. Edge (why a ticket might be a good buy) is Step 3. Buying both sides
is Step 4.

---

## Step 3 — Edge ✅

Why the bot sometimes says "this ticket looks too cheap — buy it."

**Edge** is the gap between what the crowd is charging and what the bot thinks the ticket is worth.

### Two numbers, not one

Step 1’s price is the **crowd’s** number. The bot also has **its own** guess of the chance YES (or NO) is right. Same $1 ticket. Two opinions.

| Number | Who | Example |
| ------ | --- | ------- |
| Ticket price | the crowd | YES costs **40¢** |
| Fair value | the bot’s guess | bot thinks YES is more like **50¢** |

**Edge = bot’s guess − crowd’s price.**

Here: 50¢ − 40¢ = **+10¢**. The bot is saying the ticket looks **10¢ too cheap**.

A negative edge is the opposite: the crowd is already charging more than the bot thinks it’s worth. That ticket looks **too expensive**.

This is not profit-and-loss from Step 2. Step 2 is what you make *if* you win or lose. Edge is only “is this a good *price*?”

### A $2 example

Crowd: YES at **40¢**. Bot’s guess: **50¢**. Edge: **+10¢**.

You still use Step 2 for the dollars. $2 at 40¢ is 5 tickets:

| If you… | You get back | Profit / loss |
| ------- | ------------ | ------------- |
| WIN     | $5           | **+$3**       |
| LOSE    | $0           | **−$2**       |

The +10¢ edge did **not** lock in +$3. It only means the bot prefers this 40¢ price to its 50¢ guess. If YES loses, you still lose the $2.

If the crowd charged **80¢** and the bot guessed **70¢**, edge = 70¢ − 80¢ = **−10¢**. Same Step 2 math would still apply if you bought — but the bot would say the ticket looks too expensive, so the usual move is **don’t click**.

### Before you click

- **Positive edge** feels like: “I’d rather buy this than the price suggests.” The bot may say it looks too cheap. You still decide.
- **Negative edge** feels like: “I’d be overpaying.” The bot stays quiet, or tells you to wait.
- A tiny gap is not a green light. The bot waits unless the gap is large enough to care about.

Most of the time the right move is still to wait.

### It is only an opinion

The bot’s guess can be wrong. The crowd can be right. Edge does not change Step 2: until the question is answered, you have not won or lost. A “cheap” ticket that loses still loses your dollars in.

### Quick self-check

YES costs **80¢**. The bot’s guess is **70¢**. Is the edge positive or negative? Does the ticket look too cheap, or too expensive? (Negative. Too expensive. Don’t buy just because the payout would still be $1.)

### Not this step

Buying **both** sides cheap (a hedge) is Step 4. This step is one ticket, one price, one guess.

---

## Step 4 — Hedging (save for last, it's the hardest)

The trick of buying BOTH sides cheap so you win no matter what.

---

## Golden rules while learning

- No money until a concept actually clicks. "I need to learn first" is the
  smart move, not a weakness.
- When you do start: tiny size ($2–$5), one trade at a time.
- The bot only *suggests*. You always decide and click manually.
- Most of the time the right move is to **wait**. Doing nothing is a position.
