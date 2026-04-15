"""
groq_summarizer.py
------------------
Uses Groq (free, Llama 3) to generate a daily briefing from
the top-scoring corporate actions of the day.

Only called once per session (cached). Only fires for actions scoring 50+.
Falls back gracefully if no key is set.
"""

import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


SYSTEM_PROMPT = """You are a senior financial markets analyst at Standard Chartered Bank.
Your job is to write a concise daily briefing for the FX sales desk based on corporate actions 
detected across MNC subsidiaries in India.

Rules:
- Maximum 5 bullet points
- Each bullet: one corporate action + its FX implication in plain English
- Lead with the most FX-significant event
- Mention the MNC parent and currency pair where relevant
- Flag if an action is unusual or larger than typical
- No fluff, no disclaimers, no greetings
- Write as if briefing a senior RM who has 60 seconds to read this
- Format: use • for bullets, bold the company name with **Company**"""


def _build_prompt(actions: list) -> str:
    """Build the user prompt from top actions."""
    lines = []
    for a in actions[:12]:   # send top 12 to AI
        client = a.get("client") or {}
        mnc    = client.get("client_group", "Unknown MNC")
        sub    = client.get("indian_subsidiary", a.get("company_name", ""))
        exp    = client.get("net_nih_exposure", 0) or 0
        atype  = a.get("action_type", "")
        amt    = f"₹{a['amount']:.2f}/share" if a.get("amount") and a.get("currency") == "INR" else ""
        score  = a.get("_score", 0)
        is_client = "SCB CLIENT" if a.get("is_scb_client") else "non-client"

        lines.append(
            f"[Score {score} | {is_client}] {atype}: {sub} (parent: {mnc}) "
            f"| NIH exposure: ${exp:,.0f}M | {amt} | {a.get('headline', '')[:100]}"
        )

    return (
        f"Today's top corporate actions ({len(lines)} items):\n\n"
        + "\n".join(lines)
        + "\n\nWrite the daily FX desk briefing."
    )


@st.cache_data(ttl=1800)   # cache 30 minutes
def generate_daily_briefing(action_snapshot: tuple) -> str:
    """
    action_snapshot is a tuple of (score, action_type, headline, company) tuples
    — used as cache key. Returns briefing text or empty string.
    """
    if not GROQ_API_KEY:
        return ""

    # Reconstruct minimal action dicts from snapshot for prompt building
    actions = [
        {
            "_score":        s[0],
            "action_type":   s[1],
            "headline":      s[2],
            "company_name":  s[3],
            "amount":        s[4],
            "currency":      s[5],
            "is_scb_client": s[6],
            "client":        {"client_group": s[7], "indian_subsidiary": s[8],
                              "net_nih_exposure": s[9]},
        }
        for s in action_snapshot
    ]

    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": _build_prompt(actions)},
            ],
            temperature=0.3,
            max_tokens=600,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"_Briefing unavailable: {e}_"


def make_snapshot(actions: list) -> tuple:
    """
    Convert actions list to a hashable tuple for st.cache_data.
    Only include actions scoring 50+ (the ones worth summarising).
    """
    top = sorted(
        [a for a in actions if a.get("_score", 0) >= 50],
        key=lambda x: x["_score"], reverse=True
    )[:12]

    return tuple(
        (
            a.get("_score", 0),
            a.get("action_type", ""),
            a.get("headline", "")[:100],
            a.get("company_name", ""),
            a.get("amount"),
            a.get("currency"),
            a.get("is_scb_client", False),
            (a.get("client") or {}).get("client_group", ""),
            (a.get("client") or {}).get("indian_subsidiary", ""),
            (a.get("client") or {}).get("net_nih_exposure", 0) or 0,
        )
        for a in top
    )
