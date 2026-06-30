#!/usr/bin/env python3
"""market-wizard:chart-read - indicator + chart engine.

Generic and stateless. NO personal data lives here. Reads an OHLC(+IV) JSON on
--input, computes the weekly-bias / daily-trigger indicator stack, flags
divergence candidates, and renders a date-stamped 3-panel chart
(price + 200/50-SMA + Bollinger | RSI | MACD) as a static PNG/SVG *and* a
self-contained interactive Chart.js HTML. Prints a JSON summary to stdout.

  python3 deepdive.py --input data.json --outdir ./assets [--window 90] \
                      [--iv-sell-zone 60] [--strike 95]

Input JSON (price series ordered oldest -> newest):
{
  "ticker": "XYZ",
  "asof":   "2026-06-26",
  "daily":  {"close": [...], "high": [...], "low": [...]},
  "weekly": {"close": [...], "high": [...], "low": [...]},          # optional but recommended
  "iv":     {"annual_pct": 80, "rank13": 5, "rank26": 6,
             "rank52": 20, "realized_pct": 104}                     # optional
}

Robustness contract:
  - Required: daily.close (non-empty list of finite numbers). Anything else is
    reported as a one-line JSON {"error": ...} on stdout with a non-zero exit -
    never a raw traceback.
  - Optional fields (weekly, iv) degrade gracefully whether absent, empty, or
    the wrong type. iv.rank13 is coerced from str/number; non-numeric -> sell_zone
    skipped with a warning rather than a crash.
  - Indicators that need more bars than supplied are emitted as null, never as a
    confident-but-meaningless number (e.g. MACD needs >= slow+signal bars).
  - ticker / asof are untrusted input: ticker is sanitized for the filename and
    asof must be YYYY-MM-DD, so neither can traverse out of --outdir.

Requires: numpy (always), matplotlib + pandas (for the chart; degrades gracefully).
"""
import argparse, json, os, re, sys
import numpy as np

# --- fixed indicator defaults (the SKILL.md CONFIG block documents these) -----
RSI_LEN          = 14
MACD_FAST        = 12
MACD_SLOW        = 26
MACD_SIGNAL      = 9
SMA_DAILY_REGIME = 200
SMA_DAILY_FAST   = 50
SMA_WEEKLY       = 40
BOLL_LEN         = 20
BOLL_K           = 2
SWING_K          = 3
IV_RANK_SELL_ZONE = 60          # CLI-overridable via --iv-sell-zone
MACD_MIN_BARS    = MACD_SLOW + MACD_SIGNAL   # below this, MACD is warm-up garbage
MAX_BARS         = 6000         # ~24 yr daily / ~115 yr weekly; caps the pure-python loops

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class InputError(Exception):
    """Raised for bad/missing input; turned into a clean JSON error in main()."""


def ema(x, n):
    if len(x) == 0:
        return np.array([])
    k = 2 / (n + 1); o = [x[0]]
    for v in x[1:]:
        o.append(v * k + o[-1] * (1 - k))
    return np.array(o)


def _rsi_point(ag, al):
    # No losses -> 100, unless there are also no gains (flat/halted): conventionally 50.
    if al == 0:
        return 50.0 if ag == 0 else 100.0
    return 100 - 100 / (1 + ag / al)


def rsi_series(x, n=RSI_LEN):
    x = np.asarray(x, float); d = np.diff(x)
    g = np.where(d > 0, d, 0.0); l = np.where(d < 0, -d, 0.0)
    o = np.full(len(x), np.nan)
    if len(x) > n:
        ag = g[:n].mean(); al = l[:n].mean()
        o[n] = _rsi_point(ag, al)
        for i in range(n + 1, len(x)):
            ag = (ag * (n - 1) + g[i - 1]) / n
            al = (al * (n - 1) + l[i - 1]) / n
            o[i] = _rsi_point(ag, al)
    return o


def sma_series(x, n):
    x = np.asarray(x, float); o = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        o[i] = x[i - n + 1:i + 1].mean()
    return o


def boll(x, n=BOLL_LEN, k=BOLL_K):
    # population std (ddof=0), matching StockCharts / most charting platforms
    x = np.asarray(x, float)
    up = np.full(len(x), np.nan); mid = np.full(len(x), np.nan); lo = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        seg = x[i - n + 1:i + 1]; m = seg.mean(); s = seg.std()
        up[i] = m + k * s; mid[i] = m; lo[i] = m - k * s
    return up, mid, lo


def macd(x, f=MACD_FAST, s=MACD_SLOW, sig=MACD_SIGNAL):
    ml = ema(x, f) - ema(x, s); sl = ema(ml, sig)
    return ml, sl, ml - sl


def swings(series, k=SWING_K, kind="low"):
    """Symmetric strict k-bar fractal: an extremum strictly beyond BOTH its k
    left and k right neighbours. NaN windows (warm-up) are skipped. Note the
    last k bars can never be a confirmed swing - the freshest pivot lags by k."""
    s = np.asarray(series, float); idx = []
    for i in range(k, len(s) - k):
        left = s[i - k:i]; right = s[i + 1:i + k + 1]
        if not (np.isfinite(s[i]) and np.all(np.isfinite(left)) and np.all(np.isfinite(right))):
            continue
        if kind == "low" and s[i] < left.min() and s[i] < right.min():
            idx.append(i)
        if kind == "high" and s[i] > left.max() and s[i] > right.max():
            idx.append(i)
    return idx


def divergence(close, rsi):
    """Candidate regular divergence on the last two price swing lows/highs,
    read against RSI at those same bars. ALWAYS a candidate to verify on the
    chart - never authoritative (treat as a tilt). Only the last two swings are
    compared; earlier divergences are not surfaced. RSI is sampled at the PRICE
    swing (not RSI's own swing) - a deliberate simplification. Bars whose RSI is
    still in the warm-up (NaN) region are skipped, so no 'nan' leaks into output."""
    out = {"bullish": None, "bearish": None}
    rsi = np.asarray(rsi, float)

    lows = [i for i in swings(close, SWING_K, "low") if np.isfinite(rsi[i])]
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if close[b] < close[a] and rsi[b] > rsi[a]:
            out["bullish"] = (f"CANDIDATE regular-bull: price LL {close[a]:.2f}->{close[b]:.2f}, "
                              f"RSI HL {rsi[a]:.1f}->{rsi[b]:.1f} (verify on chart)")
        elif close[b] < close[a]:
            out["bullish"] = (f"none - confirmation (price LL, RSI also LL "
                              f"{rsi[a]:.1f}->{rsi[b]:.1f})")

    highs = [i for i in swings(close, SWING_K, "high") if np.isfinite(rsi[i])]
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if close[b] > close[a] and rsi[b] < rsi[a]:
            out["bearish"] = (f"CANDIDATE regular-bear: price HH {close[a]:.2f}->{close[b]:.2f}, "
                              f"RSI LH {rsi[a]:.1f}->{rsi[b]:.1f} (verify on chart)")
        elif close[b] > close[a]:
            out["bearish"] = (f"none - confirmation (price HH, RSI also HH "
                              f"{rsi[a]:.1f}->{rsi[b]:.1f})")
    return out


def _last(v):
    return None if (len(v) == 0 or not np.isfinite(v[-1])) else round(float(v[-1]), 2)


def _regime(price, sma_last):
    """Three-way on the displayed (rounded) values: ABOVE / BELOW / AT."""
    if sma_last is None:
        return None
    p = round(float(price), 2)
    return "AT" if p == sma_last else ("ABOVE" if p > sma_last else "BELOW")


def _coerce_1d(seq, name):
    """Coerce a sequence to a finite 1-D float array or raise InputError. Catches
    non-numeric values (str prices) and ragged/nested lists before they reach numpy
    indexing or matplotlib (which would otherwise surface as a raw traceback)."""
    try:
        arr = np.asarray(seq, dtype=float)
    except (ValueError, TypeError):
        raise InputError(f"{name} contains non-numeric values")
    if arr.ndim != 1:
        raise InputError(f"{name} must be a flat list of numbers, not nested/ragged")
    if not np.all(np.isfinite(arr)):
        raise InputError(f"{name} contains non-numeric/NaN values - refusing to "
                         "emit silently-wrong indicators")
    return arr


def _closes(block, name):
    """Optional close series -> (finite 1-D array | None, warning | None). NEVER
    raises: a present-but-malformed optional block degrades to absent + a warning."""
    if not isinstance(block, dict):
        return None, None
    c = block.get("close")
    if not isinstance(c, (list, tuple)) or len(c) == 0:
        return None, None
    try:
        return _coerce_1d(c, f"{name}.close"), None
    except InputError as e:
        return None, f"{e}; {name} ignored"


def _safe_ticker(tkr):
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(tkr)).strip("._")[:32]
    return safe or "TICKER"


def run(D, outdir, window, iv_sell_zone, strike=None):
    tkr_raw = str(D.get("ticker", "TICKER"))
    safe_tkr = _safe_ticker(tkr_raw)

    asof = str(D.get("asof", "") or "")
    warnings = []
    if asof and not _DATE_RE.match(asof):
        warnings.append(f"asof '{asof}' is not YYYY-MM-DD; dropped from filename/title")
        asof = ""

    # --- required: daily.close --------------------------------------------------
    daily = D.get("daily")
    if not isinstance(daily, dict) or not isinstance(daily.get("close"), (list, tuple)) \
            or len(daily.get("close")) == 0:
        raise InputError("missing or empty required field daily.close")
    dc = _coerce_1d(daily["close"], "daily.close")
    if len(dc) > MAX_BARS:
        warnings.append(f"daily series {len(dc)} bars exceeds MAX_BARS {MAX_BARS}; "
                        f"truncated to most recent {MAX_BARS}")
        dc = dc[-MAX_BARS:]

    s200 = sma_series(dc, SMA_DAILY_REGIME); s50 = sma_series(dc, SMA_DAILY_FAST)
    up, mid, lo = boll(dc); rsi = rsi_series(dc); ml, sl, hist = macd(dc)

    pctB = None
    if np.isfinite(up[-1]) and up[-1] != lo[-1]:
        pctB = round(float((dc[-1] - lo[-1]) / (up[-1] - lo[-1])), 2)

    # MACD is meaningless until we have >= slow+signal bars; null it otherwise.
    if len(dc) >= MACD_MIN_BARS:
        macd_last, sig_last, hist_last = _last(ml), _last(sl), _last(hist)
    else:
        macd_last = sig_last = hist_last = None
        warnings.append(f"daily series < {MACD_MIN_BARS} bars; MACD suppressed (warm-up)")

    sma200_last = _last(s200)
    out = {"ticker": tkr_raw, "asof": asof,
           "daily": {"price": round(float(dc[-1]), 2), "sma200": sma200_last, "sma50": _last(s50),
                     "rsi": _last(rsi), "macd": macd_last, "signal": sig_last, "hist": hist_last,
                     "boll_up": _last(up), "boll_mid": _last(mid), "boll_lo": _last(lo), "pctB": pctB,
                     "regime_vs_200": _regime(dc[-1], sma200_last)},
           "divergence": divergence(dc, rsi),
           "iv": {}}

    # --- optional: weekly -------------------------------------------------------
    wc, wwarn = _closes(D.get("weekly"), "weekly")
    if wwarn:
        warnings.append(wwarn)
    if wc is not None and len(wc) > MAX_BARS:
        warnings.append(f"weekly series truncated to most recent {MAX_BARS}")
        wc = wc[-MAX_BARS:]
    if wc is not None:
        w40 = sma_series(wc, SMA_WEEKLY); wr = rsi_series(wc); wml, wsl, wh = macd(wc)
        w40_last = _last(w40)
        if len(wc) >= MACD_MIN_BARS:
            wmacd, wsig, whist = _last(wml), _last(wsl), _last(wh)
        else:
            wmacd = wsig = whist = None
        out["weekly"] = {"price": round(float(wc[-1]), 2), "sma40": w40_last, "rsi": _last(wr),
                         "macd": wmacd, "signal": wsig, "hist": whist,
                         "bias_vs_40w": _regime(wc[-1], w40_last)}

    # --- optional: iv -----------------------------------------------------------
    iv_in = D.get("iv")
    if isinstance(iv_in, dict):
        out["iv"] = dict(iv_in)
        if "rank13" in out["iv"]:
            try:
                r = float(out["iv"]["rank13"])
            except (TypeError, ValueError):
                r = None
            out["iv"]["note"] = "IV-RANK (relative), not absolute IV, decides rich-vs-cheap"
            if r is None:
                out["iv"]["warning"] = "rank13 not numeric; sell_zone not computed"
            else:
                out["iv"]["sell_zone"] = r >= iv_sell_zone

    if warnings:
        out["warnings"] = warnings

    outdir_abs = os.path.abspath(outdir)
    # chart is the BASENAME only - never an absolute path, so embedding it in a
    # committed decision-log can't leak a local filesystem path. The dir is separate.
    out["chart"] = _chart(safe_tkr, tkr_raw, asof, dc, s200, s50, up, lo, rsi, ml, sl, hist,
                          window, outdir_abs)
    out["chart_html"] = _chart_html(safe_tkr, tkr_raw, asof, dc, s200, s50, up, lo, rsi,
                                    ml, sl, hist, window, outdir_abs, strike)
    out["chart_dir"] = outdir_abs
    return out


def _chart(safe_tkr, tkr_label, asof, dc, s200, s50, up, lo, rsi, ml, sl, hist, W, outdir):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec
    try:
        import pandas as pd
        x_full = pd.bdate_range(end=pd.Timestamp(asof) if asof else None, periods=len(dc))
    except Exception:
        x_full = np.arange(len(dc))
    N = len(dc); W = max(1, min(W, N)); s = N - W; x = x_full[s:]
    title_date = asof if asof else "(date n/a)"
    fig = plt.figure(figsize=(11, 8)); gs = GridSpec(3, 1, height_ratios=[3, 1, 1], hspace=0.12)
    a1 = fig.add_subplot(gs[0]); a2 = fig.add_subplot(gs[1], sharex=a1); a3 = fig.add_subplot(gs[2], sharex=a1)
    a1.plot(x, dc[s:], color="#185fa5", lw=1.8, label="Close")
    if not np.all(np.isnan(s200[s:])):
        a1.plot(x, s200[s:], color="#c98500", lw=1.3, ls="--", label="200-SMA")
    a1.plot(x, s50[s:], color="#888780", lw=1.0, ls=":", label="50-SMA")
    a1.plot(x, up[s:], color="#3987e5", lw=0.7, alpha=0.5)
    a1.plot(x, lo[s:], color="#3987e5", lw=0.7, alpha=0.5)
    a1.fill_between(x, lo[s:], up[s:], color="#3987e5", alpha=0.06)
    a1.set_title(f"{tkr_label} - daily - as of {title_date}", fontsize=12, loc="left", weight="bold")
    a1.legend(loc="upper left", fontsize=8, frameon=False); a1.grid(alpha=0.15)
    a2.plot(x, rsi[s:], color="#4a3aa7", lw=1.4)
    for y, c in [(70, "#e34948"), (50, "#888780"), (30, "#639922")]:
        a2.axhline(y, color=c, lw=0.8, ls="--", alpha=0.5)
    a2.set_ylim(10, 90); a2.set_ylabel("RSI(14)", fontsize=8); a2.grid(alpha=0.15)
    cols = ["#639922" if h >= 0 else "#e34948" for h in hist[s:]]
    a3.bar(x, hist[s:], color=cols, width=1.0, alpha=0.6)
    a3.plot(x, ml[s:], color="#185fa5", lw=1.1)
    a3.plot(x, sl[s:], color="#c98500", lw=1.0, ls="--")
    a3.axhline(0, color="#888780", lw=0.6); a3.set_ylabel("MACD", fontsize=8); a3.grid(alpha=0.15)
    plt.setp(a1.get_xticklabels(), visible=False); plt.setp(a2.get_xticklabels(), visible=False)
    a3.tick_params(labelsize=8)

    outdir = os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)
    base = os.path.join(outdir, f"{asof + '_' if asof else ''}{safe_tkr}_daily")
    # defense in depth: the filename must stay inside outdir
    if os.path.commonpath([outdir, os.path.realpath(base)]) != outdir:
        plt.close(fig)
        raise InputError("refusing to write chart outside --outdir")
    fig.savefig(base + ".png", dpi=120, bbox_inches="tight")
    fig.savefig(base + ".svg", bbox_inches="tight"); plt.close(fig)
    return os.path.basename(base) + ".png"


def _html_escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# Self-contained interactive chart. Chart.js v4 is pulled from a CDN (no build);
# the series are injected at __DATA__ and the title at __TITLE__. Deliberately
# uses no identifier containing personal data and no white page background, so it
# reads on a light OR dark host. Three stacked panels share one category x-axis;
# each y-axis is pinned to a fixed width so the panels line up vertically.
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
  :root { color-scheme: light dark; }
  body { margin:0; padding:14px 16px; background:transparent;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
  h1 { font-size:15px; font-weight:600; margin:0 0 10px; color:#33373d; }
  .panel { position:relative; width:100%; }
  .panel.price { height:340px; }
  .panel.rsi   { height:150px; }
  .panel.macd  { height:168px; }
  @media (prefers-color-scheme: dark) { h1 { color:#c9d1d9; } }
</style>
</head>
<body>
<h1>__TITLE__</h1>
<div class="panel price"><canvas id="price"></canvas></div>
<div class="panel rsi"><canvas id="rsi"></canvas></div>
<div class="panel macd"><canvas id="macd"></canvas></div>
<script>
const D = __DATA__;
(function () {
  const dark = !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  const tickC = dark ? '#c9d1d9' : '#33373d';
  const gridC = dark ? 'rgba(160,160,160,0.16)' : 'rgba(120,120,120,0.15)';
  Chart.defaults.color = tickC;
  Chart.defaults.font.size = 11;
  const YW = 60;
  const fixY = { afterFit(sc) { sc.width = YW; } };
  const tip = {
    mode: 'index', intersect: false,
    callbacks: { label: (c) => c.dataset.label + ': ' + (c.parsed.y == null ? '-' : Number(c.parsed.y).toFixed(2)) }
  };
  const xTop = { grid: { color: gridC }, ticks: { display: false } };
  const xBot = { grid: { color: gridC }, ticks: { autoSkip: true, maxTicksLimit: 8, maxRotation: 0 } };
  const flat = (v) => D.labels.map(() => v);
  const last = D.close.length - 1;
  const ptR = D.close.map((_, i) => i === last ? 4.5 : 0);
  const ptC = D.close.map((_, i) => i === last ? (dark ? '#7fb2f0' : '#1f5fb0') : 'rgba(0,0,0,0)');

  const priceDs = [
    { label: 'Boll up', data: D.bup, borderColor: 'rgba(57,135,229,0.45)', borderWidth: 0.8, pointRadius: 0, fill: '+1', backgroundColor: 'rgba(57,135,229,0.10)' },
    { label: 'Boll lo', data: D.blo, borderColor: 'rgba(57,135,229,0.45)', borderWidth: 0.8, pointRadius: 0, fill: false },
    { label: 'Close', data: D.close, borderColor: '#2f7ed8', borderWidth: 1.9, pointRadius: ptR, pointBackgroundColor: ptC, pointBorderColor: ptC, tension: 0 },
    { label: '200-SMA', data: D.sma200, borderColor: '#c98500', borderWidth: 1.3, borderDash: [6, 3], pointRadius: 0 },
    { label: '50-SMA', data: D.sma50, borderColor: '#9aa0a6', borderWidth: 1.1, borderDash: [2, 2], pointRadius: 0 }
  ];
  if (D.hlLabel) {
    priceDs.push({ label: D.hlLabel, data: flat(D.hl), borderColor: '#e34948', borderWidth: 1.3, borderDash: [7, 4], pointRadius: 0, fill: false });
  }
  new Chart(document.getElementById('price'), {
    type: 'line',
    data: { labels: D.labels, datasets: priceDs },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: true, labels: { boxWidth: 12, usePointStyle: true } }, tooltip: tip },
      scales: { x: xTop, y: Object.assign({ grid: { color: gridC } }, fixY) }
    }
  });

  new Chart(document.getElementById('rsi'), {
    type: 'line',
    data: {
      labels: D.labels, datasets: [
        { label: '70', data: flat(70), borderColor: 'rgba(227,73,72,0.55)', borderWidth: 0.8, borderDash: [5, 4], pointRadius: 0 },
        { label: '50', data: flat(50), borderColor: 'rgba(154,160,166,0.6)', borderWidth: 0.7, borderDash: [3, 3], pointRadius: 0 },
        { label: '30', data: flat(30), borderColor: 'rgba(99,153,34,0.6)', borderWidth: 0.8, borderDash: [5, 4], pointRadius: 0 },
        { label: 'RSI(14)', data: D.rsi, borderColor: '#6f5bd0', borderWidth: 1.6, pointRadius: 0 }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: Object.assign({}, tip, { filter: (i) => i.dataset.label === 'RSI(14)' }) },
      scales: { x: xTop, y: Object.assign({ min: 0, max: 100, ticks: { stepSize: 20 }, grid: { color: gridC } }, fixY) }
    }
  });

  const histC = D.hist.map((v) => v == null ? 'rgba(0,0,0,0)' : (v >= 0 ? 'rgba(99,153,34,0.6)' : 'rgba(227,73,72,0.6)'));
  new Chart(document.getElementById('macd'), {
    type: 'bar',
    data: {
      labels: D.labels, datasets: [
        { type: 'bar', label: 'Hist', data: D.hist, backgroundColor: histC, borderWidth: 0, categoryPercentage: 1.0, barPercentage: 1.0 },
        { type: 'line', label: 'MACD', data: D.macd, borderColor: '#2f7ed8', borderWidth: 1.3, pointRadius: 0 },
        { type: 'line', label: 'Signal', data: D.signal, borderColor: '#c98500', borderWidth: 1.0, borderDash: [5, 3], pointRadius: 0 }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: true, labels: { boxWidth: 12 } }, tooltip: tip },
      scales: { x: xBot, y: Object.assign({ grid: { color: gridC } }, fixY) }
    }
  });
})();
</script>
</body>
</html>
"""


def _chart_html(safe_tkr, tkr_label, asof, dc, s200, s50, up, lo, rsi, ml, sl, hist, W, outdir, strike):
    """Write a self-contained interactive Chart.js chart (price / RSI / MACD),
    in addition to the PNG/SVG. Chart.js loads from a CDN; the windowed series
    are embedded inline as JSON. Returns the BASENAME only (never an absolute
    path), matching _chart()'s contract so a committed log can't leak a path."""
    N = len(dc); W = max(1, min(W, N)); s = N - W
    try:
        import pandas as pd
        x_full = pd.bdate_range(end=pd.Timestamp(asof) if asof else None, periods=N)
        labels = [d.strftime("%Y-%m-%d") for d in x_full[s:]]
    except Exception:
        labels = [str(i) for i in range(s, N)]

    def J(arr):
        # window + JSON-safe: NaN/inf -> null so Chart.js renders a gap, not a crash
        vals = []
        for v in np.asarray(arr[s:], float):
            vals.append(round(float(v), 4) if np.isfinite(v) else None)
        return vals

    hl = hl_label = None
    if strike is not None and np.isfinite(strike):
        hl = round(float(strike), 4)
        hl_label = "Strike " + (str(int(hl)) if float(hl).is_integer() else str(hl))

    title_date = asof if asof else "(date n/a)"
    payload = {
        "labels": labels, "close": J(dc), "sma200": J(s200), "sma50": J(s50),
        "bup": J(up), "blo": J(lo), "rsi": J(rsi),
        "macd": J(ml), "signal": J(sl), "hist": J(hist),
        "hl": hl, "hlLabel": hl_label,
    }
    html_doc = (_HTML_TEMPLATE
                .replace("__DATA__", json.dumps(payload))
                .replace("__TITLE__", _html_escape(f"{tkr_label} as of {title_date}")))

    outdir = os.path.abspath(outdir); os.makedirs(outdir, exist_ok=True)
    base = os.path.join(outdir, f"{asof + '_' if asof else ''}{safe_tkr}_daily")
    # same containment guard as _chart(): never write outside --outdir
    if os.path.commonpath([outdir, os.path.realpath(base)]) != outdir:
        raise InputError("refusing to write chart outside --outdir")
    path = base + ".html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    return os.path.basename(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--outdir", default="./assets")
    ap.add_argument("--window", type=int, default=90)
    ap.add_argument("--iv-sell-zone", type=float, default=IV_RANK_SELL_ZONE,
                    help="13-wk IV-rank at/above which premium is 'rich' (default 60)")
    ap.add_argument("--strike", type=float, default=None,
                    help="optional underlying price; draws a dashed horizontal line on the HTML price panel")
    a = ap.parse_args()

    try:
        with open(a.input, encoding="utf-8-sig") as f:   # -sig tolerates a UTF-8 BOM
            D = json.load(f)
    except FileNotFoundError:
        print(json.dumps({"error": f"input file not found: {a.input}"})); sys.exit(2)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(json.dumps({"error": f"invalid input file {a.input}: {e}"})); sys.exit(2)
    except OSError as e:
        print(json.dumps({"error": f"cannot read {a.input}: {e}"})); sys.exit(2)

    try:
        if not isinstance(D, dict):
            raise InputError("input JSON must be an object")
        out = run(D, a.outdir, a.window, a.iv_sell_zone, a.strike)
    except InputError as e:
        print(json.dumps({"error": str(e)})); sys.exit(2)
    except OSError as e:    # makedirs/savefig: FileExists, NotADirectory, Permission, ...
        print(json.dumps({"error": f"filesystem error writing chart output: {e}"})); sys.exit(2)

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
