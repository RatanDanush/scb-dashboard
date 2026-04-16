"""
app.py — SCB Corporate Actions Intelligence  v4
------------------------------------------------
Tabs: Live Monitor | Client Deep Dive
New: FX implication per card, non-client box, batch progress top-right
"""

import streamlit as st
import pandas as pd
import re
import datetime
from datetime import datetime as dt, timedelta
from streamlit_autorefresh import st_autorefresh

from client_registry import load_registry
from corporate_fetcher import fetch_all_corporate_actions, LOOKBACK_DAYS, LOOKAHEAD_DAYS
from groq_engine import (fx_implication, daily_briefing, make_snapshot, GROQ_API_KEY)
from batch_manager import run_next_batch, get_progress, load_cache
from deep_dive import run_deep_dive

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
  .batch-status{font-size:11px;color:#546e7a;text-align:right;}
  .batch-active{color:#1D9E75;font-weight:600;}

  .urgency-critical{background:#1a0505;border:1px solid #d32f2f;
    border-left:4px solid #f44336;border-radius:8px;padding:12px 16px;margin:4px 0;
    animation:pulse-red 2.5s ease-in-out infinite;}
  .urgency-high{background:#1a0e05;border:1px solid #e65100;
    border-left:4px solid #ff6d00;border-radius:8px;padding:12px 16px;margin:4px 0;}
  .urgency-medium{background:#06111a;border:1px solid #0277bd;
    border-left:4px solid #0288d1;border-radius:8px;padding:12px 16px;margin:4px 0;}
  .urgency-low{background:#111;border:1px solid #222;
    border-left:4px solid #333;border-radius:8px;padding:10px 14px;
    margin:4px 0;opacity:0.85;}

  @keyframes pulse-red{
    0%,100%{border-left-color:#f44336;box-shadow:0 0 0 0 rgba(244,67,54,0);}
    50%{border-left-color:#ff8a80;box-shadow:0 0 8px 2px rgba(244,67,54,0.15);}
  }

  .u-critical{background:#b71c1c;color:#ffcdd2;padding:2px 8px;
    border-radius:999px;font-size:11px;font-weight:700;letter-spacing:.04em;}
  .u-high{background:#bf360c;color:#ffccbc;padding:2px 8px;
    border-radius:999px;font-size:11px;font-weight:600;}
  .u-medium{background:#01579b;color:#b3e5fc;padding:2px 8px;
    border-radius:999px;font-size:11px;font-weight:600;}
  .u-low{background:#212121;color:#666;padding:2px 8px;
    border-radius:999px;font-size:11px;}

  .pill{display:inline-block;padding:2px 9px;border-radius:999px;
    font-size:11px;font-weight:600;margin-right:4px;}
  .p-div{background:#1a3d1a;color:#81c784;}
  .p-divsp{background:#0d3320;color:#a5d6a7;border:1px solid #2e7d32;}
  .p-ma{background:#3d1a1a;color:#ef9a9a;}
  .p-fdi{background:#1a2d3d;color:#90caf9;}
  .p-buy{background:#3d2a1a;color:#ffcc80;}
  .p-strat{background:#2d2a1a;color:#fff176;}
  .p-split{background:#2a2a2a;color:#aaa;}
  .p-ipo{background:#1a1a3d;color:#b39ddb;}
  .p-news{background:#1e1e1e;color:#777;}

  .client-badge{background:#0d2137;border:1px solid #1976d2;color:#64b5f6;
    padding:2px 9px;border-radius:999px;font-size:11px;font-weight:600;}
  .non-client-badge{background:#1e1e1e;border:1px solid #333;color:#555;
    padding:2px 9px;border-radius:999px;font-size:11px;}
  .unverified-badge{background:#1a1a10;border:1px solid #555;color:#888;
    padding:1px 7px;border-radius:999px;font-size:10px;font-style:italic;}
  .new-today{background:#1b5e20;color:#a5d6a7;padding:1px 7px;
    border-radius:999px;font-size:10px;font-weight:700;letter-spacing:.05em;}

  .fx-line{background:#06111a;border-left:2px solid #0288d1;padding:6px 10px;
    border-radius:0 6px 6px 0;font-size:12px;color:#90caf9;
    margin-top:6px;line-height:1.5;}

  .counter-bar{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;}
  .cc{border-radius:8px;padding:10px 12px;text-align:center;flex:1;min-width:70px;}
  .cc-critical{background:#1a0505;border:1px solid #d32f2f;}
  .cc-high{background:#1a0e05;border:1px solid #e65100;}
  .cc-medium{background:#06111a;border:1px solid #0277bd;}
  .cc-low{background:#111;border:1px solid #333;}
  .cc-num{font-size:20px;font-weight:500;}
  .cc-lbl{font-size:10px;opacity:.65;margin-top:1px;}

  .non-client-box{background:#0d0d0d;border:1px solid #2a2a2a;
    border-radius:8px;padding:12px 14px;margin-top:4px;}
  .nc-item{padding:6px 0;border-bottom:1px solid #1a1a1a;font-size:12px;}
  .nc-item:last-child{border-bottom:none;}

  .dd-event{border-radius:8px;padding:12px 14px;margin-bottom:8px;border:1px solid #222;}
  .dd-high{border-left:3px solid #f44336;background:#1a0505;}
  .dd-medium{border-left:3px solid #ff6d00;background:#1a0e05;}
  .dd-low{border-left:3px solid #333;background:#111;}
  .dd-type{display:inline-block;font-size:10px;font-weight:600;padding:1px 7px;
    border-radius:999px;background:#1a2d3d;color:#90caf9;margin-right:4px;}
</style>
""", unsafe_allow_html=True)


# ─── Scoring ─────────────────────────────────────────────────────────────────

def is_special_div(a):
    h   = (a.get("headline","") + " " + a.get("raw_detail","")).lower()
    amt = a.get("amount") or 0
    return any(w in h for w in ["special","extraordinary","one-time","interim",
               "repatriat","bumper","enhanced"]) or amt >= 15

ACTION_SCORES = {
    "Dividend_Special":30,"M&A":30,"FDI":25,"Dividend":15,
    "Buyback":20,"Strategic":10,"IPO":20,"Stock Split":5,"Other":3,
}

def score_action(a):
    total = 40 if a.get("is_scb_client") else 0
    atype = a.get("action_type","Other")
    akey  = "Dividend_Special" if atype=="Dividend" and is_special_div(a) else atype
    total += ACTION_SCORES.get(akey, 3)
    exp = (a.get("client") or {}).get("net_nih_exposure") or 0
    if exp >= 1000:   total += 20
    elif exp >= 500:  total += 12
    elif exp >= 100:  total += 6
    elif exp > 0:     total += 2
    # Non-client significant deal gets a boost
    if not a.get("is_scb_client") and atype in ("M&A","FDI","IPO"):
        sig = a.get("_significance","")
        if sig == "High":   total += 15
        elif sig == "Medium": total += 8
    try:
        delta = (datetime.date.today() -
                 datetime.date.fromisoformat(a.get("date","")[:10])).days
        if delta <= 1:   total += 10
        elif delta <= 3: total += 7
        elif delta <= 7: total += 4
    except Exception:
        pass
    return total

def urgency(score):
    if score >= 70: return "critical"
    if score >= 50: return "high"
    if score >= 35: return "medium"
    return "low"

MINIMUM_SCORE       = 25
NON_CLIENT_MIN      = 35   # higher bar for non-pipeline companies


# ─── UI helpers ──────────────────────────────────────────────────────────────

def action_pill(a):
    atype = a.get("action_type","Other")
    sp    = atype=="Dividend" and is_special_div(a)
    MAP   = {
        "Dividend":   ("p-div",   "Dividend"),
        "M&A":        ("p-ma",    "M&A"),
        "FDI":        ("p-fdi",   "FDI / Capital raise"),
        "Buyback":    ("p-buy",   "Buyback"),
        "Strategic":  ("p-strat", "Strategic"),
        "Stock Split": ("p-split", "Split"),
        "IPO":        ("p-ipo",   "IPO"),
        "Other":      ("p-news",  "News"),
    }
    cls, lbl = MAP.get(atype, ("p-news", atype))
    if sp: cls, lbl = "p-divsp", "Special dividend"
    return f'<span class="pill {cls}">{lbl}</span>'

def urgency_pill(score):
    u = urgency(score)
    MAP = {"critical":("u-critical","CRITICAL"),"high":("u-high","HIGH"),
           "medium":("u-medium","MEDIUM"),"low":("u-low","LOW")}
    cls, lbl = MAP[u]
    return f'<span class="{cls}">{lbl}</span>'

def is_today(a):
    try:
        return (datetime.date.today() -
                datetime.date.fromisoformat(a.get("date","")[:10])).days <= 1
    except: return False

def src_tag(s):
    colors = {"NSE":"#1565c0","yfinance":"#2e7d32","FMP":"#6a1b9a",
              "News":"#e65100","Google":"#0277bd","Groq":"#534AB7"}
    c = next((v for k,v in colors.items() if k in s), "#555")
    return f'<span style="font-size:10px;font-weight:600;color:{c};">{s.split("—")[0].strip()[:25]}</span>'

def score_chip(score):
    u  = urgency(score)
    sc = {"critical":"#ef5350","high":"#ff6d00","medium":"#0288d1","low":"#444"}[u]
    return (f'<span style="font-size:11px;font-weight:600;padding:1px 7px;'
            f'border-radius:999px;background:{sc}22;color:{sc};border:1px solid {sc}55;">'
            f'{score}</span>')

def render_card(action, expanded=False):
    score   = action["_score"]
    u       = action["_urgency"]
    client  = action.get("client")
    sp_div  = action["action_type"]=="Dividend" and is_special_div(action)
    today   = is_today(action)
    low_conf = action.get("_groq_confidence") == "low"

    if client:
        info = (f'<strong style="color:#fff;">{client["indian_subsidiary"]}</strong>'
                f' → <span style="color:#64b5f6;">{client["client_group"]}</span>'
                f' &nbsp;·&nbsp; <strong style="color:#a5d6a7;">'
                f'${client.get("net_nih_exposure",0):,.0f}M</strong>')
    else:
        info = f'<span style="color:#666;">{action["company_name"]}</span>'

    amt_str = ""
    if action.get("amount") and action.get("currency")=="INR":
        amt_str = f' &nbsp;·&nbsp; <strong style="color:#a5d6a7;">₹{action["amount"]:,.2f}/sh</strong>'
    elif action.get("amount") and action.get("currency")=="USD":
        amt_str = f' &nbsp;·&nbsp; <strong style="color:#90caf9;">${action["amount"]:,.0f}M</strong>'

    fe_str = (f' &nbsp;·&nbsp; <span style="color:#ffcc80;font-size:11px;">'
              f'↔ {action["foreign_entity"]}</span>'
              if action.get("foreign_entity") else "")

    new_badge    = '<span class="new-today">NEW TODAY</span> ' if today else ""
    unver_badge  = '<span class="unverified-badge">unverified</span> ' if low_conf else ""
    client_badge = ('<span class="client-badge">Current client</span>'
                    if action["is_scb_client"] else
                    '<span class="non-client-badge">Non-client</span>')

    # FX implication — fetch for high/critical SCB client actions
    fx_line = ""
    if action["is_scb_client"] and score >= 50 and GROQ_API_KEY and client:
        amt_display = (f"₹{action['amount']:.2f}/share"
                       if action.get("amount") and action.get("currency")=="INR"
                       else (f"${action['amount']:.0f}M"
                             if action.get("amount") else ""))
        impl = fx_implication(
            action["headline"],
            action["action_type"],
            client.get("indian_subsidiary",""),
            client.get("client_group",""),
            amt_display,
            float(client.get("net_nih_exposure",0) or 0),
        )
        if impl:
            fx_line = f'<div class="fx-line">FX → {impl}</div>'

    with st.expander(
        f"{'★ ' if u=='critical' else ''}"
        f"{action['date']}  ·  {action['action_type']}"
        f"{'  ★' if sp_div else ''}  ·  {action['company_name'][:50]}",
        expanded=expanded
    ):
        st.markdown(f"""
        <div class="urgency-{u}">
          <div style="display:flex;align-items:center;gap:5px;flex-wrap:wrap;">
            {urgency_pill(score)} {action_pill(action)}
            {client_badge} {score_chip(score)} {new_badge}{unver_badge}
          </div>
          <div style="font-size:14px;font-weight:500;color:#e0e0e0;
                      margin:5px 0 4px;line-height:1.4;">
            {action['headline'][:200]}
          </div>
          <div style="font-size:12px;color:#888;">{info}{amt_str}{fe_str}</div>
          <div style="font-size:11px;color:#444;margin-top:3px;">
            {src_tag(action['source'])} &nbsp;·&nbsp; {action['date']}
            {"&nbsp;·&nbsp;<a href='" + action['url'] + "' target='_blank' style='color:#333;font-size:11px;'>→</a>" if action.get('url') else ""}
          </div>
          {"<div style='font-size:12px;color:#555;margin-top:5px;'>" + action['raw_detail'][:180] + "</div>" if action.get('raw_detail') else ""}
          {fx_line}
        </div>
        """, unsafe_allow_html=True)


# ─── Load data ────────────────────────────────────────────────────────────────

st.markdown("""
<div class="hdr">
  <strong style="font-size:18px;">🏦 SCB — Corporate Actions Intelligence</strong><br>
  <span style="font-size:12px;opacity:0.8;">
    MNC subsidiaries · SCB FX Pipeline v7 · AI-powered classification + FX signals
  </span>
</div>
""", unsafe_allow_html=True)

with st.spinner("Loading registry..."):
    registry = load_registry()

# Run next batch in background (staggered, 25-min cooldown)
with st.spinner("Running web search batch..."):
    try:
        cache    = run_next_batch(registry)
        progress = get_progress(registry, cache)
    except Exception:
        cache    = load_cache()
        progress = {"total":len(registry["all"]),"fresh_24h":0,
                    "pct":0,"next_in_mins":25,"batches_left":20,
                    "last_run_mins_ago":None}

# Tabs
tab_live, tab_dive = st.tabs(["📡  Live Monitor", "🔍  Client Deep Dive"])


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1 — LIVE MONITOR
# ═══════════════════════════════════════════════════════════════════════════
with tab_live:

    # Stats row + batch progress top-right
    c1,c2,c3,c4 = st.columns([2,2,2,2])
    with c1: st.metric("Monitored", len(registry["all"]))
    with c2: st.metric("Tickers", len(registry["by_ticker"]))
    with c3: st.metric("Window",
        f"–{LOOKBACK_DAYS}d / +{LOOKAHEAD_DAYS}d",
        f"{(dt.now()-timedelta(days=LOOKBACK_DAYS)).strftime('%d %b')} → "
        f"{(dt.now()+timedelta(days=LOOKAHEAD_DAYS)).strftime('%d %b')}")
    with c4:
        pct   = progress["pct"]
        fresh = progress["fresh_24h"]
        total = progress["total"]
        nxt   = progress["next_in_mins"]
        st.markdown(
            f'<div style="text-align:right;padding-top:4px;">'
            f'<div style="font-size:11px;color:#546e7a;">Web search coverage</div>'
            f'<div style="font-size:16px;font-weight:500;color:#{"1D9E75" if pct>50 else "BA7517"};">'
            f'{fresh}/{total} clients</div>'
            f'<div class="batch-status">Next batch in {nxt} min</div>'
            f'</div>', unsafe_allow_html=True)

    if st.button("⟳ Refresh now", use_container_width=False):
        st.cache_data.clear()
        st.rerun()

    st.divider()

    # Fetch + score
    with st.spinner("Fetching from all sources..."):
        raw = fetch_all_corporate_actions(registry)

    for a in raw:
        a["_score"]   = score_action(a)
        a["_urgency"] = urgency(a["_score"])

    # Separate client vs non-client
    client_actions     = sorted(
        [a for a in raw if a["is_scb_client"] and a["_score"] >= MINIMUM_SCORE],
        key=lambda x: x["_score"], reverse=True)
    non_client_actions = sorted(
        [a for a in raw if not a["is_scb_client"] and a["_score"] >= NON_CLIENT_MIN
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
      <div class="cc" style="background:#0d0d0d;border:1px solid #2a2a2a;">
        <div class="cc-num" style="color:#888;">{len(non_client_actions)}</div>
        <div class="cc-lbl" style="color:#555;">Non-pipeline</div>
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
                    r'<strong style="color:#e0e0e0;">\1</strong>', line)
                color  = "#b0bec5" if line.startswith(("•","-")) else "#546e7a"
                prefix = "padding:2px 0 2px 4px;" if line.startswith(("•","-")) else ""
                st.markdown(f'<div style="font-size:13px;color:{color};'
                            f'line-height:1.75;{prefix}">{line}</div>',
                            unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-size:10px;color:#37474f;margin-top:8px;">'
            f'Groq / Llama 3 &nbsp;·&nbsp; {len(snapshot)} signals &nbsp;·&nbsp; '
            f'Cached 30 min</div></div>', unsafe_allow_html=True)

    st.divider()

    # Filters
    fc1,fc2,fc3 = st.columns([2,2,2])
    with fc1:
        f_type = st.selectbox("Action type",
            ["All"] + sorted({a["action_type"] for a in client_actions}))
    with fc2:
        f_urg = st.selectbox("Min urgency",
            ["All","Medium+","High+","Critical only"])
    with fc3:
        f_src = st.selectbox("Source",
            ["All"] + sorted({a["source"].split("—")[0].strip()
                              for a in client_actions}))

    def apply_f(lst):
        if f_type != "All":  lst = [a for a in lst if a["action_type"]==f_type]
        if f_urg == "Medium+":
            lst = [a for a in lst if a["_urgency"] in ("critical","high","medium")]
        elif f_urg == "High+":
            lst = [a for a in lst if a["_urgency"] in ("critical","high")]
        elif f_urg == "Critical only":
            lst = [a for a in lst if a["_urgency"]=="critical"]
        if f_src != "All":
            lst = [a for a in lst if f_src in a["source"]]
        return lst

    filtered = apply_f(client_actions)
    st.caption(
        f"**{len(filtered)} current client actions** · "
        f"{len(non_client_actions)} non-pipeline companies · "
        f"Min score {MINIMUM_SCORE}"
    )

    # Main columns
    col_feed, col_right = st.columns([3,1], gap="large")

    with col_feed:
        if not filtered:
            st.info("No actions match filters.")
        else:
            for action in filtered[:60]:
                render_card(
                    action,
                    expanded=(action["_urgency"] in ("critical","high"))
                )

        # Non-client important companies box
        if non_client_actions:
            st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
            with st.expander(
                f"🔭  Non-pipeline companies with significant activity  "
                f"({len(non_client_actions)} found)",
                expanded=False
            ):
                st.caption(
                    "These companies are NOT in your SCB pipeline. "
                    "Consider whether any should be added to the Excel."
                )
                st.markdown('<div class="non-client-box">', unsafe_allow_html=True)
                for a in non_client_actions[:20]:
                    sig_col = {"M&A":"#ef9a9a","FDI":"#90caf9","IPO":"#b39ddb",
                               "Buyback":"#ffcc80","Strategic":"#fff176"}.get(
                               a["action_type"],"#888")
                    amt_str = ""
                    if a.get("amount"):
                        curr = a.get("currency","")
                        sym  = "₹" if curr=="INR" else "$"
                        amt_str = f' · <strong>{sym}{a["amount"]:,.0f}</strong>'
                    fe_str = f' · <span style="color:#ffcc80;">{a["foreign_entity"]}</span>' if a.get("foreign_entity") else ""
                    st.markdown(f"""
                    <div class="nc-item">
                      <span style="font-size:11px;font-weight:600;color:{sig_col};">
                        {a['action_type']}
                      </span>
                      &nbsp;
                      <span style="color:#ccc;">{a['company_name'][:50]}</span>
                      {amt_str}{fe_str}
                      <span style="color:#444;font-size:10px;"> · {a['date']}</span>
                      <div style="font-size:11px;color:#666;margin-top:2px;">
                        {a['headline'][:120]}
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

    with col_right:
        # Urgency breakdown
        st.markdown("**Urgency breakdown**")
        for lbl, grp, col in [
            ("Critical (70+)", critical, "#ef5350"),
            ("High (50–69)",   high,     "#ff6d00"),
            ("Medium (35–49)", medium,   "#0288d1"),
            ("Low (25–34)",    low,      "#444"),
        ]:
            if grp:
                st.markdown(
                    f'<div style="font-size:12px;color:#ccc;margin:3px 0;">'
                    f'{lbl} &nbsp;<strong style="color:{col};">{len(grp)}</strong></div>',
                    unsafe_allow_html=True)

        st.divider()

        # Web search progress
        st.markdown("**Web search progress**")
        pct = progress["pct"]
        st.progress(pct / 100)
        st.markdown(
            f'<div style="font-size:11px;color:#546e7a;">'
            f'{progress["fresh_24h"]}/{progress["total"]} clients (last 24h)<br>'
            f'{progress["batches_left"]} batches remaining<br>'
            f'Next batch in {progress["next_in_mins"]} min</div>',
            unsafe_allow_html=True)

        st.divider()

        # Current client highlights
        st.markdown("**Current client highlights**")
        for a in [x for x in filtered if x["is_scb_client"]][:5]:
            c  = a.get("client") or {}
            uc = {"critical":"#ef5350","high":"#ff6d00",
                  "medium":"#0288d1","low":"#444"}[a["_urgency"]]
            st.markdown(f"""
            <div style="border:1px solid #1e3a5f;border-left:3px solid {uc};
                        border-radius:6px;padding:8px 10px;margin-bottom:6px;">
              <div style="font-size:11px;font-weight:600;color:#64b5f6;">
                {c.get('client_group','')}
              </div>
              <div style="font-size:11px;color:#ccc;">{c.get('indian_subsidiary','')[:35]}</div>
              <div style="margin-top:4px;display:flex;gap:5px;align-items:center;">
                {action_pill(a)}
                <span style="font-size:10px;color:{uc};font-weight:600;">{a['_score']}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

        st.divider()

        # By action type
        st.markdown("**By action type**")
        tc = {}
        for a in filtered:
            k = "Special div." if a["action_type"]=="Dividend" and is_special_div(a) else a["action_type"]
            tc[k] = tc.get(k,0)+1
        for k,v in sorted(tc.items(),key=lambda x:-x[1]):
            st.markdown(
                f'<div style="font-size:12px;color:#aaa;margin:2px 0;">'
                f'{k} <strong style="color:#fff;">{v}</strong></div>',
                unsafe_allow_html=True)

    # Full data table
    st.divider()
    with st.expander("📄 Full data table + CSV", expanded=False):
        all_display = filtered + non_client_actions
        if all_display:
            rows = [{
                "Score":    a["_score"],
                "Urgency":  a["_urgency"].title(),
                "Client":   "Yes" if a["is_scb_client"] else "No",
                "Date":     a["date"],
                "Action":   ("Special div." if a["action_type"]=="Dividend"
                             and is_special_div(a) else a["action_type"]),
                "Company":  a["company_name"][:40],
                "Headline": a["headline"][:80],
                "Amount":   a.get("amount"),
                "Currency": a.get("currency"),
                "Source":   a["source"][:30],
                "MNC":      (a.get("client") or {}).get("client_group","—"),
                "NIH $M":   (a.get("client") or {}).get("net_nih_exposure"),
            } for a in all_display]
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Download CSV",
                df.to_csv(index=False),
                f"scb_corp_{dt.now().strftime('%Y%m%d_%H%M')}.csv","text/csv")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2 — CLIENT DEEP DIVE
# ═══════════════════════════════════════════════════════════════════════════
with tab_dive:
    st.markdown("""
    <div style="background:#0a1628;border:1px solid #1e3a5f;border-radius:10px;
                padding:14px 18px;margin-bottom:18px;">
      <strong style="color:#64b5f6;">Client Deep Dive</strong>
      <div style="font-size:12px;color:#78909c;margin-top:4px;">
        Select any client · searches past 12 months · Groq extracts
        significant corporate actions only
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
        sub = sel_rec["indian_subsidiary"]
        grp = sel_rec["client_group"]
        exp = sel_rec.get("net_nih_exposure",0) or 0
        tier= sel_rec.get("priority_tier","")

        st.markdown(f"""
        <div style="border:1px solid #1e3a5f;border-radius:8px;
                    padding:12px 16px;margin-bottom:16px;background:#06111a;">
          <div style="font-size:13px;font-weight:500;color:#fff;">{sub}</div>
          <div style="font-size:12px;color:#64b5f6;">{grp}</div>
          <div style="font-size:11px;color:#546e7a;margin-top:4px;">
            NIH: <strong style="color:#a5d6a7;">${exp:,.0f}M</strong>
            &nbsp;·&nbsp; {tier[:25] if tier else '—'}
            &nbsp;·&nbsp; CIN: {sel_rec.get('cin','—')[:25]}
          </div>
          {"<div style='font-size:11px;color:#37474f;margin-top:4px;'>Known trigger: " + sel_rec.get('event_flag','')[:120] + "</div>" if sel_rec.get('event_flag') else ""}
        </div>
        """, unsafe_allow_html=True)

    if run_btn and sel_rec:
        if not GROQ_API_KEY:
            st.error("GROQ_API_KEY required for deep dive.")
        else:
            with st.spinner(f"Searching 12 months for {sub}..."):
                result = run_deep_dive(grp, sub, exp)

            st.caption(
                f"**{result['query_count']} headlines** found · "
                f"**{len(result['events'])} significant events** extracted · "
                f"{result['searched_at']}"
            )

            if not result["events"]:
                st.info("No significant events found. Try refreshing.")
            else:
                m1,m2,m3 = st.columns(3)
                with m1: st.metric("Events", len(result["events"]))
                with m2: st.metric("High significance",
                    sum(1 for e in result["events"] if e.get("significance")=="High"))
                with m3:
                    dates = [e.get("date","") for e in result["events"] if e.get("date")]
                    if dates:
                        st.metric("Date range",
                            f"{min(dates)[:7]} → {max(dates)[:7]}")

                st.divider()
                for ev in result["events"]:
                    sig  = ev.get("significance","Low")
                    css  = {"High":"dd-high","Medium":"dd-medium","Low":"dd-low"}[sig]
                    sc   = {"High":"#ef5350","Medium":"#ff6d00","Low":"#555"}[sig]
                    st.markdown(f"""
                    <div class="dd-event {css}">
                      <div style="font-size:11px;color:#555;margin-bottom:3px;">
                        {ev.get('date','')[:10]}
                        &nbsp;·&nbsp;
                        <span style="color:{sc};font-weight:700;">{sig.upper()}</span>
                        &nbsp;·&nbsp;
                        <span class="dd-type">{ev.get('action_type','Other')}</span>
                        {"&nbsp;·&nbsp;<span style='color:#ffcc80;font-size:10px;'>" + ev['counterparty'] + "</span>" if ev.get('counterparty') else ""}
                      </div>
                      <div style="font-size:13px;font-weight:500;color:#e0e0e0;margin-bottom:3px;">
                        {ev.get('headline','')}
                      </div>
                      {"<div style='font-size:12px;color:#90caf9;'>FX → " + ev['fx_implication'] + "</div>" if ev.get('fx_implication') else ""}
                    </div>
                    """, unsafe_allow_html=True)

            with st.expander(f"Raw headlines ({result['query_count']})", expanded=False):
                for h in sorted(result["headlines"],key=lambda x:x["date"],reverse=True)[:40]:
                    st.markdown(
                        f'<div style="font-size:12px;color:#555;padding:2px 0;">'
                        f'<span style="color:#444;">{h["date"]}</span> &nbsp; {h["title"]}'
                        f'</div>', unsafe_allow_html=True)
