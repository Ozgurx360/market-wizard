---
name: leaps
description: >
  Full-lifecycle LEAPS strategy for the user's Interactive Brokers account: evaluates NEW
  entries, and reviews EXISTING long-call LEAPS to HOLD / ROLL-OUT / ROLL-UP / ROLL-DOWN /
  TRIM / CLOSE — single calls AND call debit spreads (verticals) — always showing intrinsic
  vs extrinsic value and the relevant Greeks.
  Trigger on: "review my LEAPS", "LEAPS health check", "should I roll a ticker", "should I
  open/buy a LEAPS on a ticker", "is this a good LEAPS entry", "manage my long calls",
  "what should I do with my options", "trim/close a position", "build a debit/call spread on
  a ticker", "manage my spread", or any question about entering, holding, rolling, trimming, or
  closing a long-dated call or call vertical. Read-only by default; ALL order
  placement requires explicit per-order human approval (see OPERATING MODE).
---

# LEAPS — Full-Lifecycle Operating Skill

Turns the *LEAPS Decision Mechanism* into a deterministic, IBKR-wired procedure covering the
**whole lifecycle — ENTRY, HOLD, ROLL, TRIM, CLOSE** for both **single long calls** and
**call debit spreads (verticals)**. It screens candidates, classifies existing positions,
always surfaces **intrinsic vs extrinsic value** and the Greeks, and
prepares exact limit orders **for the user to approve**. Decision aid only — not an
autotrader, not financial advice.

<!-- CHANGELOG
 2026-05-29 (v2.1): added (a) TIME-AWARE STOP — §6 rule 2 now yields CLOSE-CANDIDATE (not a reflex CLOSE)
   for far-dated, slow-bleeding LEAPS; (b) §10-G COST-OF-WAITING forward-decay table; (c) CONVICTION-FIRST
   ordering on impaired/stopped positions (§0.3, §4.4, §12): present math -> ask conviction -> conclude.
   Prior v2 already carried: IV-percentile IV-rank (§1/§2/§5/§9), breakeven-unreachable rule 7b,
   manual copy-paste option tickets (§0/§7/§11), trigger-levels-as-underlying-price (§2/§10-B),
   greeks standardization, memory-reconcile (§4.0/§13), quick-path router (§3.0).
 2026-05-30 (v2.1.1): corrected §10-G IV-rank direction — IV-down stress belongs at HIGH iv_rank
   (room to revert down); at LOW iv_rank show an IV-up case instead (normalization helps a long holder).
-->

---

## 0. OPERATING MODE — NON-NEGOTIABLE (recommend-only)

1. **Autonomous scope is READ-ONLY.** Without explicit, per-order approval *in the
   conversation*, call ONLY: `get_account_positions`, `get_account_balances`,
   `get_account_summary`, `get_account_orders`, `get_account_trades`,
   `get_order_instructions`, `get_price_snapshot`, `get_price_history`, `search_contracts`.
2. **`create_order_instruction` is EQUITY/ETF ONLY — it cannot place option orders.** Every option
   action (single leg, roll, spread, PMCC) is therefore a **copy-paste ticket the user enters manually
   in IBKR** (see §7/§11), never a connector order. Even for an equity/ETF result, NEVER call
   `create_order_instruction` / `delete_order_instruction` until the user approves that specific order by
   reference (e.g. "place order #2"); then report its ID and tell the user to review/transmit it in IBKR.
   Confirm fills only by re-reading orders/positions.
3. **Never assess fundamentals.** "Thesis bullish / intact / broken" is a **human input** —
   ask for it; never infer it from price. On an **impaired/stopped** position (rule 2 CLOSE-CANDIDATE or
   7b breakeven-unreachable), the order is fixed: **present economics + §10-G cost-of-waiting FIRST, then
   ASK CONVICTION, THEN conclude** — never lead with a CLOSE verdict before the user has weighed in.
4. When anything is ambiguous, missing, or stale — **stop and ask.** Flag, don't guess.

Loop: *analyze → present report + proposed orders/tickets → user approves a specific one →
re-pull fresh quotes → emit the copy-paste IBKR combo ticket (options) or construct the LIMIT
`create_order_instruction` (equity/ETF) → report the ticket / instruction ID.*

---

## 1. CONFIG (edit to tune behaviour)

```yaml
account_id: ""                      # the user's IBKR account — resolve from their CLAUDE.md/memory; if none is set there, ASK the user before any account call (never guess)

# --- scope ---
scope_right: "C"                    # long calls
scope_min_dte_to_be_leaps: 270
exclude_symbols: []
short_legs_are_pmcc: true

# --- delta / moneyness ---
delta_target_min: 0.70
delta_target_max: 0.85
delta_sweet_spot: 0.80
deep_itm_delta: 0.75
delta_rollout_trigger: 0.60
delta_rollup_trigger: 0.90

# --- time / roll windows (days) ---
dte_roll_window_low: 90
dte_roll_window_high: 120
dte_early_roll_if_drifted: 180
dte_hard_floor: 45
dte_watch_lead: 30
new_leg_dte_min: 540
new_leg_dte_max: 730

# --- P&L thresholds (on premium) ---
stop_loss_pct: -50
trim_1_gain_pct: 50
trim_2_gain_pct: 100
rollup_gain_trigger_pct: 50
stop_urgency_is_time_aware: true    # a -50% stop on a FAR-DATED, SLOW-bleeding LEAP is a CLOSE-CANDIDATE,
                                    # not a reflex CLOSE: show §10-G cost-of-waiting + ask conviction (§6 rule 2)
stop_urgent_dte_max: 180            # at/under this DTE a breached stop IS urgent (decay/pin biting); above = slow-bleed

# --- breakeven-reachability escalation (don't sit passive on deep-underwater names) ---
breakeven_required_move_max_pct: 25     # flag if breakeven needs > this % move above spot
flag_breakeven_above_52w_high: true     # also flag if breakeven > underlying's 52-wk high

# --- cost / risk screens ---
leverage_cost_max_pct_yr: 15        # extrinsic / strike / years
iv_rank_entry_max: 50               # IV rank = implied-volatility-percentile.high_52w ×100 (see §2); prefer entries below
max_bidask_spread_pct: 10
data_staleness_max_min: 3           # derivatives: a 2yr option combo priced off a stale quote gets
                                    # picked off or hangs dead. 3 min ceiling; re-pull right before any combo.

# --- greeks / Black-Scholes assumptions (pin these so two runs never disagree) ---
risk_free_rate_pct: 3.7             # ~3-mo T-bill, May 2026 (set/refresh as needed; 2nd-order for LEAPS, see §2 rho)
bs_dividend_yield_source: "get_price_snapshot dividend-yield.yield_pct"   # q per name (GLD/SLV=0; dividend stocks >0)
bs_iv_source_option: "implied-vol.annual_iv (fallback option-midpoint-iv.annualIv)"
bs_iv_source_underlying: "implied-vol-underlying.annual_iv"

# --- ENTRY: asset-class playbook (delta target, size cap, preferred structure) ---
asset_classes:
  etf:         { delta_target: 0.80, max_notional_pct: 30, structure: "single_call" }
  blue_chip:   { delta_target: 0.80, max_notional_pct: 20, structure: "single_call" }
  growth:      { delta_target: 0.70, max_notional_pct: 10, structure: "single_call (IV-pullback only)" }
  speculative: { delta_target: 0.55, max_notional_pct: 3,  structure: "debit_spread" }
known_etfs: ["SPY","QQQ","IWM","DIA","SCHD","VTI","XLK","XLF","XLE","XLV"]
avoid_entry_days_before_earnings: 7

# --- DEBIT SPREADS (call verticals; entry construction + management) ---
spread_long_leg_delta: 0.70            # long (lower-strike) leg target delta — the directional leg
spread_short_leg_delta: 0.30           # short (higher-strike) leg target delta — caps cost & vega
spread_min_width_pct_of_S: 8           # min (K2−K1)/S; ensures room to profit
spread_max_debit_pct_of_width: 60      # reject if net_debit/width exceeds this (poor risk:reward)
spread_profit_take_pct: 60             # long-dated verticals CAN'T reach ~70% of width early: a stock
                                       # pushing the short strike ATM inflates the short leg's extrinsic,
                                       # which barely decays with 500+ DTE -> spread mark pins ~50-60% of
                                       # width for months. 60% = strong capital velocity; don't wait for max.
spread_stop_loss_pct: -50              # close (or leg-reduce, see §6-SPREADS) if spread value down this %
spread_close_dte: 45                   # close/roll a spread by this DTE (pin/assignment risk)
spread_no_roll_down: true              # NEVER roll a vertical DOWN: it pays a NEW net debit at lower
                                       # strikes = doubles defined max loss on a failing thesis. Forbidden.
# Disambiguate a long+short call on the SAME underlying:
#   short_strike > long_strike AND |short_DTE − long_DTE| ≤ 60  -> DEBIT SPREAD (manage as ONE unit, §6-SPREADS)
#   short much shorter-dated (e.g. short ≤90 DTE vs long ≥365)  -> PMCC income leg (§7)

# --- PMCC short-leg discipline (esp. when the long LEAPS are underwater) ---
pmcc_short_dte_min: 30
pmcc_short_dte_max: 45
pmcc_short_delta_min: 0.20
pmcc_short_delta_max: 0.30
pmcc_short_profit_take_pct: 50          # buy-to-close the short near ~50% of credit
pmcc_keep_uncapped_longs: 1             # always leave >= this many long contracts NOT covered by a short
pmcc_max_shorts: "longs - pmcc_keep_uncapped_longs"   # never stack shorts beyond this
pmcc_short_strike_min_rule: "above all long strikes; when long underwater, also >= long breakeven"

# --- execution ---
order_type: "LMT"                   # LIMIT ONLY — market orders forbidden
limit_price_rule: "mid_or_better"
tif: "DAY"
multileg_requires_native_combo: true  # options are MANUAL in IBKR (connector places equity/ETF only):
                                      # emit ONE copy-paste combo ticket w/ a net limit. Guidance to the user:
                                      # enter as a single combo, never leg into added exposure; if your platform
                                      # can't combo it, only a risk-reducing CLOSE may go short-leg-first.
```

---

## 2. DATA SOURCES & FIELD MAPPING

| Need | Source | Field / how |
|---|---|---|
| Open positions | `get_account_positions` | symbol, secType, right, strike, expiry, position(qty), avgCost, mark |
| Equity / buying power | `get_account_summary`, `get_account_balances` | NetLiquidation, AvailableFunds, BuyingPower |
| Underlying price `S` | `get_price_snapshot` (underlying) | last/mark |
| Option mark/bid/ask | `get_price_snapshot` (option) | bid, ask, mark |
| Option **delta, IV, greeks** | `get_price_snapshot` (option) | greeks/modelGreeks if present — see DATA GAPS |
| **IV rank (name's own)** | `get_price_snapshot` (underlying) | `implied-volatility-percentile` → `high_52w` (primary), `high_26w`/`high_13w` (context); fraction ×100 = percentile. Underlying-level, not per-option |
| Absolute IV / realized vol | `get_price_snapshot` | underlying `implied-vol-underlying.annual_iv`; option `implied-vol.annual_iv` or `option-midpoint-iv.annualIv`; 30d realized `historical-vol.annual_pct` (fractions) |
| 52-wk high/low, dividend `q` | `get_price_snapshot` (underlying) | `misc-statistics.high_52w`/`low_52w`; `dividend-yield.yield_pct` |
| Candidate contracts | `search_contracts` → `get_price_snapshot` | enumerate expiries/strikes; pick nearest target delta |
| Working orders | `get_account_orders`, `get_order_instructions` | avoid duplicate/conflicting orders |

**Computed fields (per share unless noted) — ALWAYS show intrinsic & extrinsic:**
- `DTE = expiry − today`
- `intrinsic = max(0, S − strike)`
- `extrinsic = option_mark − intrinsic`
- `extrinsic_pct_yr = extrinsic / strike / (DTE/365) × 100`  ← leverage cost
- `moneyness = S / strike`
- `breakeven = strike + avgCost` (premium paid)
- `breakeven_required_move_pct = (breakeven − S) / S × 100`  ← how far the stock must travel to break even
- `breakeven_above_52w_high = breakeven > misc-statistics.high_52w`  ← breakeven beyond the prior 52-wk high
- `pnl_pct = (mark − avgCost) / avgCost × 100`
- `mid = (bid+ask)/2` ; `spread_pct = (ask−bid)/mid × 100`
- `theta_per_day = theta/365` ; expose `delta, gamma, vega, IV` when greeks present
- Position dollars = per-share × 100 × |qty|
- **Trigger levels as underlying prices** (so the user can set price alerts): for each premium trigger
  (`stop_loss_pct`, `trim_*`, delta-roll), solve the underlying `S*` that hits it — preferred via
  Black-Scholes re-price at `S*`; fallback (label **EST**) delta-linear `S* ≈ S + (target_mark − mark)/delta`.
  E.g. the −50% stop → `S*` where option mark ≈ 0.5 × avgCost.

### DATA GAPS — handle gracefully, never fake
- **Delta/greeks missing:** say so. Estimate via Black-Scholes from **standardized inputs** (CONFIG):
  `r = risk_free_rate_pct`, `q = dividend-yield.yield_pct` (per name), IV = `implied-vol.annual_iv`
  (option) / `implied-vol-underlying.annual_iv` (underlying), plus (S,K,DTE); **label "EST"** and
  **echo the assumed r/q/IV** in output so two runs agree. If no greeks and no IV, mark **"delta
  unavailable — limited to price/DTE rules."**
- **IV rank IS available — use it.** `get_price_snapshot(underlying).implied-volatility-percentile.high_52w`
  is the name's own IV rank (a fraction; ×100 = percentile). Use `high_52w` as the primary
  `iv_rank_entry_max` screen, `high_26w`/`high_13w` for shorter-window context, and
  `implied-vol-underlying.annual_iv` for the absolute level. Only if the field is missing or returns
  `is_valid:false` fall back to: (a) current IV vs logged range; (b) absolute IV bands + VIX proxy.
  Never block silently.
- **Stale/crossed quotes** (older than `data_staleness_max_min`, or bid≥ask, or zero): treat
  as unavailable and flag.

---

## 3. MODES & INTENT DETECTION

### 3.0 QUICK-PATH ROUTER (run FIRST — don't make a simple review wade through entry/spread machinery)
Classify intent before doing anything else and load only the machinery that path needs:
- **Single plain long call** ("should I roll/trim/close TICKER", one position, no spread/entry): run the
  **lean path** — pull just that position + its underlying, compute §2 fields, run the §6 single-call
  engine, emit §10 (B, C, E). **Skip §5 (entry) and §6-SPREADS** entirely.
- **Spread detected** (long+short pair per §4): route to §6-SPREADS.
- **PMCC detected** (short much shorter-dated): add the §7 PMCC table.
- **Entry candidate named:** run §5.
- **Full review / unclear:** run the whole portfolio runbook (§4).

- **ENTRY mode** — user names a candidate to consider ("should I open a LEAPS on AAPL?",
  "is QQQ a good entry?"). Run §5.
- **REVIEW mode** — "review my LEAPS", "health check", or no specific ticker. Run §6 across the
  portfolio (single calls via §6; any **debit spreads** via §6-SPREADS).
- **SINGLE-POSITION mode** — "should I roll/trim/close <ticker>". Run §6 on that position only.

If intent is unclear, ask which the user wants. Entry and review can be combined in one run.

---

## 4. RUNBOOKS

**Review / single-position runbook**
0. **Load & reconcile memory.** Read `memory.md` + `CLAUDE.md` (conid↔ticker map, prior thesis notes, open
   TODOs). After pulling live data, **surface any contradiction** between memory, live positions, and
   statements — a conid that no longer matches, a closed position still listed, a field the notes call
   "unavailable" that the API now returns (e.g. positions now include strike/expiry/right) — instead of
   silently trusting one source; flag stale TODOs for deletion.
1. `get_account_summary` + `get_account_positions`.
2. Filter in-scope: option, `right=scope_right`, not excluded. **Pair long+short calls on the
   same underlying** (CONFIG rule): short strike > long strike & expiries within 60d → **DEBIT
   SPREAD** (route to §6-SPREADS, manage as a unit); short much shorter-dated → **PMCC** leg (§7).
3. Per long call: pull underlying + option snapshots; compute §2 fields (incl. intrinsic/extrinsic).
4. Collect **thesis status** per position (human). Required before any thesis-close or roll-down — and
   before CONCLUDING on any impaired/stopped position (rule 2 CLOSE-CANDIDATE / rule 7b): present
   economics + §10-G cost-of-waiting, ASK conviction, THEN land the verdict (math → ask → conclude).
5. Classify with §6 engine (priority order; record primary + secondary flags + WATCH).
6. Build report (§10): economics per position + proposed orders (PENDING APPROVAL) + flags.
   Run size/leverage/liquidity checks (§7/§9) on every proposed action.
7. **STOP.** Present; place nothing.
8. On a specific approval → §11.

**Entry runbook**
1. `get_account_summary` (equity/buying power).
2. Confirm **thesis** (bullish, multi-quarter+) and **asset class** (§5 / §8).
3. Underlying snapshot (S); regime/earnings gates (§9).
4. Select expiry + strike to hit class delta target (search + snapshots); compute economics.
5. Apply entry screens (§5). Size to notional (§5 step 7).
6. Output entry proposal: **GO / WAIT / PREFER-SPREAD / NO-GO** + contract + limit + economics
   + flags (PENDING APPROVAL). Place nothing.
7. On approval → §11.

---

## 5. ENTRY DECISION ENGINE (per candidate)

```
# 0. THESIS GATE (human)
IF thesis != "bullish_multiquarter": -> NO-GO (need a thesis; LEAPS aren't short-term)

# 1. ASSET CLASS -> params  (confirm class with user; known_etfs => etf)
class = classify(ticker); p = asset_classes[class]

# 2. TIMING / REGIME GATES (§9)
IF earnings within avoid_entry_days_before_earnings: -> WAIT (don't buy into earnings IV crush)
IF VIX elevated / IV high:
    IF class in (growth, speculative): -> PREFER debit_spread OR WAIT (vega trap)
    ELSE: note "cheaper stock but pricier option" caution

# 3. IV ENVIRONMENT
iv_rank = get_price_snapshot(underlying).implied-volatility-percentile.high_52w × 100   # name's own rank
IF iv_rank valid AND iv_rank > iv_rank_entry_max: -> downgrade to PREFER-SPREAD / WAIT (vega trap)
ELIF iv_rank invalid/missing: flag; fall back to absolute IV (implied-vol-underlying.annual_iv) / VIX proxy

# 4. EXPIRY: choose expiry in [new_leg_dte_min, new_leg_dte_max]

# 5. STRIKE / STRUCTURE
IF structure == "single_call":
    long_strike = strike whose delta ≈ p.delta_target          # the only leg (BUY)

IF structure == "debit_spread"  (speculative class, or any PREFER-SPREAD verdict):
    long_strike  = strike whose delta ≈ spread_long_leg_delta   # lower strike, BUY (directional leg)
    short_strike = strike whose delta ≈ spread_short_leg_delta  # higher strike, SELL (caps cost/vega)
    both legs SAME expiry in [new_leg_dte_min, new_leg_dte_max]
    width      = short_strike − long_strike
    net_debit  = mid(long) − mid(short)        # = MAX LOSS
    max_profit = width − net_debit             # realized if S ≥ short_strike at expiry
    breakeven  = long_strike + net_debit
    net_delta  = delta(long) − delta(short)    # the spread's directional exposure
    net_theta  = theta(long) − theta(short)    # less negative than a single call (short helps)
    net_vega   = vega(long)  − vega(short)     # near-zero / small → the point of the spread

# 6. SCREENS
IF structure == "single_call":
    compute intrinsic, extrinsic, extrinsic_pct_yr
    IF extrinsic_pct_yr > leverage_cost_max_pct_yr: -> flag/reject (overpaying for leverage)
IF structure == "debit_spread":
    IF width / S < spread_min_width_pct_of_S/100: -> too narrow (little profit room); widen
    IF net_debit / width > spread_max_debit_pct_of_width/100: -> poor risk:reward; reject/flag
IF spread_pct(either leg) > max_bidask_spread_pct: -> flag illiquid; propose patient limit

# 7. SIZE (risk-budget the MAX LOSS, not premium)
single_call:  contracts = floor( (p.max_notional_pct% * equity) / (100 * S) )         # share-equiv notional
debit_spread: contracts = floor( (p.max_notional_pct% * equity) / (100 * net_debit) ) # net_debit = max loss
IF contracts < 1: -> too large for size cap; flag (narrow the spread or size down)

# 8. OUTPUT: GO / WAIT / PREFER-SPREAD / NO-GO
#    single_call : contract, entry LIMIT, delta, intrinsic+extrinsic split, extrinsic_pct_yr
#    debit_spread: both legs, NET-DEBIT limit, width, net_debit (max loss), max_profit, breakeven,
#                  net delta/theta/vega
#    + contracts & resulting risk, regime/earnings/IV flags.   PENDING APPROVAL.
```

---

## 6. CLASSIFICATION RULE ENGINE — existing positions (evaluate top-down; first match = primary)

> Thresholds from CONFIG. `thesis_*`, `support_break`, `drawdown_is_market_wide` are human flags.

```
# 1. THESIS CLOSE (overrides all)
IF thesis_status == "broken": -> CLOSE (exit regardless of P&L)

# 2. HARD STOP (urgency scales with BURN, not just drawdown — stop_urgency_is_time_aware)
IF pnl_pct <= stop_loss_pct OR support_break:
    IF support_break OR DTE <= stop_urgent_dte_max OR extrinsic_pct_yr >= leverage_cost_max_pct_yr:
        -> CLOSE (URGENT)                         # support gone, near expiry, or bleeding >= ceiling/yr: cut now
    ELSE:
        -> CLOSE-CANDIDATE / DE-RISK (NOT urgent) # far-dated & slow-bleeding (e.g. -50% w/ 600 DTE, burn < ceiling).
            # A forward decision, not a reflex sell. BEFORE concluding: (a) render §10-G cost-of-waiting,
            # (b) run 7b breakeven check, (c) ASK CONVICTION; THEN offer: close now | hold-on-a-leash w/ a
            # price stop | re-express. Stop still BINDS (-> CLOSE) if thesis is broken/absent or no bull case.

# 3. EXPIRY-CLIFF PROTECTION
IF DTE <= dte_hard_floor:
    IF delta >= deep_itm_delta: -> ROLL-OUT (URGENT)        # deep-ITM winner: roll, don't expire
    ELSE: -> CLOSE (URGENT, SELL-TO-CLOSE)                  # near/at-money into cliff: exit
    # NEVER hold meaningful extrinsic inside the floor; NEVER auto-exercise.

# 4. ROLL UP (harvest big winner / restore leverage)
IF delta >= delta_rollup_trigger AND pnl_pct >= rollup_gain_trigger_pct:
    -> ROLL-UP (offer TRIM as alternative)

# 5. TRIM
IF pnl_pct >= trim_2_gain_pct: -> TRIM (larger)
ELIF pnl_pct >= trim_1_gain_pct: -> TRIM (partial)

# 6. TIME-DEFENSE ROLL OUT
IF delta >= deep_itm_delta AND DTE <= dte_roll_window_high: -> ROLL-OUT
IF delta <  deep_itm_delta AND DTE <= dte_early_roll_if_drifted: -> ROLL-OUT (EARLY)  # drifted ATM

# 7. ROLL DOWN (cautious; intact-thesis loser only)
IF delta < delta_rollout_trigger AND pnl_pct < 0
   AND thesis_status == "intact" AND drawdown_is_market_wide:
    -> ROLL-DOWN (flag: adds capital to a loser)
# Guard: NEVER roll down unless thesis_status == "intact".

# 7b. BREAKEVEN UNREACHABLE -> THESIS-CHECK (don't sit passive; does NOT force a close)
IF pnl_pct < 0 AND (breakeven_above_52w_high OR breakeven_required_move_pct > breakeven_required_move_max_pct):
    -> THESIS-CHECK (escalate: "breakeven needs +X% / sits above the 52-wk high — is the thesis still alive?")
    # Preempts a passive HOLD/WATCH so we don't sit silent until the -50% stop. Thesis stays HUMAN:
    # prompt for it, never auto-close. Triggers 1-7 (stop/roll/thesis-close) still win if they also match.
    # ALSO render §10-G cost-of-waiting (what holding costs vs closing) and ask conviction before concluding.

# 8. WATCH (approaching a trigger)
IF DTE <= (relevant_roll_window + dte_watch_lead)
   OR delta within 0.05 of a trigger
   OR pnl_pct within 10pts of a stop/trim level: -> WATCH

# 9. HOLD (healthy)
ELSE: -> HOLD
```

**Cross-cutting checks on every ROLL/NEW proposal:** leverage cost ≤ `leverage_cost_max_pct_yr`;
resulting notional in the name ≤ `max_notional_pct`; spread ≤ `max_bidask_spread_pct` (else
patient limit, mark illiquid); buying power covers any net debit — else flag.

### §6-SPREADS — CLASSIFICATION for existing DEBIT SPREADS (manage as ONE unit)

Apply to any long+short call flagged a debit spread in §4. **Do not run the single-call engine on
its legs** — manage the spread on its own metrics:
```
spread_value   = mid(long) − mid(short)              # current value of the vertical
net_debit_paid = long_avgCost − short_avgCredit      # original cost = max loss
width          = short_strike − long_strike
pct_of_max     = spread_value / width × 100          # how much of max value (K2−K1) is captured
pnl_pct        = (spread_value − net_debit_paid) / net_debit_paid × 100
net_delta      = delta(long) − delta(short)
DTE            = nearer leg's DTE
```
Evaluate top-down (first match = primary):
```
# 1. THESIS CLOSE
IF thesis_status == "broken": -> CLOSE SPREAD (regardless of P&L)
# 2. STOP  (close the whole spread by default; ONE risk-reducing alternative allowed)
IF pnl_pct <= spread_stop_loss_pct:
    -> CLOSE SPREAD (stop)
    # Allowed alternative ONLY if thesis_status == "intact" AND DTE > spread_close_dte:
    #   BUY-TO-CLOSE the short leg, KEEP the long  -> this REDUCES risk (no new debit) and
    #   converts to a single call now governed by §6. NEVER the reverse, never a new debit here.
# 3. EXPIRY / PIN RISK
IF DTE <= spread_close_dte: -> CLOSE or ROLL-OUT the spread   # avoid pin/assignment between strikes
# 4. PROFIT TAKE  (a long-dated vertical pins ~50-60% of width for months; do NOT wait for max)
IF pct_of_max >= spread_profit_take_pct: -> CLOSE SPREAD (harvest)
# 4b. EARLY UNCAP  (stock cleared the short strike with time left AND short-leg vol is rich)
IF S >= short_strike AND IV(short_leg) elevated AND thesis bullish AND DTE > spread_close_dte:
    -> BUY-TO-CLOSE short leg only (removes the extrinsic drag / cap) -> long now governed by §6. Flag it.
# 5. ROLL UP  (near-max winner, want fresh upside room)
IF S >> short_strike AND pct_of_max >= spread_profit_take_pct AND thesis bullish: -> ROLL-UP spread
# 6. (REMOVED) ROLL-DOWN is FORBIDDEN on verticals (spread_no_roll_down):
#    rolling down pays a NEW net debit at lower strikes = DOUBLES defined max loss on a failing
#    thesis. A losing vertical is closed at the stop (rule 2), never averaged down.
# 7. WATCH / HOLD
IF within dte_watch_lead of spread_close_dte OR pct_of_max within 10pts of take: -> WATCH
ELSE: -> HOLD
```

---

## 7. ROLL & TRIM CONSTRUCTION

A roll is **two legs**: SELL-TO-CLOSE current long, BUY-TO-OPEN replacement — so it carries the same
partial-fill risk as a spread roll. **The connector cannot place option orders; the deliverable is a
copy-paste IBKR combo ticket** (legs, ratio, net debit/credit `LMT`, TIF, entry order) the user routes as
ONE combo. Tell the user explicitly: **enter as a single combo, do not leg in** — a filled close with an
unfilled re-open leaves you flat/uncovered and chasing the new leg through a moved market. (A plain TRIM
or a full CLOSE is single-leg and routes as a simple ticket.)

- **ROLL-OUT:** new expiry `new_leg_dte_min..max`; strike with delta ≈ `delta_sweet_spot`.
  Report **net debit**, new delta, new `extrinsic_pct_yr`, new intrinsic/extrinsic.
- **ROLL-UP:** higher strike, same/longer expiry, delta back to band; should free capital
  (net credit / smaller cost). Report cash freed + new delta.
- **ROLL-DOWN:** lower strike to restore delta; **net debit that raises risk** — state added
  capital + new notional; require approval with that flagged.
- **TRIM:** SELL-TO-CLOSE part (sensible contract count); report realized P&L + remaining
  delta/notional.

**PMCC short legs** (if `short_legs_are_pmcc`): separate, faster cadence — short `pmcc_short_dte_min..max`
DTE, `pmcc_short_delta_min..max` delta; buy-to-close near `pmcc_short_profit_take_pct` or roll up-and-out
if tested; never let a short strike sit below the long strike or span earnings/ex-div without flagging.
**Underwater-LEAPS rules:** sell shorts only at strikes **above all long strikes** and **≥ the long's
breakeven**; keep **≥ `pmcc_keep_uncapped_longs`** long contract(s) uncovered (upside not fully sold);
never stack more than `pmcc_max_shorts` short contracts. Always render the **PMCC table (§10-F)**, and for
any roll a **roll comparison table** (current vs candidate: strike, DTE, delta, credit, % profit, distance
to long strike, earnings/ex-div). Report separately.

**Debit-spread rolls/closes (a vertical is 2 legs; rolling it touches up to 4).** Multi-leg actions
must go as a **native combo order with a single NET limit.** Sequential legging is NOT a fallback for
anything that adds exposure — a partial fill mid-sequence leaves a **naked, unhedged delta** that the
next leg may have to chase through a spiked market (the exact slippage the skill exists to prevent).
(Reminder: this connector places equity/ETF only, so every option leg is **manual in IBKR** — these
specs tell the user what combo to enter and when to abort.)

**Combo-entry rule (principle: never leg into ADDED exposure) — print these instructions on the ticket:**
- **ROLL-OUT / ROLL-UP / any spread OPEN:** the ticket MUST be entered as ONE native combo in IBKR. Tell
  the user: if IBKR can't build the combo, **do not enter leg 1** — a half-done roll is worse than no roll.
  (There is no connector leg to "halt"; this is a do-not-leg-in instruction to the user.)
- **CLOSE (flattening an existing, already-hedged pair):** prefer one combo; if IBKR can't combo it, the
  *only* safe manual sequence is **BUY-TO-CLOSE the short leg FIRST** (this *reduces* risk — kills
  assignment/margin exposure, can never create new naked-short delta), **then** SELL-TO-CLOSE the long.
  Never the reverse. A deliberate risk-reducing close, not "walking the legs."

Specs (each delivered as a copy-paste IBKR combo ticket):
- **CLOSE:** SELL-TO-CLOSE long + BUY-TO-CLOSE short as one combo at a **net-credit** limit
  (≈ current spread mid). Report realized P&L and % of max captured. (If IBKR can't combo → short-first close, above.)
- **ROLL-OUT:** close the spread, reopen the same-delta vertical in `new_leg_dte` range. Report new
  width, net_debit (max loss), max_profit, breakeven. **If IBKR can't combo → tell the user not to leg in.**
- **ROLL-UP:** close the (near-max) spread, open a higher vertical — harvests and resets upside room.
  **If IBKR can't combo → tell the user not to leg in.**
- **ROLL-DOWN:** **forbidden on verticals** (`spread_no_roll_down`) — it pays a new net debit at lower
  strikes and doubles the defined max loss on a failing thesis. Close at the stop instead (§6-SPREADS).

---

## 8. ASSET-CLASS PLAYBOOK (drives ENTRY; reference for review)

| Class | Examples | Delta target | Size cap | Structure / notes |
|---|---|---|---|---|
| **ETF** | SPY, QQQ, IWM, sector ETFs | 0.80 | 30% | Workhorse; deep-ITM single call + optional PMCC |
| **Blue chip** | AAPL, MSFT, JNJ, KO | 0.80 | 20% | "Set & maintain" deep-ITM + PMCC |
| **Growth** | TSLA, semis/AI, high-multiple tech | 0.70 | 10% | **Enter only on IV pullback**; avoid pre-earnings; tighter discipline |
| **Speculative** | small/story names | ~0.55 / ATM | 3% | **Debit spread** to cap cost & vega; accept 100% loss |

---

## 9. MARKET-REGIME OVERLAY (gates & flags)

| Signal | Source | Effect |
|---|---|---|
| VIX low (<~16–18) | `get_price_snapshot` VIX | Constructive to enter/roll |
| VIX high/spiking (>~25–30) | VIX | Prefer shares/spreads; growth/spec → WAIT or spread |
| Name's own IV rank | `get_price_snapshot` `implied-volatility-percentile.high_52w` ×100 | >`iv_rank_entry_max` → vega-rich: prefer spread / WAIT (esp. growth/spec); <30 → cheap vol, constructive to buy/roll |
| Earnings within N days | earnings date (if available) | **Block new entries** (`avoid_entry_days_before_earnings`); flag PMCC gap risk |
| Ex-dividend near | dividend data (if available) | Flag early-assignment risk on PMCC shorts; factor into strike/timing |
| Rates context | user/macro note | Judge by **equity/IV impact, not rho** (rho is second-order); easing-into-strength = constructive via delta |

If VIX/earnings/dividend data isn't retrievable, flag the gap rather than assuming a benign regime.

---

## 10. OUTPUT REPORT FORMAT (always shows intrinsic & extrinsic)

**A. Portfolio summary table** (scan view):

| Symbol | Contract (K/Exp/R) | Qty | DTE | S | Moneyness | Delta | **Intrinsic** | **Extrinsic** | Extr%/yr | P&L% | Class |
|---|---|---|---|---|---|---|---|---|---|---|---|

**B. Per-position economics** (detail block per position — surfaces the value split):
```
XYZ   800 C  2027-12-17   (x2)
  Underlying 950.00 | moneyness 1.19 | DTE 540 | IV 45% (EST if no live greeks)
  Mark 210.00  =  Intrinsic 150.00  +  Extrinsic 60.00
  Extrinsic cost 7.4%/yr | Delta 0.82 | Gamma 0.001 | Theta -0.18/day | Vega 1.1
  Basis 180.00 | P&L +30.00 (+16.7%) = +$6,000 total | Breakeven 990.00
  Trigger levels (underlying): -50% stop ≈ S* 860 (EST) | +50% trim ≈ S* 1015 | roll@delta0.60 ≈ S* 815
  -> HOLD  (delta in band; DTE clear of roll window)   [secondary: none]
```

**B2. Debit-spread economics** (per spread held — managed as one unit):
```
XYZ   900/1100 C  2027-01-15   (x1 vertical)
  Underlying 1000.00 | width 200 | DTE 230
  Spread value 120.00 ($12,000)  |  net debit paid 80.00 ($8,000)  |  P&L +50%
  % of max captured 60%  (max value = width 200) | max profit 120 | max loss 80 | breakeven 980
  net delta 0.34 | net theta -0.01/day | net vega 0.3
  -> CLOSE SPREAD  (harvest: pct_of_max 60% >= 60% take)
```

**C. Proposed orders / copy-paste IBKR tickets — PENDING YOUR APPROVAL** (numbered): legs, exact
contracts (symbol + conId + strike/expiry/right), `order_type=LMT`, limit (mid-or-better; net
debit/credit on combos), resulting delta & notional, new intrinsic/extrinsic, and the
size/leverage/liquidity check result. Option actions are **manual IBKR combo tickets** (connector
places equity/ETF only) — enter as ONE combo. State: *"Nothing is placed until you approve a specific
order by number; option orders you enter yourself in IBKR."*

**D. Entry proposals** (if ENTRY mode): GO/WAIT/PREFER-SPREAD/NO-GO with the same economics.

**E. Flags & data gaps:** missing delta/IV, EST values, illiquid spreads, stale quotes,
buying-power limits, and **positions awaiting your thesis input.**

**F. PMCC short legs** (MANDATORY if any short legs exist): table with columns — Short contract (K/Exp),
Qty, DTE, Delta, Credit, %profit, Dist-to-long-strike, Earnings/Ex-div flag, Uncapped-longs remaining,
Action. Plus a **roll comparison table** for any proposed short-leg roll (current vs candidate). Confirm
the underwater rules hold: shorts above long strikes / ≥ breakeven, `pmcc_keep_uncapped_longs` respected,
shorts ≤ `pmcc_max_shorts`.

**G. Cost-of-waiting** (MANDATORY for any CLOSE-CANDIDATE, breakeven-unreachable, or stopped position —
the verdict says *what* to do; this says *what holding costs*, the question a real holder asks): pick a
decision horizon (the user's; else next quarter-end / earnings / `dte_hard_floor`) and **re-price the option
at that date via Black-Scholes** across underlying scenarios — flat, ±10/20/25%, and key levels (range low,
mark-breakeven `strike+mark`, 52-wk high) — IV held at the calibrated level, plus an adverse IV-down case (most material when iv_rank is HIGH —
more room to revert down); when iv_rank is low, show an IV-up case instead, since normalization helps a
long holder. Per scenario report: option value then, $ change vs now, carry cost. Always state the
**flat-case $/day**, and frame the asymmetry — *bleeds if flat/down, profits only if the underlying moves
> X%* — so the user weighs optionality against carry. Restate the cut/reassess levels as **underlying
prices** (§2) for a hold-on-a-leash plan.

| Underlying @ horizon | move | option value | Δ vs now | carry cost |
|---|---|---|---|---|

Report dollars in both per-contract and total terms.

---

## 11. ORDER PLACEMENT / TICKET EMISSION (only after explicit per-order approval)

1. Re-pull fresh position + quote snapshots **immediately before pricing** (≤ `data_staleness_max_min`;
   a quote fresh enough to analyze is not necessarily fresh enough to price a combo — re-pull now).
2. **Verify contract** via `search_contracts` / the position description: confirm `conId`, `right=C`, exact
   `strike`, exact `expiry`, `multiplier=100`. **Abort on mismatch** and report.
3. **Options (any leg, single or multi) — the connector CANNOT place these.** Emit a **copy-paste IBKR combo
   ticket**: each leg's action (BUY/SELL, to-OPEN/CLOSE), readable symbol + `conId`, strike/expiry/right,
   quantity, ratio; `orderType=LMT`; net debit/credit limit (mid-or-better); `tif=DAY`; and the entry note
   ("enter as ONE combo; do not leg in"). Approval here = "I'll enter this in IBKR myself."
4. **Equity/ETF result only:** `create_order_instruction` with conId, action (BUY/SELL), quantity,
   `orderType=LMT`, `lmtPrice` (mid-or-better), `tif=DAY`. **Never** market. Report the **instruction ID**;
   tell the user to review/transmit in IBKR.
5. Don't claim a fill; confirm only via `get_account_orders` / `get_account_positions`.

---

## 12. HARD GUARDRAILS — NEVER

- **Never** place/modify/cancel an order without explicit per-order approval here.
- **Never** use market orders. Limit only, mid-or-better.
- **Never** act on missing, crossed, or stale (> `data_staleness_max_min`) data — flag.
- **Never** infer thesis status; it's a human input.
- **Never** roll a **vertical/debit spread down** (forbidden); for a naked call, never roll down unless
  thesis is confirmed intact.
- **Never** exceed `max_notional_pct` or "average down" beyond config without explicit flag + approval.
- **Never** exercise early — SELL-TO-CLOSE instead; if the user insists, warn it forfeits
  extrinsic and needs full share capital.
- **Never** chase an illiquid spread (> `max_bidask_spread_pct`); propose a patient limit.
- **Never reflexively CLOSE an impaired/stopped but far-dated, slow-bleeding LEAP.** Show §10-G
  cost-of-waiting and ASK CONVICTION first (math → ask → conclude); a -50% stop with ~600 DTE bleeding
  < the leverage-cost ceiling is a CLOSE-CANDIDATE, not an urgent cut (§6 rule 2).
- **Never tell the user to leg a multi-leg roll or spread OPEN sequentially.** Every option action is a
  manual IBKR ticket (connector places equity/ETF only) and goes as ONE native combo. If IBKR can't build
  the combo, instruct the user **not to enter leg 1** (a partial fill = naked unhedged delta chased
  through a moved market). The lone exception is **closing** an already-hedged pair, which may go
  **short-leg-first** (risk-reducing) if a combo is unavailable.

### Margin & assignment (short legs — PMCC diagonals and vertical short legs)
A PMCC is a **diagonal** (long LEAP + shorter-dated short call); IBKR margins the short leg against the
long, but that relief can **evaporate intraday on a sharp gap-up** — if the short goes deep ITM the
broker may treat assignment as imminent and demand maintenance margin, occasionally triggering an
intraday call. The skill therefore:
- Before proposing/approving any **short-call** leg, read `get_account_summary`
  (`maintenance_margin`, `excess_liquidity`, `available_funds`) and confirm a **buffer** — flag if
  `excess_liquidity` is thin relative to the short leg's notional. Never assume the long fully covers it.
- **Gap-up / deep-ITM short:** if the short strike sits at/below spot (ITM) and near ex-div or expiry,
  flag **early-assignment risk** and recommend buy-to-close or roll up-and-out — *before* assignment,
  not after.
- **Ex-dividend:** an ITM short call into ex-div is the classic early-assignment trigger; flag and
  suggest closing the short ahead of the ex-date.
- Keep a standing margin buffer (don't deploy to full `buying_power`); short-leg margin is dynamic and
  re-computed continuously by IBKR, so a position fine at entry can demand more after a gap.
- **Hard halt:** if `excess_liquidity` is near zero or a short leg is assignment-imminent, stop and
  report — do not propose new risk.

- **Halt and report** if: data won't load, buying power can't cover a proposed debit, **short-leg
  margin buffer is thin / assignment is imminent**, a single action would concentrate the portfolio,
  or anything is ambiguous.

---

## 13. FIRST-RUN CALIBRATION (once)

1. Resolve `account_id` from the user's CLAUDE.md/memory (if not configured there, **ASK** the user — never assume). Then confirm which positions are **in-scope LEAPS**, and which long+short pairs are
   **debit spreads** (give the long/short legs) vs **PMCC** — so each routes to the right engine.
2. Probe `get_price_snapshot` on one option to learn **which greeks/IV fields return**; set the
   delta/IV fallback path.
3. Collect **thesis status** + **asset class** per open position.
4. Confirm CONFIG defaults fit the user's risk tolerance (esp. `*_max_notional_pct`,
   `stop_loss_pct`, roll windows, `risk_free_rate_pct`).
5. Reconcile `memory.md` / `CLAUDE.md` against live data; correct or flag any stale fact (conid map,
   "unavailable" fields that now return, closed positions, dead TODOs) rather than propagating it.

---

*Encodes the user's chosen rules and enforces human approval on every order. An analysis and
order-preparation aid — not financial advice, not an autonomous trader. Markets, fills, and
outcomes are the user's responsibility.*
