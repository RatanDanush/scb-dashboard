# snapshot_page.py
# FX Snapshot tab — drop this file into your project root.
# Called from app.py with a single function: render_snapshot_tab()

import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime

# ── lazy imports so startup isn't slowed down ─────────────────────────────────

def _get_api_key():
    """Read Gemini key from secrets or session state."""
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return st.session_state.get("gemini_key", "")


def render_snapshot_tab():
    """Render the full FX Snapshot Generator tab."""

    # ── match existing dark theme ──────────────────────────────────────────────
    st.markdown("""
    <style>
    .snap-header{
        background:#000;border-bottom:2px solid #c8a84b;
        padding:8px 12px;display:flex;align-items:center;
        justify-content:space-between;margin-bottom:0;
    }
    .snap-title{font-size:13px;font-weight:700;color:#e8e8e8;letter-spacing:.08em;}
    .snap-sub{font-size:9px;color:#3a3a3a;letter-spacing:.05em;}
    .snap-btn-row{display:flex;gap:10px;margin:12px 0;}
    .snap-note{font-size:11px;color:#37474f;margin-top:6px;}
    .snap-warn{background:#0a0800;border:1px solid #3a2800;border-radius:3px;
               padding:6px 10px;font-size:10px;color:#c8a84b;margin-top:8px;}
    </style>
    """, unsafe_allow_html=True)

    # ── Header bar (matches Bloomberg style of existing app) ──────────────────
    st.markdown("""
    <div class="snap-header">
      <div>
        <span class="snap-title">📊 FX SNAPSHOT GENERATOR</span>
        <span class="snap-sub">&nbsp;·&nbsp; WEEKLY &amp; DAILY · INDIA FM SALES</span>
      </div>
      <div style="font-size:9px;color:#3a3a3a;font-family:monospace;">
        POWERED BY GEMINI AI + YFINANCE
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── API key ────────────────────────────────────────────────────────────────
    api_key = _get_api_key()

    if not api_key:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        with st.expander("🔑 Gemini API Key required", expanded=True):
            st.caption(
                "Get a free key at [aistudio.google.com](https://aistudio.google.com). "
                "Or add `GEMINI_API_KEY` to `.streamlit/secrets.toml` to skip this step permanently."
            )
            key_input = st.text_input(
                "Paste Gemini API key",
                type="password",
                placeholder="AIza...",
                label_visibility="collapsed"
            )
            if key_input:
                st.session_state["gemini_key"] = key_input
                api_key = key_input
                st.success("Key saved for this session.", icon="✅")
    else:
        st.markdown(
            '<div style="font-size:10px;color:#2e7d32;padding:4px 0;">● Gemini API key loaded</div>',
            unsafe_allow_html=True
        )

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # ── Generate buttons ───────────────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:9px;font-weight:700;color:#3a3a3a;'
        'letter-spacing:.12em;padding-bottom:6px;border-bottom:1px solid #181818;'
        'margin-bottom:10px;">SELECT SNAPSHOT TYPE</div>',
        unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns([2, 2, 3])
    with col1:
        gen_weekly = st.button(
            "📅 Weekly Snapshot",
            use_container_width=True,
            type="primary",
            help="Mon–Fri of last completed week · 3 AI macro stories"
        )
    with col2:
        gen_daily = st.button(
            "🗓 Daily Snapshot",
            use_container_width=True,
            help="Last 24h price action · 2 AI macro stories"
        )
    with col3:
        st.markdown(
            '<div style="font-size:10px;color:#37474f;padding:8px 0;">'
            'Weekly: Mon–Fri of the most recently completed week · '
            'Daily: last completed trading session'
            '</div>',
            unsafe_allow_html=True
        )

    # ── Data sources note ─────────────────────────────────────────────────────
    # NOTE: never use `with st.sidebar:` inside a tab block — it corrupts
    # Streamlit's rendering context and makes all subsequent tab content blank.
    with st.expander("📋 Data sources", expanded=False):
        st.markdown("""
| Data | Source |
|---|---|
| USD/INR, G3, DXY | Yahoo Finance |
| US 10Y | Yahoo Finance |
| India 10Y | Yahoo Finance |
| Brent, Gold | Yahoo Finance |
| Macro stories | Gemini + Google Search |
        """)
        st.caption(
            "⚠ Fed Funds + RBI Repo are hardcoded — "
            "update manually in `data_fetcher.py` when rates change."
        )

    # ── Generation logic ───────────────────────────────────────────────────────
    if gen_weekly or gen_daily:

        if not api_key:
            st.error("Please enter a Gemini API key above.", icon="⚠️")
            return

        mode = "weekly" if gen_weekly else "daily"

        # Import here so app startup is not slowed
        try:
            from data_fetcher import get_weekly_data, get_daily_data
            from macro_generator import get_weekly_stories, get_week_ahead, get_daily_stories
            from html_generator import generate_weekly_html, generate_daily_html
        except ImportError as e:
            st.error(
                f"Missing module: {e}. "
                "Make sure data_fetcher.py, macro_generator.py and html_generator.py "
                "are in the same folder as app.py.",
                icon="❌"
            )
            return

        # Progress steps — styled dark to match dashboard
        progress_html = lambda msg, done=False: st.markdown(
            f'<div style="font-size:11px;color:{"#43a047" if done else "#546e7a"};'
            f'font-family:monospace;padding:2px 0;">'
            f'{"✓" if done else "·"} {msg}</div>',
            unsafe_allow_html=True
        )

        with st.status(f"Generating {mode} snapshot…", expanded=True) as status:

            # Step 1: market data
            st.write("📡 Fetching market data from Yahoo Finance…")
            try:
                data = get_weekly_data() if mode == "weekly" else get_daily_data()
                n_ok = len([v for v in data.values() if v != "N/A"])
                st.write(f"✅ Market data ready — {n_ok} data points loaded")
            except Exception as e:
                st.error(f"Market data fetch failed: {e}")
                return

            # Step 2: macro stories
            st.write("🤖 Generating macro stories via Gemini + Google Search…")
            try:
                if mode == "weekly":
                    stories = get_weekly_stories(
                        api_key,
                        data.get("week_start", ""),
                        data.get("week_end", ""),
                        data.get("week_num", "")
                    )
                else:
                    stories = get_daily_stories(api_key, data.get("date", ""))
                st.write(f"✅ {len(stories)} macro stories generated")
            except Exception as e:
                st.warning(f"Macro stories failed ({e}) — using placeholder.", icon="⚠️")
                stories = []

            # Step 3: week ahead (weekly only)
            week_ahead = []
            if mode == "weekly":
                st.write("📆 Finding week-ahead events…")
                try:
                    week_ahead = get_week_ahead(api_key, data.get("week_end", ""))
                    st.write(f"✅ {len(week_ahead)} upcoming events identified")
                except Exception as e:
                    st.write(f"⚠️ Week-ahead skipped ({e})")

            # Step 4: build HTML
            st.write("🏗 Building HTML snapshot…")
            try:
                if mode == "weekly":
                    html = generate_weekly_html(data, stories, week_ahead)
                else:
                    html = generate_daily_html(data, stories)
                st.write(f"✅ HTML ready · {len(html):,} chars")
            except Exception as e:
                st.error(f"HTML generation failed: {e}")
                return

            status.update(label="✅ Snapshot ready", state="complete", expanded=False)

        # ── Preview ──────────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown(
            '<div style="font-size:9px;font-weight:700;color:#3a3a3a;'
            'letter-spacing:.12em;padding-bottom:6px;border-bottom:1px solid #181818;'
            'margin-bottom:10px;">PREVIEW</div>',
            unsafe_allow_html=True
        )
        st.caption(
            "Scroll within the preview · Download to open in browser or paste into Outlook/Gmail"
        )
        components.html(html, height=680, scrolling=True)

        # ── Download ──────────────────────────────────────────────────────────
        st.markdown("---")
        if mode == "weekly":
            fname = f"stanc_weekly_w{data.get('week_num','')}_{data.get('year','')}.html"
        else:
            fname = f"stanc_daily_{datetime.now().strftime('%Y%m%d')}.html"

        st.download_button(
            label="⬇️  Download HTML",
            data=html.encode("utf-8"),
            file_name=fname,
            mime="text/html",
            use_container_width=True,
            type="primary"
        )

        st.markdown(
            '<div class="snap-warn">'
            '⚑ How to distribute: Download → open in browser to verify → '
            'paste into Outlook (Insert HTML) or Gmail, or attach the .html file directly.'
            '</div>',
            unsafe_allow_html=True
        )
