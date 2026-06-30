---
name: chart-read
description: >
  Technical-analysis read on any holding or watch-list ticker, scoped to the market-wizard options
  workflow. Pulls IBKR price history, computes the weekly-bias / daily-trigger indicator stack (RSI,
  MACD, 200/50-SMA, Bollinger), flags divergence candidates, reads IV-RANK (relative, not absolute IV),
  renders a date-stamped Price/RSI/MACD chart, and writes a dated decision entry with trigger levels.
  Read-only; it produces the chart-and-regime read that FEEDS the options skills (leaps / covered-call)
  rather than duplicating them; it never infers your thesis. Trigger on: "chart-read TICKER",
  "chart-read review of my holdings", "technical / regime read on TICKER before I write a call or LEAP",
  "is TICKER at a support/resistance level for an options entry", "confluence/divergence read on TICKER
  before I sell premium", "is TICKER's IV-rank rich enough to sell premium", "where's my entry trigger /
  invalidation on TICKER", "log a chart-read decision on TICKER".
---

# Chart-Read — technical read, chart, and decision log

A **decision aid**, not an autotrader and not financial advice. Turns one ticker into a disciplined,
reproducible read: the indicator stack, a date-stamped chart, an IV-rank check, a divergence flag,
and a dated decision with explicit trigger levels — appended to your decisions log. It does the
*technical* layer; the *options lifecycle* (which call to write, when to roll) belongs to the
`leaps` and `covered-call` skills, which this feeds. (A `csp` cash-secured-put skill is planned; do
not hand off to it until it actually ships.)

---

## OPERATING MODE (read first)

- **Read-only.** This skill pulls quotes/positions and produces analysis + charts. It places **no orders**.
  Any trade it implies is handed off to the strategy skills or written as a copy-paste ticket you transmit yourself.
- **Never infers your thesis.** "Bullish / intact / broken" is a **human input**. Regime and momentum are
  facts off the chart; *conviction* is yours. On an ambiguous or impaired setup it shows the math and **asks**.
- **TA = tempo, not prophecy.** Every signal is a **probability tilt**, never a prediction. Divergences are
  flagged as *candidates to verify on the chart*, and they fail constantly in strong trends — say so, never oversell one.
- **Your context comes from your own files.** Account number, decisions-log path, and any per-ticker basis are
  read from the installer's `CLAUDE.md` / `memory.md`. If a needed value is missing, **ask** — never hard-code.
- **Stops and asks** whenever data is missing, stale, or contradictory. It flags; it does not guess.
- **One ticker at a time, by default.** Each ticker is its own interactive read. **Batch only on an explicit
  request** — "all holdings", "whole portfolio", or a named list of tickers — then loop the same chart per
  name and close with a one-line-per-name summary table, skipping the teaching pauses. Never sweep the book unprompted.

---

## CONFIG (the engine's built-in defaults — see the override note)

```
# Indicator stack
RSI_LEN            = 14
MACD               = (12, 26, 9)
SMA_DAILY_REGIME   = 200      # daily regime line
SMA_DAILY_FAST     = 50
SMA_WEEKLY_REGIME  = 40       # ~200-day on the weekly
BOLLINGER          = (20, 2)  # population std (ddof=0), matches StockCharts

# Timeframe model
BIAS_TF            = "weekly" # weekly sets bias
TRIGGER_TF         = "daily"  # daily times the entry

# Gates
IV_RANK_SELL_ZONE  = 60       # >= this 13-wk IV-rank = premium rich enough to SELL
CONFLUENCE_MIN     = 3        # need >= 3 of 4: location / divergence / confirmation / timeframe-aligned
SWING_FRACTAL_K    = 3        # bars each side that define a swing high/low
CHART_WINDOW       = 90       # sessions shown on the daily chart

# Output
DECISIONS_LOG      = "<from CLAUDE.md, else ask>"   # e.g. a Trading-Decisions.md in the working folder
ASSETS_DIR         = "./assets"                      # engine default; skill points --outdir at assets/ beside DECISIONS_LOG. Outputs: .png .svg .html .widget.html
DATA_AS_OF         = "prior session close"           # ignore weekend/stale 'last' snapshots
```

> **Override note (honest):** these values document `deepdive.py`'s built-in constants. Runtime CLI flags:
> `--window` (→ CHART_WINDOW), `--iv-sell-zone` (→ IV_RANK_SELL_ZONE), `--strike <p> [<p> …]` (one or more
> dashed price-panel lines — no constant), and `--logscale` (log-scale the price panel; for parabolic names).
> **`--log` (canonical; `--full` is an alias) is the output switch:** by **default** the engine runs
> **inline-only** — it computes the stack and writes just the `.widget.html` fragment, *never importing
> matplotlib* (the fast path, ~2 s cheaper per run). Pass **`--log`** to ALSO render the static `.png`/`.svg`
> + standalone `.html` — use it when you're going to **log a decision entry** (the log embeds the PNG). IV
> fields passed as 0–1 fractions are **auto-scaled to percent with a warning** (so the sell-zone gate can't
> silently fail). The rest are fixed in the engine; edit the constants at the top of `deepdive.py` to change
> them. Editing this block alone does nothing.

---

## WORKFLOW

1. **Resolve** the ticker and (if it's a holding) the position from the IBKR connector. Read the decisions-log
   path, its `assets/` folder (ASSETS_DIR = an `assets/` beside the log), and any saved basis from the user's
   `CLAUDE.md` / `memory.md`; ask if absent. Pass that `assets/` as `--outdir` so charts land beside the log.
2. **Pull data** (IBKR MCP): daily history (~1 yr), weekly history (~2 yr), and an IV snapshot
   (current IV, the 13/26/52-wk **IV-percentile/rank**, realized vol). **Use the prior-session close** — discard a
   stale weekend/intraday "last" if it disagrees with the latest **completed** history bar (set `asof` to that bar).
   - **The connector returns IV-percentile and vols as FRACTIONS (0–1).** The engine now auto-scales 0–1 values
     to percent (e.g. `high_13w` 0.38 → `rank13: 38`) and **warns** when it does, so the sell-zone gate can't
     silently always-fail. Still prefer to pass percent and stay consistent across the fields.
3. **Compute + chart** — write the pulled series to a temp JSON and run the engine. **Default = inline-only
   (fast):** it computes the stack and writes just the `.widget.html` fragment for the inline render — no
   matplotlib, no static files. Add **`--log`** only when you're going to log the read (it also writes the
   PNG/SVG/HTML the log embeds).
   `python3 "${CLAUDE_PLUGIN_ROOT}/skills/chart-read/scripts/deepdive.py" --input <tmp>.json --outdir <ASSETS_DIR> --window <CHART_WINDOW> [--strike <p> [<p> …]] [--logscale] [--log]`
   It always prints the stack as JSON (price + SMA(200/50) + Bollinger + last-price label + strikes / RSI / MACD); the `chart_*` fields report what was actually written. Outputs:
   - **`.widget.html`** *(always)* — a `show_widget`-ready fragment, the source of the inline chart in chat (step 4). On a default run this is the **only** file written.
   - **PNG/SVG** *(only with `--log`)* — the static, date-stamped image the OUTPUT template embeds in the decisions log. A default run does **not** produce it.
   - **standalone `.html`** *(only with `--log`)* — a self-contained interactive chart to open in a browser; the log links it next to the PNG.
   - **`--strike`** — pass the strikes of the user's **actual short options on this ticker** (read them from the IBKR positions) so the chart shows where the real obligations sit. One or many. Prefer the **near-the-money** strikes that matter to the decision — a deep-OTM strike stretches the y-axis and squishes the price action.
   - **`--logscale`** — use for parabolic names (a ~3×+ range) so the early action isn't crushed flat.
   On bad/missing data it prints a one-line `{"error": ...}` and exits non-zero — read it and STOP, don't guess.
   (First run in a fresh sandbox — only `--log` needs matplotlib:
   `python3 -m pip install "numpy>=1.23" "pandas>=1.5" "matplotlib>=3.6"`.)
4. **Show it inline** — don't make the user open a file. Render the chart in the chat so they see it
   immediately (Cowork and Claude Code): pass the **contents of the engine's `<asof>_<TICKER>_daily.widget.html`**
   to the `mcp__visualize__show_widget` tool — it's a ready-made fragment of the same 3-panel chart (Chart.js
   from the cdnjs allow-list, dark-mode aware). Put the ticker + as-of date in your chat text, not in the widget.
5. **Read it** (see THE READ): weekly bias → daily trigger → structure → divergence candidate → IV-rank.
6. **Decide** — one verdict with trigger levels expressed as **underlying prices**. If options are in play, show
   **premium-adjusted basis** and hand the action to `leaps` / `covered-call`.
7. **Log it** — append a dated entry to `DECISIONS_LOG` using the OUTPUT template, embedding the chart.
   The entry embeds the `.png`, so the run **must have used `--log`**. A default (inline) run does NOT produce
   the PNG — so before writing the entry, **re-run step 3 with `--log`** to render it. Never embed a chart the
   run didn't write (no broken image links).

---

## THE READ

**Timeframe model.** Weekly = **bias** (price vs the 40-wk line; weekly RSI/MACD). Daily = **trigger** (price vs
the 200-SMA; daily RSI/MACD/Bollinger). An A-grade signal is a daily trigger *in the direction of* the weekly bias.

**The stack, in one line each.** 200-SMA = regime (above = trust bullish signals, distrust bearish; below = the
reverse). RSI = momentum/divergence (it can sit "overbought" the whole way up — overbought is **not** a sell).
MACD = confirmation (signal-line cross / histogram flip). Bollinger = dynamic S/R + a volatility read; %B near 0/1
= stretched to a band, not a signal alone.

**Divergence cheat (the engine flags candidates; you confirm on the chart).**

| Type | Price | Indicator | Meaning | Tilt |
|---|---|---|---|---|
| Regular **bull** | lower low | higher low | reversal up | buy / sell put |
| Regular **bear** | higher high | lower high | reversal down | pause / sell call |
| Hidden **bull** | higher low | lower low | continue up | add in uptrend |
| Hidden **bear** | lower high | higher high | continue down | don't add |

A divergence is a **warning, not a trade** until it stacks `CONFLUENCE_MIN`-of-4: **location** (a level that
matters), **divergence**, **confirmation** (price starts to agree — MACD cross / RSI reclaim / structure break),
**timeframe-aligned**. No confirmation → **wait**. The engine only compares the **last two confirmed swings** and
reads RSI at the *price* swing bar — a deliberate simplification, so always eyeball the chart before acting.

**IV-rank, not absolute IV.** Whether premium is rich is decided by **IV-rank/percentile** (where today's IV sits
in the name's own recent range), *not* the headline IV%. `>= IV_RANK_SELL_ZONE` = rich → favour **selling**
premium (CC/CSP); low rank = cheap → favour **owning** / buying, and don't sell into it. Cross-check realized vs
implied. (Render this as an IV-rank bar when teaching.)

**Premium-adjusted cost basis (whenever an option is in play).** Show basis **net of premium collected** next to
the raw/accounting basis, arithmetic visible: assignment = strike − put premium; held shares = basis − call premium.

---

## OUTPUT — the decision-log entry (append to DECISIONS_LOG)

```
## <TICKER> — <one-line position> 

### Current plan
<live triggers, kept current: the watch level, the action if hit, the invalidation>

### Decision log
#### <YYYY-MM-DD> — <VERDICT>
![<TICKER> daily <date>](assets/<asof>_<TICKER>_daily.png) · [interactive chart](assets/<asof>_<TICKER>_daily.html)
- Weekly (bias): <price> vs 40-wk <x> -> ABOVE/BELOW; wRSI <x>; wMACD <x> (bull/bear)
- Daily (trigger): vs 200-SMA <x> -> ABOVE/BELOW; RSI <x>; MACD <l/s/h>; Bollinger <lo/mid/up>, %B <x>
- Structure: <recent swing highs/lows>
- Divergence: <candidate or "confirmation, none"> — confluence <n>/4
- IV: rank <n> (annual <x>%) -> rich/cheap; realized <x>%
- Read: <regime + momentum + what's missing> -> <verdict>
- Triggers: <buy/sell level + condition>; invalidation: <level>
```

The chart embed is relative to the **log file's** location — make sure `ASSETS_DIR` resolves correctly from
wherever `DECISIONS_LOG` lives (point `--outdir` at an `assets/` folder beside the log). Keep the chart
**date-stamped and append-only** — never overwrite a prior entry; each review adds a new dated block.

---

## What it deliberately does NOT do

- **Never places an order.** Read-only; option actions are copy-paste tickets, and lifecycle decisions go to
  `leaps` / `covered-call` (and `csp` once it ships).
- **Never infers your thesis from price** — it asks for conviction on anything ambiguous or impaired.
- **Never oversells a signal** — divergences are candidates, gated by confluence + confirmation; it states the
  failure modes.
- **Never hard-codes account or personal data** — everything personal is read from the installer's own files, or asked.
- **Never trusts a stale quote** — it reads off the prior-session close and flags weekend/frozen "last" values.

---

## Backlog (deferred)

- **Anchored VWAP** overlay from a chosen pivot (the ATH or a swing low) — not yet built; the indicator stack
  is otherwise settled. When prioritized, add it in `deepdive.py` and it flows to the PNG and the inline widget
  automatically (one chart config now drives both).

---

## Handoff

Chart-read ends at the **read + chart + logged verdict + trigger levels**. For the option itself —
which strike to write, when to roll, the annualized-return math — pass the verdict to:
`covered-call` (calls on shares), `leaps` (long calls / PMCC / verticals). A `csp` (cash-secured puts)
skill is planned; route to it only once it is actually installed.
