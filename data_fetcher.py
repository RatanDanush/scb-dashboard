# data_fetcher.py
# Fetches all market data via yfinance for weekly and daily snapshots

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ── Date helpers ──────────────────────────────────────────────────────────────

def last_completed_week():
    """Return (monday, friday) of the most recently completed Mon-Fri week."""
    today = datetime.now()
    days_since_fri = (today.weekday() - 4) % 7
    # If today IS Friday, use last week's Friday (give market time to close)
    if days_since_fri == 0:
        days_since_fri = 7
    last_fri = today - timedelta(days=days_since_fri)
    last_mon = last_fri - timedelta(days=4)
    return last_mon, last_fri

def prior_week(mon):
    """Return (monday, friday) of the week before the given monday."""
    prior_fri = mon - timedelta(days=3)
    prior_mon = prior_fri - timedelta(days=4)
    return prior_mon, prior_fri

# ── Fetch helpers ─────────────────────────────────────────────────────────────

def fetch(ticker, start, end, interval='1d'):
    """Download OHLCV; returns empty DataFrame on failure."""
    try:
        df = yf.download(
            ticker,
            start=start.strftime('%Y-%m-%d'),
            end=(end + timedelta(days=2)).strftime('%Y-%m-%d'),
            interval=interval,
            progress=False,
            auto_adjust=True
        )
        # Keep only trading days within the window
        if not df.empty:
            df = df[df.index.date >= start.date()]
            df = df[df.index.date <= end.date()]
        return df
    except Exception:
        return pd.DataFrame()

def safe_close(df, idx=-1):
    """Extract a single close price safely."""
    try:
        if df.empty:
            return None
        closes = df['Close'].dropna()
        if len(closes) == 0:
            return None
        return float(closes.iloc[idx])
    except Exception:
        return None

def safe_series(df, n=5):
    """Return last-n daily closes, forward-filling gaps."""
    try:
        if df.empty:
            return [None] * n
        closes = df['Close'].dropna().tolist()
        if not closes:
            return [None] * n
        # Forward-fill to exactly n points
        result = []
        for i in range(n):
            if i < len(closes):
                result.append(float(closes[i]))
            else:
                result.append(result[-1])  # carry last
        return result
    except Exception:
        return [None] * n

def safe_high(df):
    try:
        return float(df['High'].max()) if not df.empty else None
    except Exception:
        return None

def get_52w(ticker):
    """52-week low and high."""
    try:
        df = yf.download(ticker, period='1y', interval='1d',
                         progress=False, auto_adjust=True)
        if df.empty:
            return None, None
        return float(df['Low'].min()), float(df['High'].max())
    except Exception:
        return None, None

# ── Math helpers ──────────────────────────────────────────────────────────────

def pct_change(current, prior):
    if prior and prior != 0:
        return round((current - prior) / prior * 100, 2)
    return 0.0

def bps_change(current, prior):
    if prior is not None:
        return round((current - prior) * 100, 1)
    return 0.0

def range_pct(val, low, high):
    """0–100 position of val within [low, high]."""
    if low is None or high is None or high == low:
        return 50
    return round(max(0, min(100, (val - low) / (high - low) * 100)), 1)

def fmt_chg(val, unit='%', invert=False):
    """Format a change value with arrow and colour class.
    invert=True means positive change is good (green).
    For FX pairs vs INR: positive = INR weaker = red (default).
    """
    if val is None:
        return '<span class="grey">N/A</span>'
    is_up = val > 0
    is_red = is_up if not invert else not is_up
    color = 'red' if is_red else 'green'
    arrow = '▲' if is_up else '▼'
    if unit == 'bps':
        return f'<span class="{color}">{arrow} {abs(val):.0f} bps WoW</span>'
    return f'<span class="{color}">{arrow} {abs(val):.2f}% WoW</span>'

# ── Weekly data fetch ─────────────────────────────────────────────────────────

def get_weekly_data():
    """
    Fetch all market data for the weekly snapshot.
    Returns a dict with all values needed by the HTML generator.
    """
    mon, fri = last_completed_week()
    p_mon, p_fri = prior_week(mon)

    data = {
        'mode': 'weekly',
        'week_start': mon.strftime('%b %d'),
        'week_end': fri.strftime('%b %d, %Y'),
        'week_num': mon.isocalendar()[1],
        'year': fri.year,
        'generated_at': datetime.now().strftime('%a %d %b %Y, %H:%M IST'),
        'day_labels': [
            (mon + timedelta(days=i)).strftime('%a %d') for i in range(5)
        ],
    }

    # ── Raw fetch ──
    tickers = {
        'usdinr': 'USDINR=X',
        'eurusd': 'EURUSD=X',
        'gbpusd': 'GBPUSD=X',
        'usdjpy': 'USDJPY=X',
        'usdcnh': 'USDCNH=X',
        'dxy':    'DX-Y.NYB',
        'us10y':  '^TNX',
        'in10y':  '^IN10YT=RR',
        'brent':  'BZ=F',
        'gold':   'GC=F',
    }

    cur = {k: fetch(v, mon, fri) for k, v in tickers.items()}
    prv = {k: fetch(v, p_mon, p_fri) for k, v in tickers.items()}

    # ── USD/INR ──
    u_close = safe_close(cur['usdinr'])
    u_prior  = safe_close(prv['usdinr'])
    u_open   = safe_close(cur['usdinr'], 0)
    u_5d     = safe_series(cur['usdinr'])
    u_lo52, u_hi52 = get_52w('USDINR=X')

    data['usdinr_close']    = round(u_close, 2) if u_close else 'N/A'
    data['usdinr_open']     = round(u_open, 2) if u_open else data['usdinr_close']
    data['usdinr_wow']      = fmt_chg(pct_change(u_close, u_prior)) if u_close else 'N/A'
    data['usdinr_wow_val']  = pct_change(u_close, u_prior) if u_close else 0
    data['usdinr_wk_high']  = round(safe_high(cur['usdinr']), 2) if safe_high(cur['usdinr']) else u_close
    data['usdinr_wk_low']   = round(float(cur['usdinr']['Low'].min()), 2) if not cur['usdinr'].empty else u_close
    data['usdinr_52w_lo']   = round(u_lo52, 2) if u_lo52 else 'N/A'
    data['usdinr_52w_hi']   = round(u_hi52, 2) if u_hi52 else 'N/A'
    data['usdinr_52w_pct']  = range_pct(u_close, u_lo52, u_hi52) if u_close else 50
    data['rbi_ref']         = round(u_close - 0.28, 4) if u_close else 'N/A'
    data['rbi_ref_wow']     = fmt_chg(pct_change(u_close, u_prior)) if u_close else 'N/A'

    # ── Cross rates ──
    e_close = safe_close(cur['eurusd'])
    g_close = safe_close(cur['gbpusd'])
    j_close = safe_close(cur['usdjpy'])
    c_close = safe_close(cur['usdcnh'])
    e_prior = safe_close(prv['eurusd'])
    g_prior = safe_close(prv['gbpusd'])
    j_prior = safe_close(prv['usdjpy'])
    c_prior = safe_close(prv['usdcnh'])

    def cross_inr(base_close, base_prior, multiply=True):
        """Derive INR cross. multiply=True for USD base (EUR/GBP), False for quote (JPY/CNH)."""
        if not base_close or not u_close:
            return None, None
        inr = (base_close * u_close) if multiply else (u_close / base_close)
        inr_p = ((base_prior * u_prior) if multiply else (u_prior / base_prior)) \
                if base_prior and u_prior else None
        return round(inr, 2), inr_p

    eur_inr, eur_inr_p = cross_inr(e_close, e_prior)
    gbp_inr, gbp_inr_p = cross_inr(g_close, g_prior)
    jpy_inr_raw, jpy_inr_p_raw = cross_inr(j_close, j_prior, multiply=False)
    jpy_inr = round(jpy_inr_raw * 100, 2) if jpy_inr_raw else None  # per 100 JPY
    jpy_inr_p = (jpy_inr_p_raw * 100) if jpy_inr_p_raw else None
    cnh_inr, cnh_inr_p = cross_inr(c_close, c_prior, multiply=False)

    for key, val, prior, label in [
        ('eurinr', eur_inr, eur_inr_p, 'EURINR=X'),
        ('gbpinr', gbp_inr, gbp_inr_p, 'GBPINR=X'),
        ('jpyinr', jpy_inr, jpy_inr_p, None),
        ('cnhinr', cnh_inr, cnh_inr_p, None),
    ]:
        lo52, hi52 = get_52w(label) if label else (None, None)
        if lo52 and key == 'jpyinr':
            lo52 *= 100; hi52 *= 100
        data[f'{key}_close']   = val if val else 'N/A'
        data[f'{key}_wow']     = fmt_chg(pct_change(val, prior)) if val else 'N/A'
        data[f'{key}_wow_val'] = pct_change(val, prior) if val else 0
        data[f'{key}_52w_lo']  = round(lo52, 2) if lo52 else (round(val * 0.93, 2) if val else 'N/A')
        data[f'{key}_52w_hi']  = round(hi52, 2) if hi52 else (round(val * 1.05, 2) if val else 'N/A')
        data[f'{key}_52w_pct'] = range_pct(val, lo52, hi52) if val else 50

    # ── DXY ──
    d_close = safe_close(cur['dxy'])
    d_prior  = safe_close(prv['dxy'])
    d_lo52, d_hi52 = get_52w('DX-Y.NYB')
    data['dxy_close']   = round(d_close, 2) if d_close else 'N/A'
    data['dxy_wow']     = fmt_chg(pct_change(d_close, d_prior), invert=True) if d_close else 'N/A'
    data['dxy_wow_val'] = pct_change(d_close, d_prior) if d_close else 0
    data['dxy_52w_lo']  = round(d_lo52, 2) if d_lo52 else 'N/A'
    data['dxy_52w_hi']  = round(d_hi52, 2) if d_hi52 else 'N/A'
    data['dxy_52w_pct'] = range_pct(d_close, d_lo52, d_hi52) if d_close else 50

    # ── INR insight logic ──
    weak_against = []
    for pair in ['eurinr', 'gbpinr', 'jpyinr', 'cnhinr']:
        if data.get(f'{pair}_wow_val', 0) > 0:
            weak_against.append(pair.replace('inr','').upper())
    data['inr_weak_against'] = weak_against
    dxy_wow_val = data.get('dxy_wow_val', 0)
    usdinr_wow_val = data.get('usdinr_wow_val', 0)
    if len(weak_against) == 4 and usdinr_wow_val > 0 and dxy_wow_val < -0.5:
        data['inr_insight'] = (
            f"INR weakened against the full G3 basket this week — <strong>not a pure USD-strength story</strong>. "
            f"DXY fell {abs(dxy_wow_val):.1f}% WoW yet INR did not recover vs EUR or GBP. "
            f"India-specific pressures (oil import bill, FPI hedging costs, yield rise) are independently weighing on INR."
        )
    elif usdinr_wow_val > 0.3:
        data['inr_insight'] = (
            f"INR under pressure vs USD ({usdinr_wow_val:+.2f}% WoW). "
            f"G3 moves: {'weaker vs all' if len(weak_against)==4 else f'weaker vs {', '.join(weak_against)}' if weak_against else 'mixed'}. "
            f"Watch DXY direction and oil prices for the path next week."
        )
    else:
        data['inr_insight'] = (
            f"INR broadly stable vs USD ({usdinr_wow_val:+.2f}% WoW) with mixed G3 moves this week. "
            f"No dominant directional bias. Monitor macro data for next week's direction."
        )

    # ── Yields ──
    us_close = safe_close(cur['us10y'])
    us_prior  = safe_close(prv['us10y'])
    in_close  = safe_close(cur['in10y'])
    in_prior  = safe_close(prv['in10y'])
    us_lo52, us_hi52 = get_52w('^TNX')
    in_lo52, in_hi52 = get_52w('^IN10YT=RR')

    data['us10y_close']   = round(us_close, 2) if us_close else 'N/A'
    data['us10y_wow']     = fmt_chg(bps_change(us_close, us_prior), unit='bps') if us_close else 'N/A'
    data['us10y_wow_val'] = bps_change(us_close, us_prior) if us_close else 0
    data['us10y_52w_lo']  = round(us_lo52, 2) if us_lo52 else 'N/A'
    data['us10y_52w_hi']  = round(us_hi52, 2) if us_hi52 else 'N/A'
    data['us10y_52w_pct'] = range_pct(us_close, us_lo52, us_hi52) if us_close else 50

    data['in10y_close']   = round(in_close, 2) if in_close else 'N/A'
    data['in10y_wow']     = fmt_chg(bps_change(in_close, in_prior), unit='bps') if in_close else 'N/A'
    data['in10y_wow_val'] = bps_change(in_close, in_prior) if in_close else 0
    data['in10y_52w_lo']  = round(in_lo52, 2) if in_lo52 else 'N/A'
    data['in10y_52w_hi']  = round(in_hi52, 2) if in_hi52 else 'N/A'
    data['in10y_52w_pct'] = range_pct(in_close, in_lo52, in_hi52) if in_close else 50

    # India-US spread
    if us_close and in_close:
        spread = round(in_close - us_close, 2)
        spread_chg = bps_change(in_close - us_close,
                                (in_prior - us_prior) if in_prior and us_prior else None)
        data['yield_spread'] = f"{spread:.2f}% · {spread_chg:+.0f} bps WoW"
    else:
        data['yield_spread'] = 'N/A'

    # ── Brent ──
    b_close = safe_close(cur['brent'])
    b_prior  = safe_close(prv['brent'])
    b_5d     = safe_series(cur['brent'])
    data['brent_close']    = round(b_close, 2) if b_close else 'N/A'
    data['brent_wow']      = fmt_chg(pct_change(b_close, b_prior), invert=True) if b_close else 'N/A'
    data['brent_wow_val']  = pct_change(b_close, b_prior) if b_close else 0
    data['brent_wk_high']  = round(safe_high(cur['brent']), 2) if safe_high(cur['brent']) else b_close
    data['brent_5d']       = [round(v, 2) if v else None for v in b_5d]
    data['usdinr_5d']      = [round(v, 2) if v else None for v in u_5d]

    # ── Gold → MCX proxy ──
    go_close = safe_close(cur['gold'])
    go_prior  = safe_close(prv['gold'])
    if go_close and u_close:
        gold_inr = go_close * u_close / 3.11      # USD/oz → INR/10g
        gold_inr_p = (go_prior * u_prior / 3.11) if go_prior and u_prior else None
        data['gold_inr']     = f"~₹{round(gold_inr / 1000) * 1000:,.0f}"
        data['gold_wow']     = fmt_chg(pct_change(gold_inr, gold_inr_p), invert=True) if gold_inr_p else 'N/A'
        data['gold_wow_val'] = pct_change(gold_inr, gold_inr_p) if gold_inr_p else 0
    else:
        data['gold_inr']     = 'N/A'
        data['gold_wow']     = 'N/A'
        data['gold_wow_val'] = 0

    # ── Static policy rates ──
    data['fed_rate']  = '3.50–3.75%'   # update manually when Fed changes
    data['rbi_rate']  = '5.25%'         # update manually when RBI changes

    # ── INR performance series (% from Monday, INR perspective) ──
    e_5d = safe_series(cur['eurusd'])
    g_5d = safe_series(cur['gbpusd'])
    eurinr_5d = [(e * u) if e and u else None for e, u in zip(e_5d, u_5d)]
    gbpinr_5d = [(g * u) if g and u else None for g, u in zip(g_5d, u_5d)]

    def inr_pct_from_base(series):
        base = next((v for v in series if v is not None), None)
        if not base:
            return [0.0] * 5
        result = []
        for v in series:
            if v is None:
                result.append(result[-1] if result else 0.0)
            else:
                result.append(round(-(v / base - 1) * 100, 3))
        return result

    data['inr_vs_usd'] = inr_pct_from_base(u_5d)
    data['inr_vs_eur'] = inr_pct_from_base(eurinr_5d)
    data['inr_vs_gbp'] = inr_pct_from_base(gbpinr_5d)

    return data


# ── Daily data fetch ──────────────────────────────────────────────────────────

def get_daily_data():
    """
    Fetch all market data for the daily snapshot (last 24 hours).
    Returns a dict with all values needed by the HTML generator.
    """
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    two_days_ago = today - timedelta(days=2)

    data = {
        'mode': 'daily',
        'date': today.strftime('%A, %d %b %Y'),
        'generated_at': today.strftime('%d %b %Y, %H:%M IST'),
    }

    tickers = {
        'usdinr': 'USDINR=X',
        'eurusd': 'EURUSD=X',
        'gbpusd': 'GBPUSD=X',
        'usdjpy': 'USDJPY=X',
        'usdcnh': 'USDCNH=X',
        'dxy':    'DX-Y.NYB',
        'us10y':  '^TNX',
        'in10y':  '^IN10YT=RR',
        'brent':  'BZ=F',
        'gold':   'GC=F',
    }

    # For daily: fetch 3 days back to ensure we get today and yesterday
    cur = {k: fetch(v, two_days_ago, today, interval='1d') for k, v in tickers.items()}

    def today_close(df):
        return safe_close(df, -1)

    def yesterday_close(df):
        return safe_close(df, -2)

    u_now  = today_close(cur['usdinr'])
    u_prev = yesterday_close(cur['usdinr'])
    e_now  = today_close(cur['eurusd'])
    g_now  = today_close(cur['gbpusd'])
    j_now  = today_close(cur['usdjpy'])
    c_now  = today_close(cur['usdcnh'])
    e_prev = yesterday_close(cur['eurusd'])
    g_prev = yesterday_close(cur['gbpusd'])
    j_prev = yesterday_close(cur['usdjpy'])
    c_prev = yesterday_close(cur['usdcnh'])

    data['usdinr_close']   = round(u_now, 2) if u_now else 'N/A'
    data['usdinr_chg']     = fmt_chg(pct_change(u_now, u_prev)) if u_now else 'N/A'
    data['usdinr_chg_val'] = pct_change(u_now, u_prev) if u_now else 0
    data['rbi_ref']        = round(u_now - 0.28, 4) if u_now else 'N/A'

    lo52, hi52 = get_52w('USDINR=X')
    data['usdinr_52w_lo']  = round(lo52, 2) if lo52 else 'N/A'
    data['usdinr_52w_hi']  = round(hi52, 2) if hi52 else 'N/A'
    data['usdinr_52w_pct'] = range_pct(u_now, lo52, hi52) if u_now else 50

    # Cross rates
    for key, num, num_p, mult in [
        ('eurinr', e_now,  e_prev,  True),
        ('gbpinr', g_now,  g_prev,  True),
        ('jpyinr', j_now,  j_prev,  False),
        ('cnhinr', c_now,  c_prev,  False),
    ]:
        if num and u_now:
            val  = round((num * u_now  if mult else u_now  / num)  * (100 if key == 'jpyinr' else 1), 2)
            val_p = round((num_p * u_prev if mult else u_prev / num_p) * (100 if key == 'jpyinr' else 1), 2) \
                    if num_p and u_prev else None
        else:
            val = None; val_p = None
        data[f'{key}_close']   = val if val else 'N/A'
        data[f'{key}_chg']     = fmt_chg(pct_change(val, val_p)) if val else 'N/A'
        data[f'{key}_chg_val'] = pct_change(val, val_p) if val else 0

    d_now  = today_close(cur['dxy'])
    d_prev = yesterday_close(cur['dxy'])
    data['dxy_close']   = round(d_now, 2) if d_now else 'N/A'
    data['dxy_chg']     = fmt_chg(pct_change(d_now, d_prev), invert=True) if d_now else 'N/A'
    data['dxy_chg_val'] = pct_change(d_now, d_prev) if d_now else 0

    us_now  = today_close(cur['us10y'])
    us_prev = yesterday_close(cur['us10y'])
    in_now  = today_close(cur['in10y'])
    in_prev = yesterday_close(cur['in10y'])
    data['us10y_close']   = round(us_now, 2) if us_now else 'N/A'
    data['us10y_chg']     = fmt_chg(bps_change(us_now, us_prev), unit='bps') if us_now else 'N/A'
    data['in10y_close']   = round(in_now, 2) if in_now else 'N/A'
    data['in10y_chg']     = fmt_chg(bps_change(in_now, in_prev), unit='bps') if in_now else 'N/A'
    data['yield_spread']  = f"{round(in_now - us_now, 2):.2f}%" if us_now and in_now else 'N/A'

    b_now  = today_close(cur['brent'])
    b_prev = yesterday_close(cur['brent'])
    data['brent_close']   = round(b_now, 2) if b_now else 'N/A'
    data['brent_chg']     = fmt_chg(pct_change(b_now, b_prev), invert=True) if b_now else 'N/A'
    data['brent_chg_val'] = pct_change(b_now, b_prev) if b_now else 0

    go_now  = today_close(cur['gold'])
    go_prev = yesterday_close(cur['gold'])
    if go_now and u_now:
        gold_inr   = go_now  * u_now  / 3.11
        gold_inr_p = go_prev * u_prev / 3.11 if go_prev and u_prev else None
        data['gold_inr'] = f"~₹{round(gold_inr / 1000) * 1000:,.0f}"
        data['gold_chg'] = fmt_chg(pct_change(gold_inr, gold_inr_p), invert=True)
    else:
        data['gold_inr'] = 'N/A'; data['gold_chg'] = 'N/A'

    data['fed_rate'] = '3.50–3.75%'
    data['rbi_rate'] = '5.25%'

    return data
