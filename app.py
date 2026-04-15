"""
app.py — SCB Corporate Actions Intelligence Dashboard
------------------------------------------------------
Prioritises corporate actions using a scoring system:
  Client match  (40pts) + Action urgency (30pts) + Exposure (20pts) + Recency (10pts)
Minimum score to display: 25
"""

import streamlit as st
import pandas as pd
import re
import datetime
from datetime import datetime as dt, timedelta
from streamlit_autorefresh import st_autorefresh

from client_registry import load_registry
from corporate_fetcher import fetch_all_corporate_actions, LOOKBACK_DAYS, LOOKAHEAD_DAYS

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
  .hdr{background:#002f6c;color:#fff;padding:14px 20px;border-radius:8px;margin-bottom:16px;}
  .pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:600;margin-right:4px;}
  .p-div   {background:#1a3d1a;color:#81c784;}
  .p-divsp {background:#0d3320;color:#a5d6a7;border:1px solid #2e7d32;}
  .p-ma    {background:#3d1a1a;color:#ef9a9a;}
  .p-fdi   {background:#1a2d3d;color:#90caf9;}
  .p-buy   {background:#3d2a1a;color:#ffcc80;}
  .p-strat {background:#2d2a1a;color:#fff176;}
  .p-split {background:#2a2a2a;color:#aaa;}
  .p-news  {background:#1e1e1e;color:#888;}
  .client-badge{background:#0d2137;border:1px solid #1976d2;color:#64b5f6;
                padding:2px 9px;border-radius:999px;font-size:11px;font-weight:600;}
  .non-client-badge{background:#1e1e1e;border:1px solid #444;color:#888;
                    padding:2px 9px;border-radius:999px;font-size:11px;}
  .score-bar-bg{background:#1e1e1e;border-radius:4px;height:4px;margin-top:6px;}
  .card{border-radius:8px;padding:14px 16px;margin:6px 0;border:1px solid #2a2a2a;}
  .card-client{border-left:3px solid #1976d2;}
  .card-high{border-left:3px solid #d32f2f;}
  .meta{font-size:11px;color:#666;margin-top:4px;}
  .headline{font-size:14px;font-weight:500;color:#e0e0e0;margin:6px 0 4px;}
  .sub{font-size:12px;color:#888;line-height:1.5;}
  .mnc-link{font-size:12px;color:#64b5f6;}
  .score-chip{font-size:11px;font-weight:600;padding:1px 7px;border-radius:999px;}
</style>
""", unsafe_allow_html=True)


# ─── Priority scoring ─────────────────────────────────────────────────────────

def is_special_dividend(action: dict) -> bool:
    """True if dividend is irregular, large, or explicitly special."""
    h = (action.get("headline", "") + " " + action.get("raw_detail", "")).lower()
    amt = action.get("amount") or 0
    special_words = ["special", "extraordinary", "one-time", "interim",
                     "repatriat", "one time", "bumper", "enhanced"]
    if any(w in h for w in special_words):
        return True
    if amt >= 15:   # ₹15+ per share is meaningfully large for most Indian cos
        return True
    return False

ACTION_SCORES = {
    "Dividend_Special": 30,
    "M&A":              30,
    "FDI":              25,
    "Dividend":         15,
    "Buyback":          20,
    "Strategic":        10,
    "Stock Split":       5,
    "Other":             3,
}

def score_action(action: dict) -> int:
    """
    Score = client match + action urgency + exposure + recency
    Max = 40 + 30 + 20 + 10 = 100
    """
    total = 0

    # 1. Client match
    if action.get("is_scb_client"):
        total += 40

    # 2. Action urgency
    atype = action.get("action_type", "Other")
    if atype == "Dividend" and is_special_dividend(action):
        atype_key = "Dividend_Special"
    else:
        atype_key = atype
    total += ACTION_SCORES.get(atype_key, 3)

    # 3. Exposure size
    client = action.get("client") or {}
    exp = client.get("net_nih_exposure") or client.get("exposure_usd_m") or 0
    if exp >= 1000:   total += 20
    elif exp >= 500:  total += 12
    elif exp >= 100:  total += 6
    elif exp > 0:     total += 2

    # 4. Recency
    try:
        d = datetime.date.fromisoformat(action.get("date", "")[:10])
        delta = (datetime.date.today() - d).days
        if delta <= 1:    total += 10
        elif delta <= 3:  total += 7
        elif delta <= 7:  total += 4
    except Exception:
        pass

    return total

MINIMUM_SCORE = 25


# ─── Helpers ─────────────────────────────────────────────────────────────────

def action_pill(action: dict) -> str:
    atype = action.get("action_type", "Other")
    special = atype == "Dividend" and is_special_dividend(action)
    labels = {
        "Dividend":    ("p-div",   "💰 Dividend"),
        "M&A":         ("p-ma",    "🤝 M&A"),
        "FDI":         ("p-fdi",   "🌐 FDI / Capital raise"),
        "Buyback":     ("p-buy",   "🔄 Buyback"),
        "Strategic":   ("p-strat", "🔗 Strategic"),
        "Stock Split":  ("p-split", "✂️ Split"),
        "Other":       ("p-news",  "📰 News"),
    }
    cls, label = labels.get(atype, ("p-news", atype))
    if special:
        cls, label = "p-divsp", "💰 Special dividend"
    return f'<span class="pill {cls}">{label}</span>'

def client_badge(action: dict) -> str:
    if action.get("is_scb_client"):
        return '<span class="client-badge">Current client</span>'
    return '<span class="non-client-badge">Non-client</span>'

def score_color(score: int) -> str:
    if score >= 70: return "#ef5350"
    if score >= 50: return "#ffa726"
    if score >= 35: return "#42a5f5"
    return "#666"

def score_chip(score: int) -> str:
    c = score_color(score)
    return (f'<span class="score-chip" '
            f'style="background:{c}22;color:{c};border:1px solid {c}55;">'
            f'Score {score}</span>')

def source_tag(source: str) -> str:
    colors = {
        "NSE":      "#1565c0",
        "yfinance": "#2e7d32",
        "FMP":      "#6a1b9a",
        "News":     "#e65100",
    }
    c = next((v for k, v in colors.items() if k in source), "#555")
    return f'<span style="font-size:10px;font-weight:600;color:{c};">{source}</span>'


# ─── Load data ────────────────────────────────────────────────────────────────

st.markdown("""
<div class="hdr">
  <strong style="font-size:18px;">🏦 SCB — Corporate Actions Intelligence</strong><br>
  <span style="font-size:12px;opacity:0.8;">
    MNC subsidiaries from SCB FX Pipeline v7 · Prioritised by client relationship, action type, exposure and recency
  </span>
</div>
""", unsafe_allow_html=True)

with st.spinner("Loading client registry..."):
    registry = load_registry()

# Stats row
c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 1])
with c1: st.metric("Companies monitored", len(registry["all"]))
with c2: st.metric("With NSE tickers", len(registry["by_ticker"]))
with c3: st.metric("Current clients", len([r for r in registry["all"] if r.get("priority_score", 0) > 0]))
with c4: st.metric(
    "Date window",
    f"–{LOOKBACK_DAYS}d / +{LOOKAHEAD_DAYS}d",
    f"{(dt.now()-timedelta(days=LOOKBACK_DAYS)).strftime('%d %b')} → {(dt.now()+timedelta(days=LOOKAHEAD_DAYS)).strftime('%d %b')}"
)
with c5:
    if st.button("⟳ Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.divider()

with st.spinner("Fetching corporate actions from all sources..."):
    raw_actions = fetch_all_corporate_actions(registry)

# Score and filter
for a in raw_actions:
    a["_score"] = score_action(a)

actions = [a for a in raw_actions if a["_score"] >= MINIMUM_SCORE]
actions.sort(key=lambda x: x["_score"], reverse=True)

# ─── Filters ─────────────────────────────────────────────────────────────────
fc1, fc2, fc3 = st.columns([2, 2, 2])
with fc1:
    filter_rel = st.selectbox(
        "Client relationship",
        ["All", "Current clients only", "Non-clients only"]
    )
with fc2:
    atypes = ["All"] + sorted({a["action_type"] for a in actions})
    filter_type = st.selectbox("Action type", atypes)
with fc3:
    sources = ["All"] + sorted({a["source"].split("—")[0].strip() for a in actions})
    filter_src = st.selectbox("Source", sources)

def apply_filters(lst):
    if filter_rel == "Current clients only":
        lst = [a for a in lst if a["is_scb_client"]]
    elif filter_rel == "Non-clients only":
        lst = [a for a in lst if not a["is_scb_client"]]
    if filter_type != "All":
        lst = [a for a in lst if a["action_type"] == filter_type]
    if filter_src != "All":
        lst = [a for a in lst if filter_src in a["source"]]
    return lst

filtered = apply_filters(actions)
client_count    = sum(1 for a in filtered if a["is_scb_client"])
non_client_count = sum(1 for a in filtered if not a["is_scb_client"])

st.caption(
    f"**{len(filtered)} actions shown** (score ≥ {MINIMUM_SCORE}) — "
    f"**{client_count} current clients** · {non_client_count} non-clients · "
    f"{len(raw_actions) - len(actions)} below threshold hidden"
)
st.divider()

# ─── Main layout: feed + sidebar summary ─────────────────────────────────────
col_feed, col_summary = st.columns([3, 1], gap="large")

with col_feed:
    if not filtered:
        st.info("No actions meet the minimum priority threshold. Try adjusting filters or refreshing.")
    else:
        for action in filtered[:60]:
            client  = action.get("client")
            score   = action["_score"]
            is_client = action["is_scb_client"]
            special_div = (action["action_type"] == "Dividend" and is_special_dividend(action))

            card_extra = "card-client" if is_client else ("card-high" if score >= 60 else "")

            # Build header line
            pills = action_pill(action) + " " + client_badge(action) + " " + score_chip(score)

            # Client/company info line
            if client:
                info_line = (
                    f'<span style="font-size:12px;color:#ccc;">'
                    f'<strong>{client["indian_subsidiary"]}</strong>'
                    f' → <span class="mnc-link">{client["client_group"]}</span>'
                    f' &nbsp;·&nbsp; ${client.get("net_nih_exposure", 0):,.0f}M NIH'
                    f'</span>'
                )
            else:
                info_line = (
                    f'<span style="font-size:12px;color:#777;">'
                    f'{action["company_name"]}'
                    f'</span>'
                )

            # Amount display
            amt_str = ""
            if action.get("amount") and action.get("currency") == "INR":
                lbl = "Special dividend" if special_div else action["action_type"]
                amt_str = f' &nbsp;·&nbsp; <strong style="color:#a5d6a7;">₹{action["amount"]:,.2f}/share</strong>'
            elif action.get("amount") and action.get("currency") == "USD":
                amt_str = f' &nbsp;·&nbsp; <strong style="color:#90caf9;">${action["amount"]:,.0f}M</strong>'

            # Foreign entity
            fe_str = ""
            if action.get("foreign_entity"):
                fe_str = f' &nbsp;·&nbsp; <span style="color:#ffcc80;font-size:11px;">↔ {action["foreign_entity"]}</span>'

            with st.expander(
                f"{action['date']}  ·  {action['action_type']}{'  ★' if special_div else ''}  ·  {action['company_name'][:55]}",
                expanded=(score >= 65)
            ):
                st.markdown(f"""
                <div class="card {card_extra}">
                  <div>{pills}</div>
                  <div class="headline">{action['headline'][:200]}</div>
                  <div>{info_line}{amt_str}{fe_str}</div>
                  <div class="meta">
                    {source_tag(action['source'])} &nbsp;·&nbsp; {action['date']}
                    {"&nbsp;·&nbsp;<a href='" + action['url'] + "' target='_blank' style='color:#555;font-size:11px;'>source →</a>" if action.get('url') else ""}
                  </div>
                  {"<div class='sub' style='margin-top:6px;'>" + action['raw_detail'][:200] + "</div>" if action.get('raw_detail') else ""}
                </div>
                """, unsafe_allow_html=True)

with col_summary:
    # Score breakdown
    st.markdown("**Priority breakdown**")
    score_bands = [
        ("🔴 Critical  (70+)", [a for a in filtered if a["_score"] >= 70]),
        ("🟠 High      (50–69)", [a for a in filtered if 50 <= a["_score"] < 70]),
        ("🔵 Medium    (35–49)", [a for a in filtered if 35 <= a["_score"] < 50]),
        ("⚪ Low       (25–34)", [a for a in filtered if 25 <= a["_score"] < 35]),
    ]
    for label, group in score_bands:
        if group:
            st.markdown(
                f'<div style="font-size:12px;color:#ccc;margin:3px 0;">'
                f'{label} &nbsp; <strong style="color:#fff;">{len(group)}</strong></div>',
                unsafe_allow_html=True
            )

    st.divider()

    # Action type breakdown
    st.markdown("**By action type**")
    type_counts = {}
    for a in filtered:
        k = ("Special dividend" if a["action_type"] == "Dividend"
             and is_special_dividend(a) else a["action_type"])
        type_counts[k] = type_counts.get(k, 0) + 1
    for k, v in sorted(type_counts.items(), key=lambda x: -x[1]):
        st.markdown(
            f'<div style="font-size:12px;color:#aaa;margin:2px 0;">'
            f'{k} <strong style="color:#fff;">{v}</strong></div>',
            unsafe_allow_html=True
        )

    st.divider()

    # Source breakdown
    st.markdown("**By source**")
    src_counts = {}
    for a in filtered:
        s = a["source"].split("—")[0].strip()
        src_counts[s] = src_counts.get(s, 0) + 1
    for k, v in sorted(src_counts.items(), key=lambda x: -x[1]):
        st.markdown(
            f'<div style="font-size:12px;color:#aaa;margin:2px 0;">'
            f'{k} <strong style="color:#fff;">{v}</strong></div>',
            unsafe_allow_html=True
        )

    st.divider()

    # Top current client actions
    st.markdown("**Current client highlights**")
    top_clients = [a for a in filtered if a["is_scb_client"]][:6]
    if not top_clients:
        st.caption("No current client actions in this window.")
    else:
        for a in top_clients:
            c = a.get("client") or {}
            sc = score_color(a["_score"])
            st.markdown(f"""
            <div style="border:1px solid #1e3a5f;border-radius:6px;padding:8px 10px;margin-bottom:6px;">
              <div style="font-size:11px;font-weight:600;color:#64b5f6;">{c.get('client_group','')}</div>
              <div style="font-size:11px;color:#ccc;">{c.get('indian_subsidiary','')[:35]}</div>
              <div style="margin-top:4px;">{action_pill(a)}</div>
              <div style="font-size:10px;color:{sc};font-weight:600;margin-top:3px;">Score {a['_score']}</div>
            </div>
            """, unsafe_allow_html=True)

# ─── Full data table ──────────────────────────────────────────────────────────
st.divider()
with st.expander("📄 Full data table + CSV download", expanded=False):
    if filtered:
        rows = [{
            "Score":       a["_score"],
            "Date":        a["date"],
            "Action":      ("Special dividend" if a["action_type"] == "Dividend"
                            and is_special_dividend(a) else a["action_type"]),
            "Company":     a["company_name"][:40],
            "Headline":    a["headline"][:80],
            "Amount":      a.get("amount"),
            "Currency":    a.get("currency"),
            "Source":      a["source"][:30],
            "MNC Parent":  (a.get("client") or {}).get("client_group", "—"),
            "NIH Exp $M":  (a.get("client") or {}).get("net_nih_exposure"),
            "Client":      "Yes" if a["is_scb_client"] else "No",
        } for a in filtered]
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Download CSV",
            df.to_csv(index=False),
            f"scb_corp_{dt.now().strftime('%Y%m%d_%H%M')}.csv",
            "text/csv",
        )
