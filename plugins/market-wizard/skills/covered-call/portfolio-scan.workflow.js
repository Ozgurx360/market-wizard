export const meta = {
  name: 'covered-call-portfolio-scan',
  description: 'Read-only covered-call review across all eligible share lots; returns a ranked action board',
  phases: [{ title: 'Scan' }, { title: 'Synthesize' }],
}
// args: { account_id, lots: [{ symbol, shares, raw_basis, intent, existing_short|null }], statements_path }
// NOTE: the caller (SKILL.md §11) scouts `lots` INLINE first — positions with >=100 shares,
// each paired with any existing short call, and the per-ticker intent from the ledger (asking if missing).
// `statements_path` = folder with the IBKR Activity Statement CSVs (PRIMARY option-premium source, §4).

const PER_LOT_SCHEMA = {
  type: 'object',
  properties: {
    symbol: { type: 'string' },
    intent: { type: 'string' },
    adjusted_basis: { type: 'number' },
    premium_to_date: { type: 'number' },
    writes_count: { type: 'integer' },
    suggested_write: { type: 'object' },          // {strike, expiry, dte, delta, premium, ret_if_flat, ret_if_called}
    // --- existing short economics (null when no short) — feeds the §7 engine + §10-A action board ---
    short_strike: { type: ['number', 'null'] },
    short_expiry: { type: ['string', 'null'] },
    short_dte: { type: ['integer', 'null'] },
    short_delta: { type: ['number', 'null'] },
    short_mark: { type: ['number', 'null'] },     // positive, per-share
    captured_pct: { type: ['number', 'null'] },   // (credit_received − short_mark)/credit_received × 100, per-share
    existing_action: { type: 'string' },          // HOLD|BUY-TO-CLOSE|ROLL-UP|ROLL-OUT|ROLL-UP&OUT|LET-ASSIGN|DEFEND|null
    flags: { type: 'array', items: { type: 'string' } },
  },
  required: ['symbol', 'adjusted_basis', 'flags'],
}

phase('Scan')
const results = (await parallel((args.lots || []).map(lot => () =>
  agent(
    `You are a READ-ONLY covered-call analyst for ${lot.symbol} (${lot.shares} shares, raw basis ${lot.raw_basis}, intent ${lot.intent}). ` +
    `Use ONLY IBKR read tools (get_account_trades, get_price_snapshot, search_contracts, get_option_parameters, get_option_data) plus reading the IBKR Activity Statement CSVs. PLACE NOTHING — no order/create/delete tools. ` +
    (lot.existing_short
      ? `This lot ALREADY has a short call (do NOT re-discover which option row it is — it is given): ${JSON.stringify(lot.existing_short)}. `
        + `Classify THIS known short into HOLD/BUY-TO-CLOSE/ROLL-UP/ROLL-OUT/ROLL-UP&OUT/LET-ASSIGN/DEFEND and return short_strike, short_expiry, short_dte, short_delta, short_mark, captured_pct. `
        + `NORMALIZE the credit: credit_received = abs(avgCost) made per-share (divide by multiplier if per-contract); short_mark and captured_pct must be POSITIVE per-share. `
        + `PREMIUM DOUBLE-COUNT (F2): this short's premium is ALREADY inside adjusted_basis — do NOT re-add it. For its assignment economics use loss_if_assigned = (strike − adjusted_basis) × 100 × qty, and return_if_called_vs_adjbasis = (strike − adjusted_basis)/adjusted_basis × 365/DTE (NO + premium). `
      : `This lot has NO existing short — set short_* and captured_pct to null and existing_action to null. `) +
    `1) LEDGER (§4): adjusted_basis = raw_basis − net covered-call premium per share. Compute net premium from the IBKR Activity Statement CSVs at ${args.statements_path || '<statements_path — ASK if unset>'} (PRIMARY): in each CSV's Trades section, rows with Asset Category "Equity and Index Options" whose OCC Symbol is for ${lot.symbol} and ENDS IN " C" (calls only — drop puts); keep only the SHORT-call lifecycle (sell-to-open Quantity<0 Code O + its buy-to-close Quantity>0 Code C); EXCLUDE long-call (directional) trades. net premium = Σ Proceeds − Σ abs(Comm/Fee). Then cover the gap after the latest CSV end-date with get_account_trades (sec_type=OPT) — but it has NO right/strike, so attribute gap trades to calls ONLY when unambiguous (ticker had only calls in that window, or they match the current short); otherwise FLAG "recent trades since <CSV end date> can't be auto-attributed to calls". Do NOT guess call vs put from connector trades. Report premium_to_date ($) and writes_count = distinct sell-to-open ORDERS (group fills by order_id / Date/Time+order — NOT fills). If shares were partially sold, do NOT divide by current shares — flag "adjusted basis unreliable after partial sale". ` +
    `2) If NO existing short: propose ONE write (suggested_write) in the ${lot.intent} delta band, 30–45 DTE; give ret_if_flat and ret_if_called (annualized on current price). For a PROPOSED new write, repair-vs-adjusted-basis ADDS the proposed premium: (premium + strike − adjusted_basis)/adjusted_basis × 365/DTE. ` +
    `3) Flag ex-div, earnings, below-adjusted-basis strike, stale/crossed quotes, un-attributable gap trades. Return ONLY the structured fields.`,
    { label: `scan:${lot.symbol}`, phase: 'Scan', schema: PER_LOT_SCHEMA }
  )
)).filter(Boolean)

phase('Synthesize')
return results   // main loop renders the §10-A action board + numbered PENDING-APPROVAL tickets
