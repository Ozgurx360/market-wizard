# Market Wizard — a Claude Code plugin

Personal Claude Code plugin: trading-strategy & options skills for an Interactive Brokers workflow.
A **decision aid** — not an autotrader, not financial advice.

## Skills
- **`market-wizard:leaps`** — full-lifecycle long-call LEAPS (live now)
- **`market-wizard:covered-call`** — full-lifecycle covered calls on shares you own (live now)
- **`market-wizard:chart-read`** — TA / charting read (RSI · MACD · SMA · Bollinger + date-stamped chart) that *feeds* `leaps` & `covered-call` (live now)
- _planned:_ `market-wizard:csp` (cash-secured puts)

---

## The strategy — `leaps`

Turns a structured **LEAPS decision mechanism** into a deterministic, IBKR-wired procedure that runs the
**entire lifecycle of long-dated call positions** — for both **single long calls** and **call debit
spreads (verticals)**.

**Core idea.** A deep-in-the-money LEAPS call (long-dated, high delta) behaves like a leveraged,
lower-capital stock substitute. The edge is captured — and protected — by (1) entering at the right
delta and duration, (2) paying as little **extrinsic (time) value** as possible, and (3) actively
managing the position through its life rather than buy-and-forget. Every analysis surfaces the
**intrinsic vs extrinsic split** and the **Greeks**, because that split is what tells you whether you're
holding clean leverage or bleeding theta.

### Entry (new positions)
- **Delta band 0.70–0.85** (sweet-spot ~0.80) — deep enough to track the underlying, not so deep you overpay.
- **≥ 270 DTE** to qualify as a LEAPS; new legs opened **≥ 540 DTE** for maximum runway.
- **Sized by asset class:** blue-chip ≈ 0.80Δ / up to ~20% notional · growth ≈ 0.70Δ / ~10% · speculative →
  a **debit spread** (caps cost & vega) at ~3%.
- **IV-rank aware** — avoid overpaying for time value when implied vol is rich; prefer entries on IV pullbacks.

### Lifecycle management (existing positions)
Each position is classified to one verdict, with trigger levels expressed as **underlying prices** so they're
actionable at a glance:
- **HOLD** — delta in band, clear of the roll window.
- **ROLL-OUT** — duration is running down (inside the **90–120 DTE** window; hard floor 45 DTE) → extend time.
- **ROLL-UP** — delta has run too high (≥ 0.90) → harvest gains / free capital, reset delta back into the band.
- **ROLL-DOWN** — delta drifted too low → restore exposure.
- **TRIM** — lock partial gains.
- **CLOSE / CLOSE-CANDIDATE** — a **time-aware stop**: a far-dated, slow-bleeding position becomes a
  *candidate* (not a reflex close); it shows the economics plus a **cost-of-waiting** forward-decay view,
  **asks for your conviction**, then concludes.
- **Spreads** are managed as one unit (profit-take ≈ **60% of max width**); **PMCC** short legs ride against
  the long call and are never sold below basis.

### What it deliberately does *not* do
- **Never infers your thesis from price.** "Bullish / intact / broken" is a **human input** — it asks; on an
  impaired position it shows the math and asks conviction *before* proposing a close.
- **Read-only by default.** It pulls quotes / positions / Greeks and proposes exact limit orders, but
  **places nothing.** Every option action is a **copy-paste IBKR combo ticket you approve and transmit
  yourself** (the connector can't place option orders); equity/ETF orders are drafted only after you approve
  that specific one by reference.
- **Stops and asks** whenever something is ambiguous, missing, or stale — it flags, it doesn't guess.
- Greeks come from live IV (Black-Scholes fallback if a field is missing). Your **account number is read from
  your own CLAUDE.md/memory** — if none is set, it asks.

All thresholds — deltas, DTE windows, sizing, profit-takes — live in a **CONFIG block** at the top of the
skill, so you tune the whole strategy to your own risk tolerance without touching the logic.

---

## The strategy — `covered-call`

Sells calls against shares you already own, running the **full lifecycle of a short-call overlay** — which
call to **write**, and how to **manage** it through to expiry, roll, or assignment. Shares-only; the
LEAP-backed "poor-man's covered call" lives in `leaps`.

**Core idea.** A covered call turns shares you're holding into an income stream — you collect premium in
exchange for capping upside at the strike. The whole skill is **intent-driven**: before it suggests anything
it asks *why* you're writing, because that changes the strike, the roll rules, and the guardrails.

### Intent — the master switch
- **Income-on-keepers** — keep the shares, harvest premium; far-OTM strikes, defend hard against assignment.
- **Exit-oriented** — happy to be called away at a good price; closer strikes, let assignment happen.
- **Repair-failing** — a down position you're grinding back: writes are **adjusted-basis-aware**, any strike
  below your true (premium-reduced) basis is flagged as a *managed exit, not repair*, and the **rebound risk**
  is modeled before you cap a recovery.

### Every write shows the numbers that matter
- **Projected annualized return — both ways:** *return-if-flat* (the call expires, you keep the premium) and
  *return-if-called* (assigned — total including the move to the strike).
- **Cumulative premium collected to date** per ticker and the resulting **adjusted cost basis**
  (raw basis − net call premium), sourced from your IBKR statement history (which carries the per-trade
  call/put + strike the live feed doesn't).
- Downside cushion, upside cap, delta, and ex-dividend / earnings flags.

### Lifecycle management (existing short calls)
One verdict per position, classified top-down:
- **HOLD** · **BUY-TO-CLOSE** (profit-take ≈ 50% of the credit) · **ROLL-UP / ROLL-OUT / ROLL-UP&OUT** when the
  strike is tested · **LET-ASSIGN** (exit intent, or repair at/above basis) · **DEFEND** (in-the-money into
  ex-dividend or earnings → early-assignment risk).

### What it deliberately does *not* do
- **Never writes naked** — verifies you hold ≥ 100 shares per contract.
- **Never quietly turns "repair" into a loss** — any strike below your adjusted basis is flagged as a managed
  exit with the dollar loss-if-assigned spelled out, requiring your acknowledgment.
- **Never infers your thesis** — a broken thesis is a human input; it recommends closing rather than writing
  into a falling knife.
- **Read-only by default** — option writes/rolls are **copy-paste IBKR tickets you transmit yourself**; nothing
  is placed without your per-order approval. A full-portfolio review fans out **read-only** and hands you a
  ranked action board.

Like `leaps`, every threshold — delta bands per intent, profit-take %, DTE window, roll triggers — lives in a
**CONFIG block** you can tune.

---

## The read — `chart-read`

The **technical-analysis layer** that *feeds* the options skills rather than duplicating them. Turns one
ticker into a disciplined, reproducible read: the weekly-bias / daily-trigger indicator stack
(**RSI · MACD · 200/50-SMA · Bollinger**), a divergence-candidate flag, an **IV-rank** check (relative, not
absolute IV), a **date-stamped Price/RSI/MACD chart**, and a dated decision entry with explicit trigger
levels appended to your decisions log.

**Core idea.** Regime and momentum are *facts off the chart*; conviction is *yours*. `chart-read` produces
the chart-and-regime read — weekly sets **bias** (price vs the 40-wk line), daily times the **trigger**
(price vs the 200-SMA) — then hands the option itself (which strike, when to roll, the annualized-return
math) to `leaps` / `covered-call`. It never infers your thesis and it places no orders.

- **Read-only.** Pulls quotes / history, computes the stack, renders the chart — **no orders**, ever.
- **IV-rank, not absolute IV** decides whether premium is rich enough to sell (≥ 60 on the 13-wk rank).
- **Divergence is a candidate, not a trade** — gated behind confluence (location · divergence · confirmation
  · timeframe-aligned) and confirmed on the chart; it states the failure modes.
- A small **CONFIG block** documents the indicator defaults; the chart engine (`scripts/deepdive.py`,
  numpy / pandas / matplotlib) validates its input and **never emits a raw traceback** — bad data returns a
  one-line `{"error": …}` and a non-zero exit.

Handoff: `chart-read` ends at the **read + chart + logged verdict + trigger levels** → `leaps` (long calls /
PMCC / verticals) · `covered-call` (calls on shares). `csp` joins the chain once it ships.

---

## Install
```
/plugin marketplace add Ozgurx360/market-wizard
/plugin install market-wizard@market-wizard
```
Then `/help` → `/market-wizard:leaps`. Trigger it naturally — *"review my LEAPS,"* *"is this a good entry on
TICKER,"* *"should I roll X,"* *"build a debit spread on Y,"* *"trim/close this position."*

For `covered-call` — *"review my covered calls,"* *"write a covered call on TICKER,"* *"how much premium have I
collected on TICKER,"* *"should I roll my short call,"* *"reduce my cost basis by selling calls."*

For `chart-read` — *"chart-read TICKER,"* *"technical / regime read on TICKER before I write a call,"* *"is
TICKER's IV-rank rich enough to sell premium,"* *"where's my entry trigger / invalidation on TICKER."*

## Update (after a push)
```
/plugin marketplace update market-wizard && /reload-plugins
```
No version pin — every push is the latest.

## Add a skill later
Drop `plugins/market-wizard/skills/<name>/SKILL.md`, commit, push, `/reload-plugins` → auto-loads as
`market-wizard:<name>`. (CSP will follow the same lifecycle-and-config philosophy as `leaps` and `covered-call`.)

## Layout
```
.claude-plugin/marketplace.json          marketplace catalog
plugins/market-wizard/
  .claude-plugin/plugin.json             plugin manifest
  skills/leaps/SKILL.md                  the LEAPS skill
  skills/covered-call/                   covered-call skill (SKILL.md + portfolio-scan workflow)
  skills/chart-read/                     TA read + chart engine (SKILL.md + scripts/deepdive.py)
```

## Disclaimer
A decision-support tool — **not financial advice and not an automated trading system.** It analyzes and
proposes; you review and place every order yourself.
