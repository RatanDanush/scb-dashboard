"""
app.py — SCB Corporate Actions Intelligence Dashboard  v3
----------------------------------------------------------
Two tabs:
  1. Live Monitor  — scored feed with urgency UI + AI briefing
  2. Client Deep Dive — 12-month historical search for any client
"""

import streamlit as st
import pandas as pd
import re
import datetime
from datetime import datetime as dt, timedelta
from streamlit_autorefresh import st_autorefresh

from client_registry import load_registry
from corporate_fetcher import fetch_all_corporate_actions, LOOKBACK_DAYS, LOOKAHEAD_DAYS
from groq_summarizer import generate_daily_briefing, make_snapshot, GROQ_API_KEY
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
  /* Header */
  .hdr{background:#002f6c;color:#fff;padding:14px 20px;border-radius:8px;margin-bottom:4px;}

  /* Urgency banners */
  .urgency-critical{background:#1a0505;border:1px solid #d32f2f;border-left:4px solid #f44336;
    border-radius:8px;padding:12px 16px;margin-bottom:8px;animation:pulse-red 2s ease-in-out infinite;}
  .urgency-high{background:#1a0e05;border:1px solid #e65100;border-left:4px solid #ff6d00;
    border-radius:8px;padding:12px 16px;margin-bottom:8px;}
  .urgency-medium{background:#06111a;border:1px solid #0277bd;border-left:4px solid #0288d1;
    border-radius:8px;padding:12px 16px;margin-bottom:8px;}
  .urgency-low{background:#111;border:1px solid #333;border-left:4px solid #444;
    border-radius:8px;padding:10px 14px;margin-bottom:6px;opacity:0.85;}

  @keyframes pulse-red{0%,100%{border-left-color:#f44336;}50%{border-left-color:#ff8a80;}}

  /* Urgency pills */
  .u-critical{background:#b71c1c;color:#ffcdd2;padding:2px 8px;border-radius:999px;
    font-size:11px;font-weight:700;letter-spacing:0.04em;}
  .u-high{background:#bf360c;color:#ffccbc;padding:2px 8px;border-radius:999px;
    font-size:11px;font-weight:600;}
  .u-medium{background:#01579b;color:#b3e5fc;padding:2px 8px;border-radius:999px;
    font-size:11px;font-weight:600;}
  .u-low{background:#212121;color:#757575;padding:2px 8px;border-radius:999px;
    font-size:11px;}

  /* Action type pills */
  .pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:600;margin-right:4px;}
  .p-div   {background:#1a3d1a;color:#81c784;}
  .p-divsp {background:#0d3320;color:#a5d6a7;border:1px solid #2e7d32;}
  .p-ma    {background:#3d1a1a;color:#ef9a9a;}
  .p-fdi   {background:#1a2d3d;color:#90caf9;}
  .p-buy   {background:#3d2a1a;color:#ffcc80;}
  .p-strat {background:#2d2a1a;color:#fff176;}
  .p-split {background:#2a2a2a;color:#aaa;}
  .p-ipo   {background:#1a1a3d;color:#b39ddb;}
  .p-news  {background:#1e1e1e;color:#888;}

  /* Client / non-client badges */
  .client-badge{background:#0d2137;border:1px solid #1976d2;color:#64b5f6;
    padding:2px 9px;border-radius:999px;font-size:11px;font-weight:600;}
  .non-client-badge{background:#1e1e1e;border:1px solid #333;color:#666;
    padding:2px 9px;border-radius:999px;font-size:11px;}

  /* New today badge */
  .new-today{background:#1b5e20;color:#a5d6a7;padding:1px 7px;border-radius:999px;
    font-size:10px;font-weight:700;letter-spacing:0.05em;margin-left:4px;}

  /* Score chip */
  .score-chip{font-size:11px;font-weight:600;padding:1px 7px;border-radius:999px;}

  /* Misc */
  .meta{font-size:11px;color:#555;margin-top:4px;}
  .headline{font-size:14px;font-weight:500;color:#e0e0e0;margin:5px 0 4px;line-height:1.4;}
  .sub-text{font-size:12px;color:#777;line-height:1.5;}
  .mnc{color:#64b5f6;}
  .exposure{color:#a5d6a7;font-weight:600;}

  /* Urgency counter bar */
  .counter-bar{display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap;}
  .counter-chip{border-radius:8px;padding:10px 14px;text-align:center;min-width:80px;flex:1;}
  .cc-critical{background:#1a0505;border:1px solid #d32f2f;}
  .cc-high    {background:#1a0e05;border:1px solid #e65100;}
  .cc-medium  {background:#06111a;border:1px solid #0277bd;}
  .cc-low     {background:#111;border:1px solid #333;}
  .cc-num{font-size:22px;font-weight:500;}
  .cc-label{font-size:10px;margin-top:2px;opacity:0.7;}

  /* Deep dive styles */
  .dd-event{border-radius:8px;padding:12px 14px;margin-bottom:8px;border:1px solid #222;}
  .dd-high  {border-left:3px solid #f44336;background:#1a0505;}
  .dd-medium{border-left:3px solid #ff6d00;background:#1a0e05;}
  .dd-low   {border-left:3px solid #333;background:#111;}
  .dd-date{font-size:11px;color:#555;margin-bottom:4px;}
  .dd-headline{font-size:13px;font-weight:500;color:#e0e0e0;margin-bottom:4px;}
  .dd-fx{font-size:12px;color:#90caf9;line-height:1.5;}
  .dd-type{display:inline-block;font-size:10px;font-weight:600;padding:1px 7px;
    border-radius:999px;background:#1a2d3d;color:#90caf9;margin-right:4px;}
</style>
""", unsafe_allow_html=True)


# ─── Scoring (same as before) ─────────────────────────────────────────────────

def is_special_div(action: dict) -> bool:
    h = (action.get("headline","") + " " + action.get("raw_detail","")).lower()
    amt = action.get("amount") or 0
    return any(w in h for w in ["special","extraordinary","one-time","interim",
               "repatriat","bumper","enhanced"]) or amt >= 15

ACTION_SCORES = {
    "Dividend_Special": 30, "M&A": 30, "FDI": 25,
    "Dividend": 15, "Buyback": 20, "Strategic": 10,
    "Stock Split": 5, "IPO": 20, "Other": 3,
}

def score_action(action: dict) -> int:
    total = 40 if action.get("is_scb_client") else 0
    atype = action.get("action_type","Other")
    akey  = "Dividend_Special" if atype=="Dividend" and is_special_div(action) else atype
    total += ACTION_SCORES.get(akey, 3)
    exp = (action.get("client") or {}).get("net_nih_exposure") or 0
    if exp >= 1000: total += 20
    elif exp >= 500: total += 12
    elif exp >= 100: total += 6
    elif exp > 0: total += 2
    try:
        delta = (datetime.date.today() -
                 datetime.date.fromisoformat(action.get("date","")[:10])).days
        if delta <= 1: total += 10
        elif delta <= 3: total += 7
        elif delta <= 7: total += 4
    except Exception:
        pass
    return total

def urgency_level(score: int) -> str:
    if score >= 70: return "critical"
    if score >= 50: return "high"
    if score >= 35: return "medium"
    return "low"

MINIMUM_SCORE = 25


# ─── UI helpers ──────────────────────────────────────────────────────────────

def action_pill(action: dict) -> str:
    atype = action.get("action_type","Other")
    sp = atype=="Dividend" and is_special_div(action)
    MAP = {
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

def urgency_pill(score: int) -> str:
    u = urgency_level(score)
    labels = {
        "critical": ("u-critical", "CRITICAL"),
        "high":     ("u-high",     "HIGH"),
        "medium":   ("u-medium",   "MEDIUM"),
        "low":      ("u-low",      "LOW"),
    }
    cls, lbl = labels[u]
    return f'<span class="{cls}">{lbl}</span>'

def is_today(action: dict) -> bool:
    try:
        return (datetime.date.today() -
                datetime.date.fromisoformat(action.get("date","")[:10])).days <= 1
    except Exception:
        return False

def source_tag(s: str) -> str:
    colors = {"NSE":"#1565c0","yfinance":"#2e7d32","FMP":"#6a1b9a","News":"#e65100"}
    c = next((v for k,v in colors.items() if k in s), "#555")
    return f'<span style="font-size:10px;font-weight:600;color:{c};">{s.split("—")[0].strip()}</span>'


# ─── Load registry ────────────────────────────────────────────────────────────

st.markdown("""
<div class="hdr">
  <strong style="font-size:18px;">🏦 SCB — Corporate Actions Intelligence</strong><br>
  <span style="font-size:12px;opacity:0.8;">
    MNC subsidiaries · SCB FX Pipeline v7 · Prioritised by urgency
  </span>
</div>
""", unsafe_allow_html=True)

with st.spinner("Loading client registry..."):
    registry = load_registry()

# ─── Tabs ────────────────────────────────────────────────────────────────────

tab_live, tab_dive = st.tabs(["📡  Live Monitor", "🔍  Client Deep Dive"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — LIVE MONITOR
# ═══════════════════════════════════════════════════════════════════════════════

with tab_live:

    # Stats row
    c1,c2,c3,c4,c5 = st.columns([2,2,2,2,1])
    with c1: st.metric("Monitored", len(registry["all"]))
    with c2: st.metric("Tickers", len(registry["by_ticker"]))
    with c3: st.metric("Window", f"–{LOOKBACK_DAYS}d / +{LOOKAHEAD_DAYS}d",
        f"{(dt.now()-timedelta(days=LOOKBACK_DAYS)).strftime('%d %b')} → "
        f"{(dt.now()+timedelta(days=LOOKAHEAD_DAYS)).strftime('%d %b')}")
    with c4: st.metric("AI briefing", "ON" if GROQ_API_KEY else "OFF (no key)")
    with c5:
        if st.button("⟳", use_container_width=True, help="Refresh now"):
            st.cache_data.clear()
            st.rerun()

    st.divider()

    # Fetch + score
    with st.spinner("Scanning all sources..."):
        raw = fetch_all_corporate_actions(registry)
    for a in raw:
        a["_score"] = score_action(a)
        a["_urgency"] = urgency_level(a["_score"])

    actions = sorted(
        [a for a in raw if a["_score"] >= MINIMUM_SCORE],
        key=lambda x: x["_score"], reverse=True
    )

    critical = [a for a in actions if a["_urgency"]=="critical"]
    high     = [a for a in actions if a["_urgency"]=="high"]
    medium   = [a for a in actions if a["_urgency"]=="medium"]
    low      = [a for a in actions if a["_urgency"]=="low"]

    # ── Urgency counter bar ───────────────────────────────────────────────────
    st.markdown(f"""
    <div class="counter-bar">
      <div class="counter-chip cc-critical">
        <div class="cc-num" style="color:#ef5350;">{len(critical)}</div>
        <div class="cc-label" style="color:#ef9a9a;">Critical</div>
      </div>
      <div class="counter-chip cc-high">
        <div class="cc-num" style="color:#ff6d00;">{len(high)}</div>
        <div class="cc-label" style="color:#ffcc80;">High</div>
      </div>
      <div class="counter-chip cc-medium">
        <div class="cc-num" style="color:#0288d1;">{len(medium)}</div>
        <div class="cc-label" style="color:#b3e5fc;">Medium</div>
      </div>
      <div class="counter-chip cc-low">
        <div class="cc-num" style="color:#555;">{len(low)}</div>
        <div class="cc-label" style="color:#444;">Low</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── AI daily briefing ─────────────────────────────────────────────────────
    snapshot = make_snapshot(actions)
    if GROQ_API_KEY and snapshot:
        st.markdown("""
        <div style="background:#0a1628;border:1px solid #1e3a5f;border-radius:10px;
                    padding:14px 18px;margin-bottom:14px;">
          <div style="font-size:11px;font-weight:600;color:#64b5f6;
                      letter-spacing:0.06em;margin-bottom:8px;">
            ◆ AI DAILY BRIEFING — FX DESK
          </div>
        """, unsafe_allow_html=True)
        with st.spinner("Generating briefing..."):
            briefing = generate_daily_briefing(snapshot)
        if briefing:
            for line in briefing.split("\n"):
                line = line.strip()
                if not line: continue
                line = re.sub(r'\*\*(.+?)\*\*',
                    r'<strong style="color:#e0e0e0;">\1</strong>', line)
                prefix = "padding:2px 0 2px 4px;" if line.startswith(("•","-")) else "padding:1px 0;"
                color  = "#b0bec5" if line.startswith(("•","-")) else "#546e7a"
                st.markdown(
                    f'<div style="font-size:13px;color:{color};line-height:1.75;{prefix}">'
                    f'{line}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-size:10px;color:#37474f;margin-top:8px;">'
            f'Groq / Llama 3 &nbsp;·&nbsp; {len(snapshot)} signals &nbsp;·&nbsp; '
            f'Cached 30 min</div></div>', unsafe_allow_html=True)
    elif not GROQ_API_KEY:
        st.info("Add GROQ_API_KEY to .env to enable the AI daily briefing.")

    st.divider()

    # ── Filters ───────────────────────────────────────────────────────────────
    fc1,fc2,fc3 = st.columns([2,2,2])
    with fc1:
        f_rel = st.selectbox("Relationship",
            ["All","Current clients only","Non-clients only"])
    with fc2:
        f_type = st.selectbox("Action type",
            ["All"] + sorted({a["action_type"] for a in actions}))
    with fc3:
        f_urg = st.selectbox("Min urgency",
            ["All","Medium+","High+","Critical only"])

    def apply_f(lst):
        if f_rel == "Current clients only":
            lst = [a for a in lst if a["is_scb_client"]]
        elif f_rel == "Non-clients only":
            lst = [a for a in lst if not a["is_scb_client"]]
        if f_type != "All":
            lst = [a for a in lst if a["action_type"]==f_type]
        if f_urg == "Medium+":
            lst = [a for a in lst if a["_urgency"] in ("critical","high","medium")]
        elif f_urg == "High+":
            lst = [a for a in lst if a["_urgency"] in ("critical","high")]
        elif f_urg == "Critical only":
            lst = [a for a in lst if a["_urgency"]=="critical"]
        return lst

    filtered = apply_f(actions)
    cc = sum(1 for a in filtered if a["is_scb_client"])
    st.caption(
        f"**{len(filtered)} actions** shown · "
        f"**{cc} current clients** · "
        f"{len(filtered)-cc} non-clients · "
        f"{len(raw)-len(actions)} below threshold hidden"
    )

    # ── Main feed ─────────────────────────────────────────────────────────────
    col_feed, col_right = st.columns([3,1], gap="large")

    with col_feed:
        if not filtered:
            st.info("No actions meet the threshold. Adjust filters or refresh.")
        else:
            for action in filtered[:60]:
                score   = action["_score"]
                urgency = action["_urgency"]
                client  = action.get("client")
                sp_div  = action["action_type"]=="Dividend" and is_special_div(action)
                today   = is_today(action)

                # Card CSS class based on urgency
                card_css = f"urgency-{urgency}"

                # Client info line
                if client:
                    info = (
                        f'<strong style="color:#fff;">{client["indian_subsidiary"]}</strong>'
                        f' → <span class="mnc">{client["client_group"]}</span>'
                        f' &nbsp;·&nbsp; <span class="exposure">'
                        f'${client.get("net_nih_exposure",0):,.0f}M</span>'
                    )
                else:
                    info = f'<span style="color:#777;">{action["company_name"]}</span>'

                # Amount
                amt_str = ""
                if action.get("amount") and action.get("currency")=="INR":
                    amt_str = f' &nbsp;·&nbsp; <strong style="color:#a5d6a7;">₹{action["amount"]:,.2f}/sh</strong>'
                elif action.get("amount") and action.get("currency")=="USD":
                    amt_str = f' &nbsp;·&nbsp; <strong style="color:#90caf9;">${action["amount"]:,.0f}M</strong>'

                # Foreign entity
                fe_str = ""
                if action.get("foreign_entity"):
                    fe_str = f' &nbsp;·&nbsp; <span style="color:#ffcc80;font-size:11px;">↔ {action["foreign_entity"]}</span>'

                # Today badge
                new_badge = '<span class="new-today">NEW TODAY</span>' if today else ""

                # Score chip
                sc = {"critical":"#ef5350","high":"#ff6d00","medium":"#0288d1","low":"#444"}[urgency]
                score_html = (f'<span class="score-chip" '
                              f'style="background:{sc}22;color:{sc};border:1px solid {sc}55;">'
                              f'{score}</span>')

                with st.expander(
                    f"{'★ ' if urgency=='critical' else ''}"
                    f"{action['date']}  ·  {action['action_type']}"
                    f"{'  ★' if sp_div else ''}  ·  {action['company_name'][:50]}",
                    expanded=(urgency in ("critical","high") and action["is_scb_client"])
                ):
                    st.markdown(f"""
                    <div class="{card_css}">
                      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                        {urgency_pill(score)} {action_pill(action)}
                        {'<span class="client-badge">Current client</span>' if action["is_scb_client"] else '<span class="non-client-badge">Non-client</span>'}
                        {score_html} {new_badge}
                      </div>
                      <div class="headline">{action['headline'][:200]}</div>
                      <div style="font-size:12px;color:#999;">{info}{amt_str}{fe_str}</div>
                      <div class="meta">
                        {source_tag(action['source'])} &nbsp;·&nbsp; {action['date']}
                        {"&nbsp;·&nbsp;<a href='" + action['url'] + "' target='_blank' style='color:#444;font-size:11px;'>→</a>" if action.get('url') else ""}
                      </div>
                      {"<div class='sub-text' style='margin-top:6px;'>" + action['raw_detail'][:180] + "</div>" if action.get('raw_detail') else ""}
                    </div>
                    """, unsafe_allow_html=True)

    # ── Right panel ───────────────────────────────────────────────────────────
    with col_right:
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
        st.markdown("**Current client highlights**")
        for a in [x for x in filtered if x["is_scb_client"]][:6]:
            c = a.get("client") or {}
            uc = {"critical":"#ef5350","high":"#ff6d00","medium":"#0288d1","low":"#444"}[a["_urgency"]]
            st.markdown(f"""
            <div style="border:1px solid #1e3a5f;border-left:3px solid {uc};
                        border-radius:6px;padding:8px 10px;margin-bottom:6px;">
              <div style="font-size:11px;font-weight:600;color:#64b5f6;">
                {c.get('client_group','')}
              </div>
              <div style="font-size:11px;color:#ccc;">{c.get('indian_subsidiary','')[:35]}</div>
              <div style="margin-top:4px;display:flex;align-items:center;gap:5px;">
                {action_pill(a)}
                <span style="font-size:10px;color:{uc};font-weight:600;">{a['_score']}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

        st.divider()
        st.markdown("**By action type**")
        tc = {}
        for a in filtered:
            k = "Special div." if a["action_type"]=="Dividend" and is_special_div(a) else a["action_type"]
            tc[k] = tc.get(k,0) + 1
        for k,v in sorted(tc.items(), key=lambda x:-x[1]):
            st.markdown(
                f'<div style="font-size:12px;color:#aaa;margin:2px 0;">'
                f'{k} <strong style="color:#fff;">{v}</strong></div>',
                unsafe_allow_html=True)

    # ── Full data table ───────────────────────────────────────────────────────
    st.divider()
    with st.expander("📄 Full data table + CSV", expanded=False):
        if filtered:
            rows = [{
                "Score":     a["_score"],
                "Urgency":   a["_urgency"].title(),
                "Date":      a["date"],
                "Action":    "Special div." if a["action_type"]=="Dividend" and is_special_div(a) else a["action_type"],
                "Company":   a["company_name"][:40],
                "Headline":  a["headline"][:80],
                "Amount":    a.get("amount"),
                "Currency":  a.get("currency"),
                "Source":    a["source"][:30],
                "MNC Parent":(a.get("client") or {}).get("client_group","—"),
                "NIH $M":   (a.get("client") or {}).get("net_nih_exposure"),
                "Client":   "Yes" if a["is_scb_client"] else "No",
            } for a in filtered]
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Download CSV",
                df.to_csv(index=False),
                f"scb_corp_{dt.now().strftime('%Y%m%d_%H%M')}.csv","text/csv")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CLIENT DEEP DIVE
# ═══════════════════════════════════════════════════════════════════════════════

with tab_dive:
    st.markdown("""
    <div style="background:#0a1628;border:1px solid #1e3a5f;border-radius:10px;
                padding:14px 18px;margin-bottom:18px;">
      <strong style="color:#64b5f6;">Client Deep Dive</strong>
      <div style="font-size:12px;color:#78909c;margin-top:4px;">
        Select any client from your pipeline — searches past 12 months across
        Google News, ET, Business Standard and Moneycontrol.
        Groq extracts only significant corporate actions.
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Build dropdown options — sorted by priority score
    options = []
    seen_groups = set()
    for rec in sorted(registry["all"],
                      key=lambda r: r.get("priority_score",0), reverse=True):
        if not rec.get("indian_subsidiary"):
            continue
        label = f"{rec['indian_subsidiary']}  ({rec['client_group']})"
        options.append((label, rec))

    if not options:
        st.warning("No clients loaded from registry.")
        st.stop()

    dc1, dc2 = st.columns([3,1])
    with dc1:
        selected_label = st.selectbox(
            "Select client",
            [o[0] for o in options],
            help="Sorted by pipeline priority score"
        )
    with dc2:
        run_btn = st.button("🔍 Search 12 months", use_container_width=True,
                            type="primary")

    # Find selected record
    selected_rec = next((r for l,r in options if l==selected_label), None)

    if selected_rec:
        sub = selected_rec["indian_subsidiary"]
        grp = selected_rec["client_group"]
        exp = selected_rec.get("net_nih_exposure",0) or 0
        tier = selected_rec.get("priority_tier","")

        # Show client card
        st.markdown(f"""
        <div style="border:1px solid #1e3a5f;border-radius:8px;padding:12px 16px;
                    margin-bottom:16px;background:#06111a;">
          <div style="font-size:13px;font-weight:500;color:#fff;">{sub}</div>
          <div style="font-size:12px;color:#64b5f6;margin-top:2px;">{grp}</div>
          <div style="font-size:11px;color:#546e7a;margin-top:4px;">
            NIH exposure: <strong style="color:#a5d6a7;">${exp:,.0f}M</strong>
            &nbsp;·&nbsp; {tier[:25] if tier else '—'}
            &nbsp;·&nbsp; CIN: {selected_rec.get('cin','—')[:25]}
          </div>
          {"<div style='font-size:11px;color:#37474f;margin-top:4px;'>Known trigger: " + selected_rec.get('event_flag','')[:120] + "</div>" if selected_rec.get('event_flag') else ""}
        </div>
        """, unsafe_allow_html=True)

    if run_btn and selected_rec:
        if not GROQ_API_KEY:
            st.error("GROQ_API_KEY not set — Groq is required for deep dive analysis.")
        else:
            with st.spinner(f"Searching 12 months of news for {sub}..."):
                result = run_deep_dive(grp, sub, exp)

            st.caption(
                f"Found **{result['query_count']} headlines** · "
                f"Groq extracted **{len(result['events'])} significant events** · "
                f"Searched at {result['searched_at']}"
            )

            if not result["events"]:
                st.info("No significant corporate actions found in the past 12 months. "
                        "Try refreshing or check if the company name matches news sources.")
            else:
                # Summary metrics
                m1,m2,m3 = st.columns(3)
                with m1: st.metric("Events found", len(result["events"]))
                with m2: st.metric("High significance",
                    sum(1 for e in result["events"] if e.get("significance")=="High"))
                with m3: st.metric("Date range",
                    f"{result['events'][-1].get('date','?')[:7]} → "
                    f"{result['events'][0].get('date','?')[:7]}" if result["events"] else "—")

                st.divider()

                # Events feed
                for ev in result["events"]:
                    sig  = ev.get("significance","Low")
                    css  = {"High":"dd-high","Medium":"dd-medium","Low":"dd-low"}[sig]
                    atype = ev.get("action_type","Other")
                    date  = ev.get("date","")[:10]
                    hl    = ev.get("headline","")
                    fx    = ev.get("fx_implication","")

                    sig_color = {"High":"#ef5350","Medium":"#ff6d00","Low":"#555"}[sig]
                    sig_lbl   = f'<span style="font-size:10px;font-weight:700;color:{sig_color};">{sig.upper()}</span>'

                    st.markdown(f"""
                    <div class="dd-event {css}">
                      <div class="dd-date">{date} &nbsp;·&nbsp; {sig_lbl}
                        &nbsp;·&nbsp; <span class="dd-type">{atype}</span>
                      </div>
                      <div class="dd-headline">{hl}</div>
                      {"<div class='dd-fx'>FX implication: " + fx + "</div>" if fx else ""}
                    </div>
                    """, unsafe_allow_html=True)

            # Raw headlines expander
            with st.expander(f"Raw headlines ({result['query_count']} found)", expanded=False):
                for h in sorted(result["headlines"],
                                key=lambda x: x["date"], reverse=True)[:40]:
                    st.markdown(
                        f'<div style="font-size:12px;color:#666;padding:3px 0;">'
                        f'<span style="color:#444;">{h["date"]}</span> &nbsp; {h["title"]}'
                        f'</div>', unsafe_allow_html=True)
