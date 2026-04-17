"""
app.py — SCB Corporate Actions Intelligence  v5
------------------------------------------------
Changes:
  - Grouped by MNC parent (highest score leads, others collapse)
  - NEW flag (first_seen within 7 days AND event_date within 30 days)
  - Bigger dates, better readability
  - Google News fallback link for all items
  - Batch runs AFTER main feed loads (non-blocking)
  - INR filter applied upstream in fetcher
"""

import streamlit as st
import pandas as pd
import re
import datetime
import urllib.parse
from datetime import datetime as dt, timedelta
from streamlit_autorefresh import st_autorefresh

from client_registry import load_registry
from corporate_fetcher import fetch_all_corporate_actions, LOOKBACK_DAYS, LOOKAHEAD_DAYS
from groq_engine import fx_implication, daily_briefing, make_snapshot, GROQ_API_KEY
from batch_manager import run_next_batch, get_progress, load_cache
from deep_dive import run_deep_dive
from token_tracker import get_status as get_token_status

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SCB — Corporate Actions Intelligence",
    page_icon="🏦",
    layout="wide",
)
st_autorefresh(interval=30 * 60 * 1000, key="corp_refresh")

# ─── Styling ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .hdr{background:#002f6c;color:#fff;padding:14px 20px;border-radius:8px;margin-bottom:4px;}

  /* Urgency cards */
  .urgency-critical{background:#1a0505;border:1px solid #c62828;
    border-left:5px solid #ef5350;border-radius:10px;padding:14px 18px;margin:6px 0;
    animation:pulse-r 2.5s ease-in-out infinite;}
  .urgency-high{background:#1a0e05;border:1px solid #bf360c;
    border-left:5px solid #ff6d00;border-radius:10px;padding:14px 18px;margin:6px 0;}
  .urgency-medium{background:#06111a;border:1px solid #01579b;
    border-left:5px solid #0288d1;border-radius:10px;padding:14px 18px;margin:6px 0;}
  .urgency-low{background:#111;border:1px solid #1a1a1a;
    border-left:5px solid #2a2a2a;border-radius:10px;padding:10px 14px;margin:4px 0;}
  @keyframes pulse-r{
    0%,100%{border-left-color:#ef5350;}
    50%{border-left-color:#ff8a80;box-shadow:0 0 10px 2px rgba(239,83,80,.15);}
  }

  /* Urgency labels */
  .u-critical{background:#b71c1c;color:#ffcdd2;padding:3px 10px;
    border-radius:999px;font-size:12px;font-weight:700;letter-spacing:.05em;}
  .u-high{background:#bf360c;color:#ffccbc;padding:3px 10px;
    border-radius:999px;font-size:12px;font-weight:600;}
  .u-medium{background:#01579b;color:#b3e5fc;padding:3px 10px;
    border-radius:999px;font-size:12px;font-weight:600;}
  .u-low{background:#212121;color:#555;padding:3px 10px;
    border-radius:999px;font-size:12px;}

  /* Action pills */
  .pill{display:inline-block;padding:3px 10px;border-radius:999px;
    font-size:11px;font-weight:600;margin-right:4px;}
  .p-div{background:#1a3d1a;color:#81c784;}
  .p-divsp{background:#0d3320;color:#a5d6a7;border:1px solid #2e7d32;}
  .p-ma{background:#3d1a1a;color:#ef9a9a;}
  .p-fdi{background:#1a2d3d;color:#90caf9;}
  .p-buy{background:#3d2a1a;color:#ffcc80;}
  .p-strat{background:#2d2a1a;color:#fff176;}
  .p-split{background:#222;color:#888;}
  .p-ipo{background:#1a1a3d;color:#b39ddb;}

  /* Badges */
  .client-badge{background:#0d2137;border:1px solid #1976d2;color:#64b5f6;
    padding:2px 9px;border-radius:999px;font-size:11px;font-weight:600;}
  .non-cl-badge{background:#1e1e1e;border:1px solid #333;color:#555;
    padding:2px 9px;border-radius:999px;font-size:11px;}
  .new-badge{background:#1b5e20;color:#a5d6a7;padding:2px 9px;
    border-radius:999px;font-size:11px;font-weight:700;letter-spacing:.06em;
    animation:pulse-g 2s ease-in-out infinite;}
  @keyframes pulse-g{0%,100%{opacity:1;}50%{opacity:.7;}}
  .unver-badge{background:#1a1a10;border:1px solid #444;color:#777;
    padding:1px 7px;border-radius:999px;font-size:10px;font-style:italic;}

  /* Date — large and prominent */
  .event-date{font-size:15px;font-weight:600;color:#90a4ae;letter-spacing:.03em;
    margin-bottom:4px;}
  .event-date-rel{font-size:11px;color:#546e7a;margin-left:6px;}

  /* Headline */
  .headline{font-size:15px;font-weight:500;color:#eceff1;margin:6px 0 5px;
    line-height:1.45;}

  /* FX line */
  .fx-line{background:#06111a;border-left:2px solid #0288d1;padding:7px 12px;
    border-radius:0 6px 6px 0;font-size:13px;color:#90caf9;margin-top:8px;
    line-height:1.5;}

  /* Source link */
  .src-link{font-size:11px;color:#37474f;text-decoration:none;}
  .src-link:hover{color:#64b5f6;}

  /* Sub-events (grouped below lead) */
  .sub-event{background:#0d0d0d;border-left:2px solid #1a1a1a;
    border-radius:0 6px 6px 0;padding:8px 12px;margin-top:6px;}
  .sub-headline{font-size:13px;color:#9e9e9e;line-height:1.4;}
  .sub-date{font-size:11px;color:#424242;margin-bottom:2px;}

  /* Counters */
  .counter-bar{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;}
  .cc{border-radius:8px;padding:10px 14px;text-align:center;flex:1;min-width:70px;}
  .cc-critical{background:#1a0505;border:1px solid #c62828;}
  .cc-high{background:#1a0e05;border:1px solid #bf360c;}
  .cc-medium{background:#06111a;border:1px solid #01579b;}
  .cc-low{background:#111;border:1px solid #222;}
  .cc-nc{background:#0a0a0a;border:1px solid #1a1a1a;}
  .cc-num{font-size:22px;font-weight:500;}
  .cc-lbl{font-size:10px;opacity:.6;margin-top:2px;}

  /* Non-client box */
  .nc-box{background:#0a0a0a;border:1px solid #1e1e1e;border-radius:8px;
    padding:12px 14px;}
  .nc-item{padding:7px 0;border-bottom:1px solid #141414;}
  .nc-item:last-child{border-bottom:none;}

  /* Score chip */
  .score-chip{font-size:11px;font-weight:600;padding:2px 8px;border-radius:999px;}

  /* Deep dive */
  .dd-event{border-radius:8px;padding:12px 14px;margin-bottom:8px;border:1px solid #1a1a1a;}
  .dd-high{border-left:3px solid #ef5350;background:#1a0505;}
  .dd-medium{border-left:3px solid #ff6d00;background:#1a0e05;}
  .dd-low{border-left:3px solid #2a2a2a;background:#0a0a0a;}
</style>
""", unsafe_allow_html=True)


# ─── Scoring ─────────────────────────────────────────────────────────────────

def is_special_div(a):
    h   = (a.get("headline","") + " " + a.get("raw_detail","")).lower()
    amt = a.get("amount") or 0
    return (any(w in h for w in ["special","extraordinary","one-time","interim",
                                  "repatriat","bumper","enhanced"])
            or amt >= 15)

ACTION_SCORES = {
    "Dividend_Special":30,"M&A":30,"FDI":28,"Dividend":15,
    "Buyback":20,"Strategic":10,"IPO":20,"Stock Split":5,"Other":3,
}

def score_action(a):
    total = 40 if a.get("is_scb_client") else 0
    atype = a.get("action_type","Other")
    akey  = "Dividend_Special" if atype=="Dividend" and is_special_div(a) else atype
    total += ACTION_SCORES.get(akey, 3)

    # Exposure
    exp = (a.get("client") or {}).get("net_nih_exposure") or 0
    if exp >= 1000:   total += 20
    elif exp >= 500:  total += 12
    elif exp >= 100:  total += 6
    elif exp > 0:     total += 2

    # Non-client significant deal boost
    if not a.get("is_scb_client") and atype in ("M&A","FDI","IPO"):
        sig = a.get("_significance","")
        if sig == "High":   total += 15
        elif sig == "Medium": total += 8

    # Boost: confirmed Indian subsidiary dividend (NSE RSS or yfinance)
    # These are always genuine repatriation events
    source = a.get("source","")
    if atype in ("Dividend","Dividend_Special") and any(
            s in source for s in ["NSE","yfinance"]):
        total += 10

    # Boost: SEBI open offer trigger
    if a.get("_sebi_open_offer"):
        total += 15

    # Penalty: M&A from news source with no India keyword in headline
    # Secondary safety net on top of Groq filter
    if atype == "M&A" and "google" in source.lower():
        headline_lower = a.get("headline","").lower()
        if not any(w in headline_lower for w in
                   ["india","indian","nse","bse","mumbai","delhi","bengaluru",
                    "hyderabad","pune","chennai","open offer","sebi"]):
            total -= 20

    # Recency scoring
    try:
        delta = (datetime.date.today() -
                 datetime.date.fromisoformat(a.get("date","")[:10])).days
        if delta <= 1:    total += 10
        elif delta <= 3:  total += 7
        elif delta <= 7:  total += 4
        elif delta <= 30: total += 0
        # Score decay for old events — dividends older than 90 days
        # should not lead groups over recent events
        if atype in ("Dividend","Dividend_Special","Stock Split") and delta > 90:
            total -= 15
        elif delta > 180:
            total -= 10
    except Exception:
        pass

    return max(0, total)   # floor at 0

def urgency(score):
    if score >= 70: return "critical"
    if score >= 50: return "high"
    if score >= 35: return "medium"
    return "low"

MINIMUM_SCORE  = 25
NON_CLIENT_MIN = 35


# ─── NEW flag ─────────────────────────────────────────────────────────────────

def is_new(action: dict) -> bool:
    """
    True if:
      - first_seen within last 7 days (entered our system recently)
      - AND event_date within last 30 days (actual event is recent, not old news)
    """
    try:
        first = action.get("_first_seen","")
        if first:
            days_since_first = (datetime.date.today() -
                                datetime.date.fromisoformat(str(first)[:10])).days
            if days_since_first > 7:
                return False

        # Use Groq-extracted event date if available, else article date
        ev_date_str = action.get("_event_date") or action.get("date","")
        if ev_date_str:
            days_since_event = (datetime.date.today() -
                                datetime.date.fromisoformat(str(ev_date_str)[:10])).days
            return days_since_event <= 30
    except Exception:
        pass
    return False


# ─── Source link helper ───────────────────────────────────────────────────────

def source_link(action: dict) -> str:
    """Return a usable URL — real article URL or Google News search fallback."""
    url = action.get("url","").strip()
    if url and url.startswith("http") and len(url) > 15:
        return url
    # Build Google News search fallback
    query = action.get("headline","")[:80]
    if not query:
        query = action.get("company_name","") + " corporate action India"
    enc = urllib.parse.quote_plus(query)
    return f"https://news.google.com/search?q={enc}&hl=en-IN&gl=IN"

def source_label(action: dict) -> str:
    s = action.get("source","").split("—")[0].strip()[:20]
    colors = {"NSE":"#1565c0","yfinance":"#2e7d32","FMP":"#6a1b9a",
              "Google":"#0277bd","Groq":"#534AB7","News":"#e65100"}
    c = next((v for k,v in colors.items() if k in s), "#444")
    return f'<span style="font-size:11px;font-weight:600;color:{c};">{s}</span>'


# ─── Date display helper ──────────────────────────────────────────────────────

def format_date(date_str: str) -> str:
    """Return a large readable date with relative label."""
    try:
        d     = datetime.date.fromisoformat(str(date_str)[:10])
        delta = (datetime.date.today() - d).days
        nice  = d.strftime("%-d %b %Y")   # e.g. "16 Apr 2026"
        if delta == 0:   rel = "today"
        elif delta == 1: rel = "yesterday"
        elif delta < 0:  rel = f"in {abs(delta)}d"
        elif delta < 7:  rel = f"{delta}d ago"
        elif delta < 30: rel = f"{delta//7}w ago"
        else:            rel = f"{delta//30}mo ago"
        return nice, rel
    except Exception:
        return str(date_str)[:10], ""


# ─── UI helpers ──────────────────────────────────────────────────────────────

def action_pill(a):
    atype = a.get("action_type","Other")
    sp    = atype=="Dividend" and is_special_div(a)
    MAP   = {
        "Dividend":   ("p-div",   "Dividend"),
        "M&A":        ("p-ma",    "M&A"),
        "FDI":        ("p-fdi",   "FDI"),
        "Buyback":    ("p-buy",   "Buyback"),
        "Strategic":  ("p-strat", "Strategic"),
        "Stock Split": ("p-split", "Split"),
        "IPO":        ("p-ipo",   "IPO"),
        "Other":      ("p-split", "News"),
    }
    cls, lbl = MAP.get(atype, ("p-split", atype))
    if sp: cls, lbl = "p-divsp", "Special dividend"
    return f'<span class="pill {cls}">{lbl}</span>'

def urgency_pill(score):
    u   = urgency(score)
    MAP = {"critical":("u-critical","CRITICAL"),
           "high":("u-high","HIGH"),
           "medium":("u-medium","MEDIUM"),
           "low":("u-low","LOW")}
    cls, lbl = MAP[u]
    return f'<span class="{cls}">{lbl}</span>'

def sc_chip(score):
    u  = urgency(score)
    c  = {"critical":"#ef5350","high":"#ff6d00","medium":"#0288d1","low":"#444"}[u]
    return (f'<span class="score-chip" '
            f'style="background:{c}18;color:{c};border:1px solid {c}44;">'
            f'{score}</span>')


# ─── Group actions by MNC parent ─────────────────────────────────────────────

def group_by_mnc(actions: list) -> list:
    """
    Returns list of groups, each group = {
      "mnc_parent": str,
      "lead":       action dict (highest score),
      "others":     [remaining action dicts sorted by score desc]
    }
    Groups sorted by lead score desc.
    Actions without a client go in their own single-item groups.
    """
    from collections import defaultdict
    buckets = defaultdict(list)

    for a in actions:
        client = a.get("client") or {}
        key    = client.get("client_group","") or a.get("company_name","Unknown")
        buckets[key].append(a)

    groups = []
    for mnc, items in buckets.items():
        items_sorted = sorted(items, key=lambda x: x["_score"], reverse=True)
        groups.append({
            "mnc_parent": mnc,
            "lead":       items_sorted[0],
            "others":     items_sorted[1:],
        })

    groups.sort(key=lambda g: g["lead"]["_score"], reverse=True)
    return groups


# ─── Card renderer ────────────────────────────────────────────────────────────

def render_group(group: dict):
    lead      = group["lead"]
    others    = group["others"]
    score     = lead["_score"]
    u         = lead["_urgency"]
    client    = lead.get("client") or {}
    sp_div    = lead["action_type"]=="Dividend" and is_special_div(lead)
    new_flag  = is_new(lead)
    low_conf  = lead.get("_groq_confidence") == "low"

    nice_date, rel = format_date(lead.get("date",""))

    # Client info
    if client:
        client_info = (
            f'<strong style="color:#eceff1;">{client.get("indian_subsidiary","")}</strong>'
            f' &nbsp;→&nbsp; <span style="color:#64b5f6;">{client.get("client_group","")}</span>'
            f' &nbsp;·&nbsp; <strong style="color:#a5d6a7;">'
            f'${client.get("net_nih_exposure",0):,.0f}M</strong>'
        )
    else:
        client_info = f'<span style="color:#555;">{lead.get("company_name","")}</span>'

    # Amount
    amt_str = ""
    if lead.get("amount") and lead.get("currency")=="INR":
        amt_str = f' &nbsp;·&nbsp; <strong style="color:#a5d6a7;">₹{lead["amount"]:,.2f}/sh</strong>'
    elif lead.get("amount") and lead.get("currency")=="USD":
        amt_str = f' &nbsp;·&nbsp; <strong style="color:#90caf9;">${lead["amount"]:,.0f}M</strong>'

    # Foreign entity
    fe_str = (f' &nbsp;·&nbsp; <span style="color:#ffcc80;">↔ {lead["foreign_entity"]}</span>'
              if lead.get("foreign_entity") else "")

    # Client/non-client badge
    cl_badge = ('<span class="client-badge">Current client</span>'
                if lead["is_scb_client"] else
                '<span class="non-cl-badge">Non-client</span>')

    # New badge
    new_html  = '<span class="new-badge">NEW</span> ' if new_flag else ""
    unver_html = '<span class="unver-badge">unverified</span> ' if low_conf else ""

    # Source link
    link = source_link(lead)
    link_html = f'<a href="{link}" target="_blank" class="src-link">📰 {source_label(lead)} →</a>'

    # Others count
    others_label = f" +{len(others)} more" if others else ""

    # FX implication for high/critical SCB clients
    fx_html = ""
    if lead["is_scb_client"] and score >= 50 and GROQ_API_KEY and client:
        amt_display = (f"₹{lead['amount']:.2f}/share"
                       if lead.get("amount") and lead.get("currency")=="INR"
                       else f"${lead['amount']:.0f}M" if lead.get("amount") else "")
        impl = fx_implication(
            lead["headline"], lead["action_type"],
            client.get("indian_subsidiary",""),
            client.get("client_group",""),
            amt_display,
            float(client.get("net_nih_exposure",0) or 0),
        )
        if impl:
            fx_html = f'<div class="fx-line">FX → {impl}</div>'

    # Sub-events HTML
    sub_html = ""
    for o in others:
        o_nice, o_rel = format_date(o.get("date",""))
        o_link = source_link(o)
        sub_html += f"""
        <div class="sub-event">
          <div class="sub-date">{o_nice}
            {f'<span style="font-size:10px;color:#424242;">· {o_rel}</span>' if o_rel else ""}
          </div>
          <div class="sub-headline">
            {action_pill(o)}
            {o['headline'][:160]}
            &nbsp;
            <a href="{o_link}" target="_blank" class="src-link">→</a>
          </div>
        </div>
        """

    # Title for expander
    exp_title = (
        f"{'★ ' if u=='critical' else ''}"
        f"{group['mnc_parent'][:40]}"
        f" · {lead['action_type']}{'★' if sp_div else ''}"
        f"{others_label}"
    )

    with st.expander(exp_title,
                     expanded=(u in ("critical","high") and lead["is_scb_client"])):
        st.markdown(f"""
        <div class="urgency-{u}">
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:8px;">
            {urgency_pill(score)} {action_pill(lead)}
            {cl_badge} {sc_chip(score)} {new_html}{unver_html}
          </div>

          <div class="event-date">
            {nice_date}
            {f'<span class="event-date-rel">({rel})</span>' if rel else ""}
          </div>

          <div class="headline">{lead['headline'][:220]}</div>

          <div style="font-size:12px;color:#78909c;margin-top:3px;">
            {client_info}{amt_str}{fe_str}
          </div>

          {fx_html}

          <div style="margin-top:8px;display:flex;align-items:center;gap:10px;">
            {link_html}
            {f"<span style='font-size:11px;color:#37474f;'>· {lead.get('raw_detail','')[:100]}</span>" if lead.get('raw_detail') else ""}
          </div>

          {sub_html}
        </div>
        """, unsafe_allow_html=True)


# ─── Load registry ────────────────────────────────────────────────────────────

st.markdown("""
<div class="hdr">
  <strong style="font-size:18px;">🏦 SCB — Corporate Actions Intelligence</strong><br>
  <span style="font-size:12px;opacity:0.8;">
    MNC subsidiaries · SCB FX Pipeline v7 · INR-relevant events only
  </span>
</div>
""", unsafe_allow_html=True)

with st.spinner("Loading registry..."):
    registry = load_registry()

tab_live, tab_dive = st.tabs(["📡  Live Monitor", "🔍  Client Deep Dive"])


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1 — LIVE MONITOR
# ═══════════════════════════════════════════════════════════════════════════
with tab_live:

    # Stats row + token tracker top-right
    c1,c2,c3,c4 = st.columns([2,2,2,2])
    with c1: st.metric("Monitored", len(registry["all"]))
    with c2: st.metric("Tickers",   len(registry["by_ticker"]))
    with c3: st.metric("Window",
        f"–{LOOKBACK_DAYS}d / +{LOOKAHEAD_DAYS}d",
        f"{(dt.now()-timedelta(days=LOOKBACK_DAYS)).strftime('%d %b')} → "
        f"{(dt.now()+timedelta(days=LOOKAHEAD_DAYS)).strftime('%d %b')}")
    with c4:
        tok     = get_token_status()
        used    = tok["total_used"]
        budget  = tok["total_budget"]
        pct     = tok["pct"]
        ws_cl   = tok["web_search_clients"]
        reset   = tok["ist_reset"]
        at_lim  = tok["at_limit"]
        bar_col = "#d32f2f" if at_lim else ("#BA7517" if pct > 70 else "#1D9E75")
        st.markdown(
            f'<div style="text-align:right;padding-top:2px;">'
            f'<div style="font-size:11px;color:#546e7a;">Groq tokens today</div>'
            f'<div style="font-size:15px;font-weight:500;color:{bar_col};">'
            f'{used:,} <span style="font-size:11px;color:#37474f;">/ {budget:,}</span></div>'
            f'<div style="background:#1a1a1a;border-radius:3px;height:4px;margin:3px 0;">'
            f'<div style="width:{min(pct,100)}%;height:4px;border-radius:3px;'
            f'background:{bar_col};transition:width .4s;"></div></div>'
            f'<div style="font-size:10px;color:#37474f;">'
            f'{ws_cl} web searches · resets {reset}</div>'
            f'{"<div style=\"font-size:10px;color:#d32f2f;font-weight:600;\">⚠ Token limit reached — web search paused</div>" if at_lim else ""}'
            f'</div>', unsafe_allow_html=True)

    ref_col, _ = st.columns([1,5])
    with ref_col:
        if st.button("⟳ Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    st.divider()

    # ── Fetch main feed FIRST (user sees dashboard immediately) ───────────────
    with st.spinner("Scanning sources..."):
        raw, signal_clients = fetch_all_corporate_actions(registry)

    for a in raw:
        a["_score"]   = score_action(a)
        a["_urgency"] = urgency(a["_score"])

    client_actions = sorted(
        [a for a in raw if a["is_scb_client"] and a["_score"] >= MINIMUM_SCORE],
        key=lambda x: x["_score"], reverse=True)
    non_client_actions = sorted(
        [a for a in raw if not a["is_scb_client"]
         and a["_score"] >= NON_CLIENT_MIN
         and a["action_type"] not in ("Other","Stock Split")],
        key=lambda x: x["_score"], reverse=True)

    critical = [a for a in client_actions if a["_urgency"]=="critical"]
    high     = [a for a in client_actions if a["_urgency"]=="high"]
    medium   = [a for a in client_actions if a["_urgency"]=="medium"]
    low      = [a for a in client_actions if a["_urgency"]=="low"]

    # Counter bar
    st.markdown(f"""
    <div class="counter-bar">
      <div class="cc cc-critical">
        <div class="cc-num" style="color:#ef5350;">{len(critical)}</div>
        <div class="cc-lbl" style="color:#ef9a9a;">Critical</div>
      </div>
      <div class="cc cc-high">
        <div class="cc-num" style="color:#ff6d00;">{len(high)}</div>
        <div class="cc-lbl" style="color:#ffcc80;">High</div>
      </div>
      <div class="cc cc-medium">
        <div class="cc-num" style="color:#0288d1;">{len(medium)}</div>
        <div class="cc-lbl" style="color:#b3e5fc;">Medium</div>
      </div>
      <div class="cc cc-low">
        <div class="cc-num" style="color:#555;">{len(low)}</div>
        <div class="cc-lbl" style="color:#444;">Low</div>
      </div>
      <div class="cc cc-nc">
        <div class="cc-num" style="color:#444;">{len(non_client_actions)}</div>
        <div class="cc-lbl" style="color:#2a2a2a;">Non-pipeline</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # AI briefing
    snapshot = make_snapshot(client_actions)
    if GROQ_API_KEY and snapshot:
        st.markdown("""
        <div style="background:#0a1628;border:1px solid #1e3a5f;border-radius:10px;
                    padding:14px 18px;margin-bottom:12px;">
          <div style="font-size:11px;font-weight:600;color:#64b5f6;
                      letter-spacing:.06em;margin-bottom:8px;">
            ◆ AI DAILY BRIEFING — FX DESK
          </div>
        """, unsafe_allow_html=True)
        with st.spinner("Generating briefing..."):
            brief = daily_briefing(snapshot)
        if brief:
            for line in brief.split("\n"):
                line = line.strip()
                if not line: continue
                line = re.sub(r'\*\*(.+?)\*\*',
                    r'<strong style="color:#eceff1;">\1</strong>', line)
                color = "#b0bec5" if line.startswith(("•","-")) else "#546e7a"
                pad   = "padding:3px 0 3px 4px;" if line.startswith(("•","-")) else ""
                st.markdown(
                    f'<div style="font-size:13px;color:{color};line-height:1.8;{pad}">'
                    f'{line}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-size:10px;color:#263238;margin-top:8px;">'
            f'Groq / Llama 3 &nbsp;·&nbsp; {len(snapshot)} signals &nbsp;·&nbsp; '
            f'Cached 30 min</div></div>', unsafe_allow_html=True)

    st.divider()

    # Filters
    fc1,fc2,fc3 = st.columns([2,2,2])
    with fc1:
        f_type = st.selectbox("Action type",
            ["All"] + sorted({a["action_type"] for a in client_actions}))
    with fc2:
        f_urg  = st.selectbox("Min urgency",
            ["All","Medium+","High+","Critical only"])
    with fc3:
        new_only = st.toggle("NEW only", value=False,
                             help="Show only events flagged as new this week")

    def apply_f(lst):
        if f_type != "All":  lst = [a for a in lst if a["action_type"]==f_type]
        if f_urg  == "Medium+":
            lst = [a for a in lst if a["_urgency"] in ("critical","high","medium")]
        elif f_urg == "High+":
            lst = [a for a in lst if a["_urgency"] in ("critical","high")]
        elif f_urg == "Critical only":
            lst = [a for a in lst if a["_urgency"]=="critical"]
        if new_only:
            lst = [a for a in lst if is_new(a)]
        return lst

    filtered = apply_f(client_actions)
    st.caption(
        f"**{len(filtered)} current client actions** · "
        f"{len(non_client_actions)} non-pipeline · "
        f"{sum(1 for a in filtered if is_new(a))} new this week"
    )

    # Main columns
    col_feed, col_right = st.columns([3,1], gap="large")

    with col_feed:
        if not filtered:
            st.info("No actions match filters. Try adjusting or refreshing.")
        else:
            groups = group_by_mnc(filtered)
            for grp in groups[:50]:
                render_group(grp)

        # Non-client box
        if non_client_actions:
            st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
            with st.expander(
                f"🔭  Non-pipeline companies with significant activity  "
                f"({len(non_client_actions)} found) — consider adding to Excel",
                expanded=False
            ):
                st.markdown('<div class="nc-box">', unsafe_allow_html=True)
                for a in non_client_actions[:20]:
                    nice_date, rel = format_date(a.get("date",""))
                    link = source_link(a)
                    sig_color = {"M&A":"#ef9a9a","FDI":"#90caf9","IPO":"#b39ddb",
                                 "Buyback":"#ffcc80","Strategic":"#fff176"}.get(
                                 a["action_type"],"#666")
                    amt_str = ""
                    if a.get("amount"):
                        sym = "₹" if a.get("currency")=="INR" else "$"
                        amt_str = f' · {sym}{a["amount"]:,.0f}'
                    fe_str = (f' · <span style="color:#ffcc80;">{a["foreign_entity"]}</span>'
                              if a.get("foreign_entity") else "")
                    new_html = '<span class="new-badge" style="font-size:9px;padding:1px 5px;">NEW</span> ' if is_new(a) else ""
                    st.markdown(f"""
                    <div class="nc-item">
                      <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">
                        <span style="font-size:12px;font-weight:600;color:{sig_color};">{a['action_type']}</span>
                        <span style="font-size:13px;color:#ccc;">{a['company_name'][:50]}</span>
                        {new_html}
                        <span style="font-size:11px;color:#37474f;">{amt_str}{fe_str}</span>
                      </div>
                      <div style="font-size:12px;color:#546e7a;">
                        <strong style="color:#78909c;">{nice_date}</strong>
                        {f'<span style="color:#37474f;"> · {rel}</span>' if rel else ""}
                        &nbsp;·&nbsp; {a['headline'][:110]}
                        &nbsp;<a href="{link}" target="_blank" style="color:#37474f;font-size:11px;">→</a>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

    with col_right:
        st.markdown("**Urgency breakdown**")
        for lbl, grp_list, col in [
            ("Critical (70+)", critical, "#ef5350"),
            ("High (50–69)",   high,     "#ff6d00"),
            ("Medium (35–49)", medium,   "#0288d1"),
            ("Low (25–34)",    low,      "#444"),
        ]:
            if grp_list:
                st.markdown(
                    f'<div style="font-size:12px;color:#90a4ae;margin:3px 0;">'
                    f'{lbl} <strong style="color:{col};">{len(grp_list)}</strong></div>',
                    unsafe_allow_html=True)

        st.divider()
        st.markdown("**Web search**")
        st.progress(prog["pct"] / 100)
        st.markdown(
            f'<div style="font-size:11px;color:#546e7a;">'
            f'{prog["fresh_24h"]}/{prog["total"]} clients (24h)<br>'
            f'{prog["batches_left"]} batches left<br>'
            f'Next in {prog["next_in_mins"]}m</div>',
            unsafe_allow_html=True)

        st.divider()
        st.markdown("**Client highlights**")
        shown_mncs = set()
        for a in filtered[:10]:
            c  = a.get("client") or {}
            mn = c.get("client_group","")
            if mn in shown_mncs: continue
            shown_mncs.add(mn)
            uc = {"critical":"#ef5350","high":"#ff6d00",
                  "medium":"#0288d1","low":"#444"}[a["_urgency"]]
            st.markdown(f"""
            <div style="border:1px solid #1e3a5f;border-left:3px solid {uc};
                        border-radius:6px;padding:8px 10px;margin-bottom:5px;">
              <div style="font-size:11px;font-weight:600;color:#64b5f6;">{mn}</div>
              <div style="font-size:11px;color:#90a4ae;">{c.get('indian_subsidiary','')[:35]}</div>
              <div style="margin-top:4px;display:flex;gap:5px;align-items:center;">
                {action_pill(a)}
                <span style="font-size:10px;color:{uc};font-weight:600;">{a['_score']}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

        st.divider()
        st.markdown("**By type**")
        tc = {}
        for a in filtered:
            k = ("Special div."
                 if a["action_type"]=="Dividend" and is_special_div(a)
                 else a["action_type"])
            tc[k] = tc.get(k,0)+1
        for k,v in sorted(tc.items(),key=lambda x:-x[1]):
            st.markdown(
                f'<div style="font-size:12px;color:#78909c;margin:2px 0;">'
                f'{k} <strong style="color:#eceff1;">{v}</strong></div>',
                unsafe_allow_html=True)

    # Data table
    st.divider()
    with st.expander("📄 Full data table + CSV", expanded=False):
        all_rows = filtered + non_client_actions
        if all_rows:
            rows = [{
                "Score":    a["_score"],
                "Urgency":  a["_urgency"].title(),
                "New":      "✓" if is_new(a) else "",
                "Client":   "Yes" if a["is_scb_client"] else "No",
                "Date":     a.get("date",""),
                "Action":   ("Special div." if a["action_type"]=="Dividend"
                             and is_special_div(a) else a["action_type"]),
                "Company":  a.get("company_name","")[:40],
                "Headline": a.get("headline","")[:80],
                "MNC":      (a.get("client") or {}).get("client_group","—"),
                "NIH $M":   (a.get("client") or {}).get("net_nih_exposure"),
                "Source":   a.get("source","")[:25],
                "Link":     source_link(a),
            } for a in all_rows]
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button("⬇️ CSV",
                df.to_csv(index=False),
                f"scb_{dt.now().strftime('%Y%m%d_%H%M')}.csv","text/csv")

    # ── Run batch AFTER feed is rendered ──────────────────────────────────────
    batch_placeholder = st.empty()
    with batch_placeholder.container():
        batch_status = st.empty()
        batch_status.markdown(
            '<div style="font-size:11px;color:#263238;text-align:right;">'
            'Running web search batch...</div>',
            unsafe_allow_html=True)
    try:
        updated_cache = run_next_batch(registry, signal_clients=signal_clients)
        new_prog      = get_progress(registry, updated_cache)
        batch_status.markdown(
            f'<div style="font-size:11px;color:#1b5e20;text-align:right;">'
            f'✓ Batch complete · {new_prog["fresh_24h"]}/{new_prog["total"]} clients updated</div>',
            unsafe_allow_html=True)
    except Exception as ex:
        batch_status.markdown(
            f'<div style="font-size:11px;color:#37474f;text-align:right;">'
            f'Batch skipped: {str(ex)[:40]}</div>',
            unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2 — CLIENT DEEP DIVE
# ═══════════════════════════════════════════════════════════════════════════
with tab_dive:
    st.markdown("""
    <div style="background:#0a1628;border:1px solid #1e3a5f;border-radius:10px;
                padding:14px 18px;margin-bottom:18px;">
      <strong style="color:#64b5f6;">Client Deep Dive</strong>
      <div style="font-size:12px;color:#546e7a;margin-top:4px;">
        12 months · Google News + ET + BS + Moneycontrol · Groq extracts
        INR-relevant events only
      </div>
    </div>
    """, unsafe_allow_html=True)

    options = [
        (f"{r['indian_subsidiary']}  ({r['client_group']})", r)
        for r in sorted(registry["all"],
                        key=lambda x: x.get("priority_score",0), reverse=True)
        if r.get("indian_subsidiary")
    ]

    dc1, dc2 = st.columns([3,1])
    with dc1:
        sel_label = st.selectbox("Select client", [o[0] for o in options])
    with dc2:
        run_btn = st.button("🔍 Search 12 months", use_container_width=True, type="primary")

    sel_rec = next((r for l,r in options if l==sel_label), None)

    if sel_rec:
        sub  = sel_rec["indian_subsidiary"]
        grp  = sel_rec["client_group"]
        exp  = sel_rec.get("net_nih_exposure",0) or 0
        tier = sel_rec.get("priority_tier","")
        st.markdown(f"""
        <div style="border:1px solid #1e3a5f;border-radius:8px;
                    padding:12px 16px;margin-bottom:16px;background:#06111a;">
          <div style="font-size:14px;font-weight:500;color:#eceff1;">{sub}</div>
          <div style="font-size:12px;color:#64b5f6;">{grp}</div>
          <div style="font-size:11px;color:#37474f;margin-top:4px;">
            NIH: <strong style="color:#a5d6a7;">${exp:,.0f}M</strong>
            &nbsp;·&nbsp; {tier[:25] if tier else '—'}
            &nbsp;·&nbsp; CIN: {sel_rec.get('cin','—')[:25]}
          </div>
          {"<div style='font-size:11px;color:#263238;margin-top:4px;'>Trigger: " + sel_rec.get('event_flag','')[:120] + "</div>" if sel_rec.get('event_flag') else ""}
        </div>
        """, unsafe_allow_html=True)

    if run_btn and sel_rec:
        if not GROQ_API_KEY:
            st.error("GROQ_API_KEY required for deep dive.")
        else:
            with st.spinner(f"Searching 12 months for {sub}..."):
                result = run_deep_dive(grp, sub, exp)

            st.caption(
                f"**{result['query_count']} headlines** · "
                f"**{len(result['events'])} significant events** · "
                f"{result['searched_at']}"
            )

            if not result["events"]:
                st.info("No significant INR-relevant events found.")
            else:
                m1,m2,m3 = st.columns(3)
                with m1: st.metric("Events", len(result["events"]))
                with m2: st.metric("High",
                    sum(1 for e in result["events"] if e.get("significance")=="High"))
                with m3:
                    dates = [e.get("date","") for e in result["events"] if e.get("date")]
                    if dates: st.metric("Range",
                        f"{min(dates)[:7]} → {max(dates)[:7]}")

                st.divider()
                for ev in result["events"]:
                    sig = ev.get("significance","Low")
                    css = {"High":"dd-high","Medium":"dd-medium","Low":"dd-low"}[sig]
                    sc  = {"High":"#ef5350","Medium":"#ff6d00","Low":"#555"}[sig]
                    ev_link = ev.get("source_url","") or (
                        f"https://news.google.com/search?q="
                        f"{urllib.parse.quote_plus(ev.get('headline','')[:60])}"
                        f"&hl=en-IN&gl=IN")
                    nice_d, rel_d = format_date(ev.get("date","")[:10])
                    st.markdown(f"""
                    <div class="dd-event {css}">
                      <div style="font-size:13px;color:{sc};margin-bottom:2px;">
                        <strong>{nice_d}</strong>
                        {f'<span style="font-size:11px;color:#546e7a;"> · {rel_d}</span>' if rel_d else ""}
                        &nbsp;·&nbsp;
                        <span style="font-weight:700;">{sig.upper()}</span>
                        &nbsp;·&nbsp;
                        <span style="background:#1a2d3d;color:#90caf9;font-size:10px;
                                     font-weight:600;padding:1px 7px;border-radius:999px;">
                          {ev.get('action_type','Other')}
                        </span>
                        {"&nbsp;·&nbsp;<span style='color:#ffcc80;font-size:11px;'>" + ev['counterparty'] + "</span>" if ev.get('counterparty') else ""}
                      </div>
                      <div style="font-size:14px;font-weight:500;color:#eceff1;
                                  margin:5px 0 4px;line-height:1.45;">
                        {ev.get('headline','')}
                      </div>
                      {"<div style='font-size:12px;color:#90caf9;'>FX → " + ev['fx_implication'] + "</div>" if ev.get('fx_implication') else ""}
                      <div style="margin-top:6px;">
                        <a href="{ev_link}" target="_blank"
                           style="font-size:11px;color:#37474f;text-decoration:none;">
                           📰 Read source →
                        </a>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

            with st.expander(f"Raw headlines ({result['query_count']})", expanded=False):
                for h in sorted(result["headlines"],
                                key=lambda x: x["date"], reverse=True)[:40]:
                    glink = (f"https://news.google.com/search?q="
                             f"{urllib.parse.quote_plus(h['title'][:60])}&hl=en-IN&gl=IN")
                    actual = h.get("url","")
                    link   = actual if actual.startswith("http") else glink
                    st.markdown(
                        f'<div style="font-size:12px;color:#37474f;padding:3px 0;">'
                        f'<strong style="color:#546e7a;">{h["date"]}</strong>'
                        f'&nbsp; {h["title"]}'
                        f'&nbsp;<a href="{link}" target="_blank" '
                        f'style="color:#263238;font-size:11px;">→</a>'
                        f'</div>', unsafe_allow_html=True)
