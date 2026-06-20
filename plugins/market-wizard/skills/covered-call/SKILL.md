---
name: covered-call
description: >
  Full-lifecycle covered-call strategy for shares the user holds in their Interactive Brokers
  account: picks which call to WRITE and manages EXISTING short calls — HOLD / BUY-TO-CLOSE /
  ROLL-UP / ROLL-OUT / ROLL-UP&OUT / LET-ASSIGN / DEFEND. Intent-driven (income-on-keepers /
  exit-oriented / repair-failing), always showing the projected annualized return (if-flat and
  if-called) and cumulative premium collected to date. Shares-only (NOT PMCC — that's the leaps
  skill). Trigger on: "write a covered call on TICKER", "sell calls against my shares",
  "manage my covered call", "should I roll/close my short call", "review my covered calls",
  "covered-call health check", "how much premium have I collected on TICKER", "reduce my cost
  basis by selling calls", "what covered call should I sell". Read-only by default; ALL order
  placement requires explicit per-order human approval.
---

# covered-call — Full-Lifecycle Covered-Call Skill (shares-only)

Turns covered-call writing on **shares the user already owns** into a deterministic, IBKR-wired
procedure covering the **whole lifecycle — WRITE (entry), HOLD, ROLL, BUY-TO-CLOSE, LET-ASSIGN,
DEFEND**. It is **intent-driven**: before suggesting anything it asks the user's intent for the
position (income-on-keepers / exit-oriented / repair-failing), and that intent reconfigures
strike/delta selection, roll rules, the assignment stance, and which guardrails bind. Every write
shows the **projected annualized return** (if-flat and if-called) and the **cumulative premium
collected to date**. Decision aid only — not an autotrader, not financial advice.

**Scope boundary (read this):** this skill is **shares-only covered calls** — a SHORT call written
against ≥100 owned shares. **PMCC (poor-man's covered call), long calls, and LEAPS belong to the
`leaps` skill, not here.** This skill never opens a long call and never analyzes a diagonal; if a
short call is backed by a long LEAP rather than shares, that's a PMCC → hand it to `leaps`.

---

## §0. OPERATING MODE — NON-NEGOTIABLE (recommend-only)

1. **Autonomous scope is READ-ONLY.** Without explicit, per-order approval *in the conversation*,
   call ONLY these read tools: `get_account_positions`, `get_account_balances`,
   `get_account_summary`, `get_account_orders`, `get_account_trades`, `get_order_instructions`,
   `get_price_snapshot`, `get_price_history`, `search_contracts`, `get_option_parameters`,
   `get_option_data`.
2. **`create_order_instruction` is EQUITY/ETF ONLY — it cannot place option orders.** Every option
   action (sell-to-open a call, buy-to-close, roll) is therefore a **copy-paste IBKR ticket the user
   enters manually** (see §12). The connector is used **only to SELL the underlying shares** on a
   deliberate equity exit — and only after the user approves that specific order by reference (e.g.
   "place order #2"); then report its instruction ID and tell the user to review/transmit it in IBKR.
   NEVER call `create_order_instruction` / `delete_order_instruction` (cancelling an order also needs
   explicit per-order approval) until the user approves that specific action by reference.
   Confirm fills only by re-reading orders/positions.
3. **Never infer thesis or intent.** Both are **human inputs** — ask. Intent is the master switch
   (§3); thesis is the repair-gate input (§8). Never derive either from price action.
4. When anything is ambiguous, missing, or stale — **stop and ask.** Flag, don't guess.

Loop: *analyze → present report + proposed tickets → user approves a specific one → re-pull fresh
quotes → emit the copy-paste IBKR ticket (options) or construct the LIMIT `create_order_instruction`
(equity share sale only) → report the ticket / instruction ID.*

---

## §1. CONFIG (edit to tune behaviour)

```yaml
account_id: ""                       # resolve from CLAUDE.md/memory; if absent, ASK before any account call

# --- scope ---
scope_right: "C"
min_shares_per_contract: 100         # never write more contracts than floor(shares/100)
exclude_symbols: []

# --- intent master switch (HUMAN input, per position; ask first) ---
intents: ["income_keepers", "exit_oriented", "repair_failing"]
income_keepers:  { delta_min: 0.15, delta_max: 0.20, strike_rule: ">= max(adjusted_basis, nearest_resistance)" }
exit_oriented:   { delta_min: 0.30, delta_max: 0.40, strike_rule: ">= acceptable_sell_price (ask user)" }
repair_failing:  { delta_min: 0.20, delta_max: 0.35, strike_rule: "prefer >= adjusted_basis; below => MANAGED-EXIT flag" }
# nearest_resistance = recent swing high from get_price_history; fallback 52-wk high from
#   get_price_snapshot misc-statistics.high_52w. ONE name throughout (§1/§3/§6); if neither resolves, flag the gap.

# --- write tenor ---
write_dte_min: 30
write_dte_max: 45

# --- management thresholds ---
profit_take_pct: 50                  # buy-to-close when ~this % of the credit is captured
roll_when_delta: 0.50                # short tested -> consider roll up/out (exit_oriented / repair_failing)
roll_when_delta_income: 0.40         # income_keepers defend EARLIER (goal = AVOID assignment), see §7 rule 4
roll_dte_floor: 21                   # roll or close by this DTE (pin/assignment risk)

# --- gates ---
avoid_write_days_before_earnings: 7
exdiv_itm_assignment_flag: true      # ITM short into ex-div => early-assignment flag

# --- return / annualization ---
annualize_denominator: "current_price"   # documentation-only: formulas hardcode S (and adjusted_basis for repair); this key just records the convention
days_per_year: 365

# --- data / execution ---
data_staleness_max_min: 3
order_type: "LMT"
limit_price_rule: "mid_or_better"
tif: "DAY"

# --- ledger ---
ledger_path: "Covered Calls/memory.md"
statements_path: ""                  # folder holding your IBKR Activity Statement CSV exports;
                                     #   resolve from CLAUDE.md/memory. If unknown, ASK before computing the ledger.
                                     #   PRIMARY source for option premium (carries right/strike/expiry + Open/Close Code);
                                     #   get_account_trades only fills the post-CSV gap (§4).

# --- greeks / Black-Scholes assumptions (pin so two runs agree) ---
risk_free_rate_pct: 3.7
bs_dividend_yield_source: "get_price_snapshot dividend-yield.yield_pct"
bs_iv_source_option: "implied-vol.annual_iv (fallback option-midpoint-iv.annualIv)"
bs_iv_source_underlying: "implied-vol-underlying.annual_iv"
```

---

## §2. DATA SOURCES & FIELD MAPPING

| Need | Source | Field / how |
|---|---|---|
| **Held shares** | `get_account_positions` | rows where `secType=STK`: symbol, position(shares), avgCost(raw_basis), mark(`S`) |
| **Existing short calls** | `get_account_positions` | rows `secType=OPT, right=C, position<0`: strike, expiry, qty(=\|position\|), avgCost → `credit_received` (NORMALIZE — see note) |
| Equity / buying power | `get_account_summary`, `get_account_balances` | NetLiquidation, AvailableFunds (for the share-sale leg only) |
| Underlying price `S` | `get_price_snapshot` (underlying) | last/mark |
| **Option premium history (PRIMARY)** | IBKR Activity Statement CSVs (`statements_path`) | `Trades` section, Asset Category `Equity and Index Options`: per row `Symbol` (full OCC, e.g. `XYZ 18JUN26 190 C`), `Date/Time`, `Quantity`(signed: −sell/+buy), `Proceeds` (+sell/−buy), `Comm/Fee` (negative), `Code` (`O`=open / `C`=close). OCC Symbol gives right(C/P)/strike/expiry directly; Code gives open/close. Authoritative source for option attribution — feeds the ledger (§4) |
| **Option premium gap (post-CSV only)** | `get_account_trades` | per trade: symbol, `sec_type` (OPT/STK), side (BUY/SELL), size, price, net_amount, commission, realized_pnl, trade_time, order_id. **`sec_type` present, but NO contract_id/strike/expiry/right — cannot split call vs put; use the Statement CSVs for option attribution.** Only used for the window AFTER the latest CSV's end-date (§4), and only when call-attribution is unambiguous |
| Option mark/bid/ask | `get_price_snapshot` (option) | bid, ask, mark |
| Option **delta, IV, greeks** | `get_price_snapshot` (option) | greeks/modelGreeks if present — see DATA GAPS; fallback Black-Scholes with echoed r/q/IV |
| 52-wk high/low, dividend `q`, ex-div | `get_price_snapshot` (underlying) | `misc-statistics.high_52w`/`low_52w`; `dividend-yield.yield_pct`; ex-div date if present |
| **Chain enumeration** | `get_option_parameters` → `search_contracts` / `get_option_data` | enumerate expiries/strikes to hit the intent delta band |
| Working orders | `get_account_orders`, `get_order_instructions` | avoid duplicate/conflicting orders |

**Computed fields (per share unless noted):**
- `DTE = expiry − today`
- `intrinsic = max(0, S − strike)`
- `extrinsic = option_mark − intrinsic`
- `breakeven_up = strike + credit`        ← the per-share price above which writing cost you vs holding
- `downside_cushion = credit / S`         ← how far S can fall before the write is underwater
- `upside_cap = (strike − S) / S`         ← capped appreciation if called
- `mid = (bid + ask) / 2`; `spread_pct = (ask − bid) / mid × 100`
- expose `delta, gamma, theta, vega, IV` when greeks present
- Position dollars = per-share × `min_shares_per_contract` × \|qty\|

**NORMALIZE the existing short's credit (sign + scale) before any use:** for a SHORT option, position
`avgCost` can arrive **negative and/or per-contract (multiplier-scaled)**, not the absolute per-share
premium the §7 engine and §6 returns assume. Compute `credit_received = abs(avgCost)` made POSITIVE, then
made PER-SHARE — **divide by `multiplier` (default 100) if avgCost is per-contract**. The §7 `captured_pct`
is only correct when `credit_received` and `current_mark` are both positive per-share figures. If the
position field is ambiguous, recompute the credit from the `get_account_trades` sell-to-open price (already
per-share) and confirm against the `get_price_snapshot` mark.

### DATA GAPS — handle gracefully, never fake
- **Delta/greeks missing:** say so. Estimate via Black-Scholes from **standardized inputs** (CONFIG):
  `r = risk_free_rate_pct`, `q = dividend-yield.yield_pct` (per name), IV = `implied-vol.annual_iv`
  (option) / `implied-vol-underlying.annual_iv` (underlying), plus (S, K, DTE); **label "EST"** and
  **echo the assumed r/q/IV** in output so two runs agree. If no greeks and no IV, mark **"delta
  unavailable — limited to price/DTE rules."**
- **Stale/crossed quotes** (older than `data_staleness_max_min`, or bid ≥ ask, or zero): treat as
  unavailable and flag.
- **Missing ex-div / earnings date:** flag the gap rather than assuming a benign window.

---

## §3. INTENT ENGINE (the master switch)

Intent is a REQUIRED human input per position, the master switch for this skill (what
`thesis_status` is to `leaps`). If not supplied, ASK before suggesting anything:

  "What's your intent for <TICKER>? (1) income-on-keepers — keep the shares, harvest premium,
   AVOID being called away; (2) exit-oriented — happy to be called away at a good strike;
   (3) repair-failing — down position, reduce cost basis by writing calls."

The chosen intent selects the CONFIG block (income_keepers / exit_oriented / repair_failing),
which sets delta band, strike rule, roll behavior, and which guardrails bind. Persist the
per-ticker intent in the ledger (§4) so reviews remember it; re-confirm if stale.

| Intent | Delta / strike | Roll behavior | Assignment stance | Key guardrails |
|---|---|---|---|---|
| **income_keepers** | Far OTM ~0.15–0.20Δ; strike ≥ max(adjusted_basis, nearest_resistance) | Roll up-and-out when tested (earlier, ~`roll_when_delta_income`); defend the shares | Bad outcome — AVOID being called away | No ITM into ex-div/earnings |
| **exit_oriented** | Closer ~0.30–0.40Δ; strike ≥ a price you'd happily sell at | Minimal | Desired — let-assign is the goal | Strike ≥ acceptable sell price |
| **repair_failing** | ~0.20–0.35Δ; adjusted-basis aware | Roll out/up cautiously, never below adjusted_basis w/o §8 flag | Flag when strike < adjusted_basis | Adjusted-basis ledger, below-basis flag, rebound model, thesis gate |

---

## §4. Adjusted-basis ledger

**Data source = the IBKR Activity Statement CSVs (PRIMARY), with `get_account_trades` filling only the
post-CSV gap.** `get_account_trades` carries `sec_type` but NO right/strike/expiry — it cannot tell a call
from a put, so it CANNOT be the ledger's primary source. The Statement CSVs carry the full OCC `Symbol`
(right/strike/expiry) and an open/close `Code`, so option premium is attributed from them.

Resolve `statements_path` from your CLAUDE.md/memory; if unknown,
**ASK before computing the ledger.** Read every `U<account>_*.csv` there (yearly immutable files + the
current-year YTD file).

**Step A — primary, from the CSVs.** In each CSV's `Trades` section, take rows where
`Asset Category == "Equity and Index Options"` and the OCC `Symbol` is for TICKER. The OCC Symbol's last
token gives the right; **keep only rows ending in ` C` (calls) — drop puts.** Among the call rows, isolate
the covered-call (SHORT-call) lifecycle:
- **sell-to-open** = `Quantity < 0` AND `Code` contains `O`
- its **buy-to-close** = `Quantity > 0` AND `Code` contains `C`
- **EXCLUDE long-call (directional) trades** — buy-to-open (`Quantity > 0`, `Code` `O`) and its sell-to-close
  (`Quantity < 0`, `Code` `C`). Those are NOT covered-call premium.
```
short_call_rows = CSV option rows for TICKER, Symbol ends " C", restricted to the
                  sell-to-open / buy-to-close covered-call lifecycle above (long-call rows excluded).
# Proceeds is + for sells, − for buys; Comm/Fee is negative.
net_premium_dollars = Σ Proceeds(short_call_rows) − Σ abs(Comm/Fee)(short_call_rows)   # commissions netted out, abs() (see note)
```

**Step B — gap after the latest CSV's end-date.** The YTD CSV ends at its download date and lags real-time
(it can miss the last few weeks). For the window `(latest_CSV_end_date, today]`, pull
`get_account_trades` (sec_type=OPT) for TICKER. Since those rows lack right/strike, attribute them to calls
**only when unambiguous**: (a) TICKER has only ever had calls (no puts) in that window, OR (b) they match a
current short-call position. Net the qualifying gap trades into `net_premium_dollars` the same way
(Σ net_amount − Σ abs(commission), grouped per the connector's per-share price × size × multiplier).
**Otherwise FLAG the ticker:** "recent trades since `<latest_CSV_end_date>` can't be auto-attributed to
calls — refresh the YTD statement or confirm manually" — and exclude them rather than guess.

```
net_premium_per_share    = net_premium_dollars / shares_held    # ONLY valid if shares were NOT partially sold — see PARTIAL-SALE GUARD
adjusted_basis           = raw_share_basis − net_premium_per_share
since_date               = earliest covered-call sell-to-open date for TICKER (across CSVs + gap)
writes_count             = count of distinct sell-to-open ORDERS (not fills) — see note below
```

**PARTIAL-SALE GUARD (do NOT skip — protects the §13 below-basis guardrail).** `net_premium_per_share`
divides by *current* `shares_held`; if shares were partially sold, the premium was earned against the
LARGER lot, so dividing by the shrunken count **over-reduces basis** and can falsely clear a below-basis
strike. Before computing `adjusted_basis`, detect a reduction: compare current `shares_held` against the
share count at the time each premium was collected — derive it from STK sell trades in `get_account_trades`
(or a stored share count in the ledger). If a reduction is detected:
- **Preferred:** denominate each premium by the share count in force *when that premium was collected*
  (per-write share base), not by current shares.
- **Else:** do NOT silently divide by current shares — **FLAG the ticker "adjusted basis unreliable after
  partial sale — confirm manually"** and ask the user before using `adjusted_basis` in any strike/guardrail.

**COMMISSION SIGN (F4).** Commissions arrive with inconsistent signs (a SELL row's `Comm/Fee` is negative,
a BUY-to-close row's can come back positive; the connector's `commission` is likewise inconsistent). Always
net them out with `abs()` so they reduce premium regardless of sign — never add a commission back in.

Headline output line: **"Premium collected to date: $<net_premium_dollars> across <writes_count>
sell-to-open orders (since <since_date>)."**
> `writes_count` counts distinct **sell-to-open ORDERS, not fills** — one write can fill in many pieces under
> a single order (e.g. 10 calls filled in 6 pieces = ONE write). Group fills by `order_id` (connector) or by
> Date/Time+order line (CSV). A roll's sell leg is its own order, so a rolled position contributes more than
> one. Do not read `writes_count` as N independent income events, nor as a fill count.

Persist per ticker in `Covered Calls/memory.md`:

  | Ticker | Intent | Shares | Raw basis | Net premium $ | Adjusted basis | Writes | Since | Last reviewed |

On every run: RECOMPUTE net_premium from the CSVs (Step A) plus any attributable gap trades (Step B),
compare to the stored row, and FLAG any discrepancy (the `leaps` memory-reconcile pattern) instead of
trusting one source — e.g. a write that settled since last run, a closed position still listed, a basis
that moved, or gap trades that couldn't be auto-attributed.
First run for a ticker: create the row. If `Covered Calls/memory.md` / `CLAUDE.md` don't exist,
create them (CLAUDE.md says "read memory.md first") per the user's domain conventions.

---

## §5. QUICK-PATH ROUTER (run FIRST)

Classify intent before loading machinery:
- "write/sell a call on TICKER" (one ticker)         -> ENTRY engine (§6), inline.
- "manage/roll/close my short on TICKER"             -> MANAGE engine (§7), inline.
- "review my covered calls" / no ticker / portfolio  -> WORKFLOW fan-out (§11) -> action board.
- "how much premium on TICKER"                        -> ledger (§4) only.
First filter: **skip any symbol in `exclude_symbols`** — drop it before routing (and if the user names an
excluded ticker explicitly, say it's excluded and ask whether to override). If unclear, ask which.

---

## §6. ENTRY — which call to write (per intent)

```
require intent (§3); p = CONFIG[intent]
coverage: max_contracts = floor(shares_held / min_shares_per_contract); if 0 -> STOP (need 100+ shares)
gates (§9): if earnings within avoid_write_days_before_earnings -> WARN/WAIT unless intent accepts it
expiry: choose expiry in [write_dte_min, write_dte_max]
strike: pick strike whose delta is in [p.delta_min, p.delta_max] AND satisfies p.strike_rule
   income_keepers: strike >= max(adjusted_basis, nearest_resistance)
   exit_oriented:  strike >= acceptable_sell_price (ASK the user the price)
   repair_failing: prefer strike >= adjusted_basis; if best premium needs strike < adjusted_basis,
                   set MANAGED-EXIT flag (§8) and show the realized loss-if-assigned
premium = mid(option)    # mid-or-better limit
```
ALWAYS report both annualized returns (per share), denominated on current price S:
```
return_if_flat   = premium / S × (days_per_year / DTE)                       # call expires, keep premium
return_if_called = (premium + strike − S) / S × (days_per_year / DTE)        # assigned: total incl. move to strike
```
For repair_failing ALSO report (vs adjusted basis):
```
# PROPOSED NEW write (§6 ENTRY) — this premium is NOT yet in adjusted_basis, so ADD it:
return_if_called_vs_adjbasis = (premium + strike − adjusted_basis) / adjusted_basis × (days_per_year / DTE)
   # prints a LOSS when strike < adjusted_basis — this is the managed-exit reality
```
> **Premium-double-count rule (F2) — proposed vs existing.** `adjusted_basis` (§4) already nets ALL booked
> covered-call premium, *including any currently-open short*. So: a **PROPOSED new write** (this §6 path) is
> not yet in history → **ADD its premium** (formula above). An **EXISTING open short** (the §7/§8 MANAGE/repair
> path) is already inside `adjusted_basis` → **do NOT re-add its premium**; use the existing-short forms in §6
> below and §8. `return_if_flat` and `return_if_called` (on S, above) are UNCHANGED for both — they are
> denominated on current price, not adjusted basis.

For an **EXISTING short** under review (MANAGE/repair, premium already in adjusted_basis — do NOT re-add):
```
return_if_called_vs_adjbasis = (strike − adjusted_basis) / adjusted_basis × (days_per_year / DTE)
   # no + premium: the short's credit is already inside adjusted_basis
```
Also report: downside_cushion = premium/S, upside_cap = (strike−S)/S, delta, ex-div/earnings flags.
Output: contract, SELL-TO-OPEN limit, both returns, cushion/cap, coverage check. PENDING APPROVAL.

---

## §7. MANAGE — existing short call against held shares
```
captured_pct = (credit_received − current_mark) / credit_received × 100   # % of premium decayed in your favor
# credit_received and current_mark must BOTH be POSITIVE, PER-SHARE figures (normalize avgCost per §2:
#   abs() + divide by multiplier if per-contract). If the position field is ambiguous, recompute from the
#   get_price_snapshot option mark before using captured_pct.
# 1. CLOSE        IF thesis_status == "broken" (human input) -> BUY-TO-CLOSE, then decide shares separately
# 2. DEFEND       IF short is ITM AND (ex-div before expiry OR earnings before expiry) -> flag early-assignment;
#                    recommend buy-to-close or roll up&out ahead of the date
# 3. BUY-TO-CLOSE IF captured_pct >= profit_take_pct -> harvest, free the shares to re-write
# 4. ROLL         use an INTENT-AWARE roll-delta trigger (income_keepers defend EARLIER):
#                    income_keepers -> IF delta >= roll_when_delta_income (0.40): ROLL-UP&OUT (goal = AVOID assignment, defend the shares)
#                    repair_failing -> IF delta >= roll_when_delta (0.50): ROLL-OUT (or up&out) cautiously; never below adjusted_basis without §8 flag
#                    exit_oriented  -> IF delta >= roll_when_delta (0.50): usually LET-ASSIGN instead of rolling
# 5. EXPIRY/PIN   IF DTE <= roll_dte_floor -> ROLL-OUT or CLOSE (avoid pin/assignment)
# 6. LET-ASSIGN   IF exit_oriented AND ITM near expiry  (or repair AND assignment >= adjusted_basis) -> allow assignment
# 7. WATCH        approaching a trigger (delta within 0.05, captured within 10pts, DTE within roll_dte_floor+7)
# 8. HOLD         else
```
Every roll is two legs (BUY-TO-CLOSE + SELL-TO-OPEN) -> ONE copy-paste IBKR combo ticket, net
debit/credit limit; tell the user to enter as one combo, never leg in.

---

## §8. Repair machinery (intent = repair_failing)

1. ADJUSTED-BASIS AWARE: every strike compared to adjusted_basis (§4).
2. BELOW-BASIS FLAG: any candidate strike < adjusted_basis is a MANAGED EXIT at a realized loss,
   NOT "repair". Print the dollar loss-if-assigned, and **mind the premium-double-count rule (F2):
   `adjusted_basis` already contains every booked premium, including any currently-open short.**
   - **PROPOSED NEW write** (not yet in history): its premium is NOT in adjusted_basis, so ADD it —
     `loss_if_assigned = (strike − adjusted_basis + premium) × 100 × qty` (consistent with §6's
     proposed-write `return_if_called_vs_adjbasis`, which includes it).
   - **EXISTING open short** (under MANAGE/repair): its premium is ALREADY in adjusted_basis — do NOT
     re-add it — `loss_if_assigned = (strike − adjusted_basis) × 100 × qty`.
   In both, a loss prints when negative. Worked check (existing short): adjusted basis 40.00, strike 38,
   qty 5 → `(38 − 40.00) × 100 × 5 = −$1,000` (NOT −$1,000 + this short's credit; that credit is already in
   the 40.00 basis). Print: "Assignment here realizes a net loss of $<loss_if_assigned> — this is a managed
   exit, not cost-basis repair." Require explicit acknowledgment before emitting.
3. REBOUND/WHIPSAW MODEL (the `leaps` §10-G analogue): re-price the SHORT call via Black-Scholes at
   the chosen DTE across underlying scenarios — flat, +10%, +20%, and a V-recovery THROUGH the
   strike — IV held at the calibrated level. Per scenario report: short value then, $ to buy-to-close,
   and outcome if assigned (called away at strike vs. missed upside). Frame the asymmetry: writing
   caps the rebound you are hoping for.

   | Underlying @ horizon | move | short-call value | buy-to-close cost | if assigned (P&L vs adj. basis) |
   |---|---|---|---|---|

4. THESIS GATE: thesis_status is a HUMAN input. If broken -> recommend CLOSE the position; do NOT
   keep writing into a falling knife. State plainly that premium is a trickle against a structural
   decline (e.g. $X collected vs $Y drawdown).

### Sanity-check rationale (why this machinery exists)
Cost-basis repair via repeated CC writing is valid **only** for a down-but-basing / range-bound
stock the user still believes in. Its two failure modes — (a) a V-recovery ripping through a low
strike (called away below basis, missing the bounce), and (b) slow-bleeding while capping every
rebound on a broken name — are exactly what items 2–4 police.

---

## §9. Assignment & ex-div/earnings defense

- **COVERAGE:** verify `shares_held >= 100 × short_contracts` (never naked). Halt if not.
- **EX-DIV:** an ITM short call into ex-dividend is the classic early-assignment trigger — flag and
  suggest buy-to-close / roll up&out ahead of the ex-date. (Pull dividend/ex-div from price snapshot;
  if unavailable, flag the gap.)
- **EARNINGS:** flag writing through earnings; only acceptable if intent explicitly accepts the
  IV-crush / assignment risk (block by default within `avoid_write_days_before_earnings`).
- Covered calls are share-secured (no margin risk like PMCC short legs), so the concern is TIMING
  (ex-div/earnings), not maintenance margin.

---

## §10. Output report

**A. Action-board table** (portfolio scan):
| Symbol | Shares | Intent | Existing short (K/Exp/Δ) | Adj. basis | Premium-to-date | Action |
|---|---|---|---|---|---|---|

**B. Per-position block:**
```
TICKER  (N shares)  intent=income_keepers
  Underlying S 47.00 | adjusted basis 38.20 | premium to date $1,240 across 4 sell-to-open orders (since 2025-11-03)
  WRITE: 50 C 2026-08-15 (35 DTE)  premium 1.10  delta 0.18  | covers 1 contract (100 sh)
    return-if-flat  ≈ 24.4%/yr   | return-if-called ≈ 90.9%/yr   | downside cushion 2.3% | upside cap 6.4%
    breakeven (above which holding beat writing): 51.10  (strike + credit)
    flags: none (ex-div/earnings clear)
  -> SELL-TO-OPEN (PENDING APPROVAL)
```
For repair_failing add the vs-adjusted-basis return, the MANAGED-EXIT flag (if any), and the §8 rebound table.

**C. Proposed tickets — PENDING APPROVAL** (numbered): copy-paste IBKR option tickets (legs, conId,
strike/expiry/right, qty, LMT, mid-or-better, TIF=DAY, "enter as ONE combo"); equity/ETF via connector
only after explicit approval. State: "Nothing is placed until you approve a specific order by number."

**D. Flags & data gaps:** missing greeks/IV (EST + echoed r/q/IV), stale/crossed quotes, ledger
discrepancies, positions awaiting intent input.

---

## §11. Workflow harness (full-portfolio review)
For a portfolio review (no single ticker), SCOUT INLINE first: get_account_positions ->
share lots with >=100 shares (**skip any symbol in `exclude_symbols`**, matching §5), pair each with any
existing short call, load each ticker's intent from the ledger (ask if missing), and resolve
`statements_path` (§4; ASK if unset). Then invoke the Workflow tool with
`scriptPath: skills/covered-call/portfolio-scan.workflow.js` and `args:{account_id, lots, statements_path}`.
(`scriptPath` resolves from the plugin root — `plugins/market-wizard/` — so this path is correct as written.)
The fan-out is READ-ONLY: agents analyze and return structured data; NO orders are placed inside
the workflow. After synthesis, present the action board; the user approves a specific action and
THEN the skill emits that ticket inline (§12). Single-ticker requests skip the workflow entirely.

---

## §12. ORDER / TICKET EMISSION (only after explicit per-order approval)

1. Re-pull fresh position + quote snapshots **immediately before pricing** (≤ `data_staleness_max_min`;
   a quote fresh enough to analyze is not necessarily fresh enough to price — re-pull now).
2. **Verify contract** via `search_contracts` / the position description: confirm `conId`, `right=C`,
   exact `strike`, exact `expiry`, `multiplier=100`. **Abort on mismatch** and report.
3. **Options (sell-to-open, buy-to-close, roll) — the connector CANNOT place these.** Emit a
   **copy-paste IBKR ticket**: each leg's action (SELL/BUY, to-OPEN/CLOSE), readable symbol + `conId`,
   strike/expiry/right, quantity; `orderType=LMT`; net debit/credit limit (mid-or-better); `tif=DAY`;
   and the entry note ("enter as ONE combo; do not leg in"). Approval here = "I'll enter this in IBKR
   myself."
4. **Equity result only (selling shares on a deliberate exit):** `create_order_instruction` with conId,
   action=SELL, quantity, `orderType=LMT`, `lmtPrice` (mid-or-better), `tif=DAY`. **Never** market.
   Report the **instruction ID**; tell the user to review/transmit in IBKR.
5. Don't claim a fill; confirm only via `get_account_orders` / `get_account_positions`.

---

## §13. Guardrails — NEVER
- Never write without verifying shares_held >= 100 × contracts (no naked calls).
- Never suggest a strike below adjusted_basis without the MANAGED-EXIT flag + explicit acknowledgment.
- Never write ITM through ex-dividend without flagging early-assignment risk.
- Never write through earnings unless the position's intent explicitly accepts it.
- Never place/modify/cancel an order without explicit per-order approval here.
- Never use market orders — LIMIT only, mid-or-better.
- Never act on stale/crossed/missing data — flag.
- Never infer thesis or intent — both are human inputs.
- Never place option orders via the connector (equity/ETF only) — options are manual tickets.
- Halt and report if data won't load, coverage fails, or anything is ambiguous.

### First-run calibration (once)
1. Resolve account_id (ASK if not in CLAUDE.md/memory).
2. List held share lots >=100 shares; pair existing short calls; confirm which are covered calls
   (vs leaps/PMCC, which this skill ignores).
3. Probe get_price_snapshot on one option for greeks/IV availability; set the BS fallback path.
4. Collect intent per position; create/reconcile Covered Calls/memory.md.
5. Confirm CONFIG defaults fit risk tolerance (delta bands, profit_take_pct, DTE window).

---

*Encodes the user's chosen rules and enforces human approval on every order. An analysis and
order-preparation aid — not financial advice, not an autonomous trader. Markets, fills, and
outcomes are the user's responsibility.*
