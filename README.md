# Market Wizard — a Claude Code plugin

Personal Claude Code plugin: trading-strategy & options skills for an Interactive Brokers workflow.
A **decision aid** — not an autotrader, not financial advice.

## Skills
- **`market-wizard:leaps`** — full-lifecycle long-call LEAPS (live now)
- _planned:_ `market-wizard:csp` (cash-secured puts) · `market-wizard:cc` (covered calls)

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

## Install
```
/plugin marketplace add Ozgurx360/market-wizard
/plugin install market-wizard@market-wizard
```
Then `/help` → `/market-wizard:leaps`. Trigger it naturally — *"review my LEAPS,"* *"is this a good entry on
TICKER,"* *"should I roll X,"* *"build a debit spread on Y,"* *"trim/close this position."*

## Update (after a push)
```
/plugin marketplace update market-wizard && /reload-plugins
```
No version pin — every push is the latest.

## Add a skill later
Drop `plugins/market-wizard/skills/<name>/SKILL.md`, commit, push, `/reload-plugins` → auto-loads as
`market-wizard:<name>`. (CSP and CC will follow the same lifecycle-and-config philosophy as `leaps`.)

## Layout
```
.claude-plugin/marketplace.json          marketplace catalog
plugins/market-wizard/
  .claude-plugin/plugin.json             plugin manifest
  skills/leaps/SKILL.md                  the LEAPS skill
```

## Disclaimer
A decision-support tool — **not financial advice and not an automated trading system.** It analyzes and
proposes; you review and place every order yourself.
