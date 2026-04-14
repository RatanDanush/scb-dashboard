"""
app.py
------
Main dashboard. Run this with: streamlit run app.py

Layout:
┌─────────────────────────────────────────────────────┐
│  Header + last updated time + refresh button        │
├─────────────────────────────────────────────────────┤
│  ALERTS  — high urgency recommendations             │
├───────────────────────┬─────────────────────────────┤
│  LIVE NEWS FEED       │  PRODUCT RECOMMENDATIONS    │
│  (left column)        │  (right column)             │
├───────────────────────┴─────────────────────────────┤
│  DAILY BRIEFING CARD  — top 3 signals today         │
└─────────────────────────────────────────────────────┘
"""

import streamlit as st
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

from news_fetcher import fetch_all_news
from trend_detector import detect_trends
from ai_recommender import get_ai_recommendations, GROQ_AVAILABLE
from config import REFRESH_INTERVAL_MS, MAX_ARTICLES_SHOWN

# ─── PAGE SETUP ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SCB FM Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Auto-refresh every 15 minutes (900,000 ms)
st_autorefresh(interval=REFRESH_INTERVAL_MS, limit=None, key="auto_refresh")

# ─── STYLING ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Alert boxes */
    .alert-high   { background:#fff0f0; border-left:4px solid #d32f2f;
                    padding:10px 14px; border-radius:4px; margin:6px 0; }
    .alert-medium { background:#fff8e1; border-left:4px solid #f9a825;
                    padding:10px 14px; border-radius:4px; margin:6px 0; }
    .alert-low    { background:#f1f8e9; border-left:4px solid #558b2f;
                    padding:10px 14px; border-radius:4px; margin:6px 0; }

    /* Recommendation cards */
    .rec-card { background:#f8f9fa; padding:14px; border-radius:8px;
                margin:8px 0; border:1px solid #e0e0e0; }
    .rec-pitch { font-style:italic; color:#444; margin:6px 0; }

    /* Briefing card */
    .brief-card { background:#e8f4fd; padding:14px; border-radius:8px;
                  border:1px solid #90caf9; height:100%; }
    .brief-title { font-weight:600; font-size:14px; color:#1565c0; margin-bottom:6px; }

    /* News item */
    .news-source { font-size:11px; color:#888; margin-bottom:2px; }

    /* Header strip */
    .header-bar { background:#002f6c; color:white; padding:12px 20px;
                  border-radius:8px; margin-bottom:16px; }
</style>
""", unsafe_allow_html=True)


# ─── HELPER FUNCTIONS ────────────────────────────────────────────────────────

def urgency_badge(urgency: str) -> str:
    icons = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}
    return icons.get(urgency, "⚪")


def urgency_css_class(urgency: str) -> str:
    return {"High": "alert-high", "Medium": "alert-medium", "Low": "alert-low"}.get(urgency, "alert-low")


# ─── HEADER ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="header-bar">
    <strong style="font-size:18px;">📊 SCB Financial Markets — Intelligence Dashboard</strong><br>
    <span style="font-size:12px;opacity:0.8;">
        Scanning financial news and recommending products for the sales team
    </span>
</div>
""", unsafe_allow_html=True)

col_time, col_ai_status, col_refresh = st.columns([3, 2, 1])
with col_time:
    st.caption(f"Last updated: {datetime.now().strftime('%d %b %Y, %H:%M:%S')}  |  Auto-refreshes every 15 min")
with col_ai_status:
    if GROQ_AVAILABLE:
        st.caption("🤖 AI recommendations: ON (Groq / Llama 3)")
    else:
        st.caption("⚙️ AI recommendations: Rule-based (set GROQ_API_KEY to enable)")
with col_refresh:
    if st.button("⟳ Refresh now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.divider()


# ─── DATA LOADING ────────────────────────────────────────────────────────────
with st.spinner("Scanning news feeds..."):
    articles = fetch_all_news()

if not articles:
    st.error("No articles could be fetched. Check your internet connection.")
    st.stop()

with st.spinner("Detecting market trends..."):
    trends = detect_trends(articles)

with st.spinner("Generating product recommendations..."):
    recommendations = get_ai_recommendations(trends, articles[:10])


# ─── ALERTS SECTION ──────────────────────────────────────────────────────────
high_priority = [r for r in recommendations if r.get("urgency") == "High"]

if high_priority:
    st.subheader("🔴 High Priority Alerts")
    alert_cols = st.columns(min(len(high_priority), 3))
    for i, rec in enumerate(high_priority[:3]):
        with alert_cols[i]:
            st.markdown(f"""
            <div class="alert-high">
                <strong>{rec['product']}</strong><br>
                <small>{rec['trend']}</small><br>
                <small style="color:#555;">Target: <em>{rec['client_segment']}</em></small>
            </div>
            """, unsafe_allow_html=True)
    st.divider()


# ─── MAIN COLUMNS: NEWS FEED + RECOMMENDATIONS ───────────────────────────────
col_news, col_recs = st.columns([1, 1], gap="large")

# LEFT COLUMN — Live news feed
with col_news:
    st.subheader(f"📰 Live News Feed  ({len(articles)} articles)")

    # Filter by trend relevance toggle
    show_all = st.toggle("Show all articles", value=False,
                         help="Off = only articles matching a detected trend")

    # Build a set of titles that matched at least one trend
    trend_matched_titles = set()
    for trend in trends:
        for headline in trend.get("matching_headlines", []):
            trend_matched_titles.add(headline)

    shown = 0
    for article in articles[:MAX_ARTICLES_SHOWN]:
        is_relevant = article["title"] in trend_matched_titles

        if not show_all and not is_relevant:
            continue

        with st.expander(
            f"{'🔸' if is_relevant else '  '} {article['title'][:90]}",
            expanded=False
        ):
            st.markdown(f"<div class='news-source'>{article['source']}  |  {article['published'][:16]}</div>",
                        unsafe_allow_html=True)
            if article.get("summary"):
                st.write(article["summary"][:280] + "...")
            if article.get("link"):
                st.markdown(f"[Read full article →]({article['link']})")

        shown += 1

    if shown == 0:
        st.info("No trend-relevant articles found. Toggle 'Show all articles' to see everything.")


# RIGHT COLUMN — Product recommendations
with col_recs:
    st.subheader(f"💡 Recommendations  ({len(recommendations)} signals)")

    if not recommendations:
        st.info("No strong signals detected yet in today's news. Check back after the next refresh.")
    else:
        for rec in recommendations:
            badge = urgency_badge(rec.get("urgency", "Low"))
            urgency = rec.get("urgency", "Low")

            with st.expander(
                f"{badge} {rec['product']}  —  {rec['client_segment']}",
                expanded=(urgency == "High")   # Auto-expand high urgency only
            ):
                # Trend tag
                st.markdown(f"**Trend detected:** {rec['trend']}")

                # Why now
                st.markdown(f"**Why today:** {rec['why_now']}")

                # Pitch — styled differently
                st.markdown(f"""
                <div class="rec-pitch">
                    💬 <em>"{rec['pitch_angle']}"</em>
                </div>
                """, unsafe_allow_html=True)

                # SC edge
                st.markdown(f"**SC edge:** {rec['sc_edge']}")

                # Urgency chip
                colors = {"High": "#d32f2f", "Medium": "#f57c00", "Low": "#388e3c"}
                color = colors.get(urgency, "#888")
                st.markdown(f"<small style='color:{color};font-weight:600;'>● {urgency} urgency</small>",
                            unsafe_allow_html=True)


# ─── DAILY BRIEFING CARD ─────────────────────────────────────────────────────
st.divider()
st.subheader("📋 Daily Briefing Card")
st.caption("Top 3 signals for the sales team today — print-ready")

if recommendations:
    brief_cols = st.columns(3)
    for i, rec in enumerate(recommendations[:3]):
        with brief_cols[i]:
            st.markdown(f"""
            <div class="brief-card">
                <div class="brief-title">{urgency_badge(rec.get('urgency','Low'))} {rec['product']}</div>
                <div style="font-size:12px;color:#555;margin-bottom:8px;">{rec['trend']}</div>
                <div style="font-size:12px;margin-bottom:6px;">
                    <strong>Target:</strong> {rec['client_segment']}
                </div>
                <div style="font-size:12px;font-style:italic;color:#333;">
                    "{rec['pitch_angle']}"
                </div>
            </div>
            """, unsafe_allow_html=True)
else:
    st.info("Briefing card will populate once recommendations are generated.")


# ─── DETECTED TRENDS SUMMARY (sidebar / bottom) ──────────────────────────────
st.divider()
with st.expander("🔍 Detected trends breakdown (debug view)", expanded=False):
    if trends:
        import pandas as pd
        trend_df = pd.DataFrame([{
            "Trend":     t["trend_name"].replace("_", " ").title(),
            "Urgency":   t["urgency"],
            "Articles":  t["article_count"],
            "Keywords":  ", ".join(t["matched_keywords"][:5]),
            "Products":  ", ".join(t["product_hints"]),
        } for t in trends])
        st.dataframe(trend_df, use_container_width=True, hide_index=True)
    else:
        st.write("No trends detected in current news batch.")
