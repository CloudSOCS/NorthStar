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

## Step 4 — Hedging ✅

A **hedge** is buying **both** sides (YES and NO) cheap enough that you no longer need to guess which answer is right.

### Why buy the other side?

Step 1–3 are one ticket. If you only hold YES, you need YES to win. Buying NO as well is how you **offset** that. You are no longer making a pure win-or-lose bet on the question.

You only do this when **both** tickets are cheap enough that the two prices **add up to less than $1**. Then the winning side still pays $1, and that $1 is more than you paid for the pair.

If the two prices add up to **more than $1**, you lose money no matter who wins. That is not a hedge. That is overpaying for both sides.

### Same $1 either way

One YES ticket + one NO ticket. Exactly one of them pays **$1**. The other pays **$0**.

**Cheap pair:** YES **40¢** + NO **40¢** = **80¢** in.

| If… | You get back | Profit / loss |
| --- | ------------ | ------------- |
| YES wins | $1 (YES pays, NO is $0) | **+$20¢** |
| NO wins  | $1 (NO pays, YES is $0) | **+$20¢** |

Same result either way. You stopped caring who is right.

**Expensive pair:** YES **60¢** + NO **55¢** = **$1.15** in. You still get $1 back. You lose **15¢** either way. Skip it.

### A $2 + $2 example

YES at **40¢**, NO at **40¢**.

- $2 on YES → 5 YES tickets  
- $2 on NO → 5 NO tickets  
- **$4** in total  

Five tickets on the winning side pay **$5**. The losing side pays **$0**.

| If… | You get back | Profit / loss |
| --- | ------------ | ------------- |
| YES wins | $5 | **+$1** |
| NO wins  | $5 | **+$1** |

Compare that to Step 2, $2 on YES only at 40¢: win **+$3** or lose **−$2**. The hedge traded that lottery for a smaller **+$1** that does not depend on the answer.

Fees still nibble. Real venues take a cut, so your locked amount will be a little smaller than these numbers.

### A hedge is not edge

Step 3’s edge is “does this **one** ticket look too cheap vs the bot’s guess?” A hedge does **not** create that. Buying both sides does not mean the bot thought YES (or NO) was a good directional buy. It only means the **pair** cost less than $1.

If you do not have a cheap pair, wait. Most of the time the right move is still to wait.

### Quick self-check

You buy one YES at **45¢** and one NO at **45¢**. How much did the pair cost? If YES wins, what do you get back, and what is the profit? Is it the same if NO wins? (90¢ in. Get $1 back. Profit **+10¢**. Yes — same either way.)

### Not live yet

This is still a teaching step. You decide and click (or don’t). Live Kalshi orders are not wired. Practice and dry-run can *show* a hedge; they do not place a real order for you.

---

## How the four steps fit ✅

Read these in order. They are four different questions, not four ways to say “buy.”

| Step | Question | One line |
| ---- | -------- | -------- |
| 1 | What am I buying? | A YES or NO ticket. Winner pays **$1**. Loser pays **$0**. |
| 2 | What do I make or lose? | **Win** = `$1 − price`. **Lose** = `price`. Do this *before* you click. |
| 3 | Is this a good *price*? | **Edge** = bot’s guess − crowd’s price. Too cheap vs too expensive. Not locked profit. |
| 4 | Do I need to guess the answer? | A **hedge** is both sides cheap (pair under **$1**). Same dollars either way. Not edge. |

**One ticket** (Steps 1–3): you care who is right. Check P&L, then ask whether the price looks too cheap. A positive edge still loses if the answer is wrong.

**Both sides** (Step 4): you stop caring who is right, *if* the pair is cheap enough. If the pair costs more than $1, skip it.

You never need all four on every market. Often you only need Step 2 and then **wait**.

### What this is not

- Not a live order. Kalshi live placement is still unwired. The bot *suggests*. You click, or you don’t.
- Not a promise. Edge is an opinion. A hedge only helps when the pair is actually cheap.
- Not a reason to always trade. Tiny gap, no cheap pair, unclear P&L → wait.

### Quick self-check

YES is **40¢**. The bot’s guess is **50¢**. You buy **only** YES (no NO). Which steps are you using — and which are you not? (1–3: a ticket, P&L, and a +10¢ edge. Not 4: you still need YES to win.)

To try these four questions on a live Kalshi 15m market (no order is placed):

`northstar practice walk`

Optional: `northstar practice walk --save` writes a local lesson notebook (`~/.poly/walk_journal.json`). That is not a trade. Read it with `northstar practice journal`. Replay the newest lesson with `northstar practice last`. Machine-readable dump: `northstar practice last --json` or `northstar practice journal --json`. Orientation: `northstar status` (or `--json`).

---

## Golden rules while learning

- No money until a concept actually clicks. "I need to learn first" is the
  smart move, not a weakness.
- When you do start: tiny size ($2–$5), one trade at a time.
- The bot only *suggests*. You always decide and click manually.
- Most of the time the right move is to **wait**. Doing nothing is a position.
