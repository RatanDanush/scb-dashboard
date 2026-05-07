"""
gemini_engine.py
----------------
Gemini 2.0 Flash — replaces the broken Groq web_search tool.

Why Gemini:
  - Groq's tools[{"type": "web_search"}] is deprecated (400 error)
  - Gemini has native Google Search grounding — reads full articles
  - Free tier: 1,500 RPD / 15 RPM — covers all 390 clients/day

Functions:
  1. web_search_client()  — per-client grounded web search (replaces Groq batch)
  2. daily_briefing()     — FX desk summary (better synthesis than Groq 70b)
  3. deep_dive_search()   — 12-month grounded history (replaces deep_dive RSS + Groq)
"""

import os, re, json, requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-2.0-flash"
_BASE_URL      = "https://generativelanguage.googleapis.com/v1beta/models"


# ─── System prompts ──────────────────────────────────────────────────────────

WEB_SEARCH_SYSTEM = """You are a corporate intelligence analyst at Standard Chartered Bank India.
Search for recent corporate actions involving the given company.

Focus ONLY on events that create cross-border INR FX flows:
- Foreign parent investing in / acquiring Indian subsidiary
- Indian subsidiary paying dividends to foreign parent (repatriation)
- M&A deals where foreign entity acquires Indian company
- Capital raises, rights issues, ECB borrowings
- Large strategic investments with foreign funding component
- Joint ventures with foreign partners involving capital flows

SKIP:
- Pure domestic Indian M&A with no foreign angle
- Operational news, product launches, hiring
- Events older than 12 months
- Analyst ratings, price targets, share price movements

Return JSON array (max 8 items):
[{
  "date": "YYYY-MM-DD or YYYY-MM",
  "event_date": "actual event date, not report date",
  "action_type": "M&A|FDI|Dividend|Strategic|IPO|Buyback|Other",
  "headline": "clean one-line description",
  "fx_implication": "one sentence — currency pair + SC product opportunity",
  "significance": "High|Medium|Low",
  "inr_involved": true|false,
  "deal_value": "e.g. $420M or Rs 3200cr or null",
  "counterparty": "name or null",
  "source_url": "article URL if found, else null"
}]

Return ONLY valid JSON array. No other text."""


BRIEFING_SYSTEM = """You are a senior financial markets analyst at Standard Chartered Bank.
Write a concise daily briefing for the FX sales desk.

Rules:
- Maximum 5 bullet points
- Format: • **Company Name** (Parent) — action — FX implication — SC product
- Infer currency pairs from company names (e.g. Siemens India = EUR/INR)
- Lead with highest FX-significance event
- Flag large or unusual events explicitly
- Mention NIH exposure where >$500M
- No fluff, no sign-off
- Only include events with clear INR cross-border angle"""


DEEP_DIVE_SYSTEM = """You are a senior financial markets analyst at Standard Chartered Bank.

Search for all corporate actions for the given company over the past 12 months.
Read the actual news articles to find deal values, counterparties, and exact dates.

Extract ONLY events with FX or financial markets implications:
- M&A where Indian entity is acquirer or target with cross-border element
- FDI: foreign parent investing fresh capital into Indian subsidiary
- Dividends declared BY the Indian subsidiary (creates INR → foreign currency flow)
- Capital raises: rights issues, QIP, preferential allotment with foreign participation
- ECB borrowings or foreign currency bonds
- Strategic JVs involving capital flows with foreign partners
- SEBI open offer triggers from upstream ownership changes

SKIP: product launches, CSR, awards, routine operational news, domestic India-India deals

Return JSON array (max 15 items):
[{
  "date": "YYYY-MM-DD or YYYY-MM",
  "action_type": "Dividend|M&A|FDI|Buyback|Strategic|IPO|Delisting|Restructuring|Other",
  "headline": "clean one-line description",
  "fx_implication": "one sentence on FX implication for Standard Chartered",
  "significance": "High|Medium|Low",
  "source_url": "article URL if found, else null"
}]

Return ONLY valid JSON array. No other text."""


# ─── Core REST API call ───────────────────────────────────────────────────────

def _call(system: str, user: str,
          use_search: bool = True,
          max_tokens: int  = 2000) -> str:
    """
    Single Gemini API call via REST.
    use_search=True enables Google Search grounding — reads full web articles.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set — add to Streamlit secrets")

    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents":           [{"parts": [{"text": user}], "role": "user"}],
        "generationConfig": {
            "temperature":     0.1,
            "maxOutputTokens": max_tokens,
        },
    }

    if use_search:
        payload["tools"] = [{"google_search": {}}]

    url  = f"{_BASE_URL}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    resp = requests.post(url, json=payload, timeout=45)

    if resp.status_code == 429:
        raise ValueError(
            "Gemini rate limit hit (15 RPM). "
            "Batch will continue on next cycle."
        )

    resp.raise_for_status()
    data  = resp.json()
    parts = (data.get("candidates", [{}])[0]
                 .get("content", {})
                 .get("parts", []))
    text  = "".join(p.get("text", "") for p in parts).strip()

    if not text:
        # Check for safety block or empty grounding result
        finish = (data.get("candidates", [{}])[0]
                      .get("finishReason", "UNKNOWN"))
        raise ValueError(f"Gemini returned empty response (finishReason: {finish})")

    return text


# ─── JSON helpers ─────────────────────────────────────────────────────────────

def _parse_json(text: str):
    """Strip markdown fences and parse JSON array from Gemini response."""
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$",          "", text, flags=re.MULTILINE)
    # Gemini sometimes returns JSON inside prose — extract the array
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    return json.loads(text.strip())


def _parse_amount(text: str):
    """Extract numeric deal value from strings like '$420M', 'Rs 3200cr'."""
    if not text:
        return None
    for pat, mult in [
        (r"([\d,\.]+)\s*(?:bn|billion)",      1000),
        (r"([\d,\.]+)\s*(?:mn|million|M\b)",  1),
        (r"([\d,\.]+)\s*(?:cr|crore)",        1),
    ]:
        m = re.search(pat, text, re.I)
        if m:
            try: return float(m.group(1).replace(",", "")) * mult
            except: pass
    m = re.search(r"[\$₹]\s*([\d,\.]+)", text)
    if m:
        try: return float(m.group(1).replace(",", ""))
        except: pass
    return None


# ─── 1. Web search (replaces broken Groq web_search_client) ──────────────────

def web_search_client(rec: dict) -> list:
    """
    Gemini-powered grounded web search for a specific client.

    Key improvement over Groq:
    - Google Search grounding reads full articles (not just RSS snippets)
    - Extracts actual deal values, counterparties, dates from article bodies
    - Returns search + classify + fx_implication in one call
    - Covers all 390 clients within Gemini's 1,500 RPD free limit

    Returns list of event dicts — same schema as Groq version for drop-in
    compatibility with batch_manager and get_all_cached_events.
    """
    if not GEMINI_API_KEY:
        return []

    sub    = rec.get("indian_subsidiary", "") or ""
    grp    = rec.get("client_group",       "") or ""
    exp    = rec.get("net_nih_exposure",   0)  or 0
    sector = rec.get("sector",             "") or ""

    user_msg = (
        f"Company: {sub}\n"
        f"MNC Parent: {grp}\n"
        f"Sector: {sector}\n"
        f"NIH Exposure: ${exp:,.0f}M\n\n"
        f"Search for corporate actions involving {sub} or its parent {grp} in India "
        f"in the last 12 months. Read actual articles to extract deal values, "
        f"counterparty names, and exact dates. Focus only on events that create "
        f"cross-border INR FX flows. Return as JSON array."
    )

    try:
        from token_tracker import client_already_searched, record_usage

        client_key = f"{grp}|{sub}"
        if client_already_searched(client_key):
            return []

        raw = _call(WEB_SEARCH_SYSTEM, user_msg, use_search=True)
        if not raw.strip():
            return []

        events = _parse_json(raw)
        if not isinstance(events, list):
            return []

        # Record nominal tokens to keep client deduplication working in token_tracker
        # Gemini doesn't count against Groq token budget — this is just for tracking
        record_usage("web_search", 1200, client_key)

        results = []
        for ev in events:
            if not ev.get("inr_involved", True):
                continue
            results.append({
                "company_name":   sub[:60],
                "ticker":         rec.get("ticker"),
                "action_type":    ev.get("action_type", "Other"),
                "headline":       ev.get("headline", "")[:200],
                "date":           str(ev.get("event_date") or ev.get("date", ""))[:10],
                "amount":         _parse_amount(str(ev.get("deal_value", "") or "")),
                "currency":       "USD",
                "source":         "Gemini web search",
                "raw_detail":     ev.get("fx_implication", "")[:300],
                "url":            ev.get("source_url",    "") or "",
                "foreign_entity": ev.get("counterparty"),
                "_significance":  ev.get("significance", "Medium"),
                "_inr_involved":  True,
                "_pre_matched":   rec,
            })
        return results

    except Exception as ex:
        print(f"  Gemini web search error {sub[:30]}: {ex}")
        return []


# ─── 2. Daily briefing ────────────────────────────────────────────────────────

@st.cache_data(ttl=1800)
def daily_briefing(action_snapshot: tuple) -> str:
    """
    Generate FX desk daily briefing.
    Same interface as groq_engine.daily_briefing — drop-in replacement.
    """
    if not GEMINI_API_KEY or not action_snapshot:
        return ""
    try:
        lines = []
        for s in action_snapshot:
            score, atype, hl, co, amt, curr, is_client, grp, sub, nih = s
            tag     = "SCB CLIENT" if is_client else "non-client"
            amt_str = (f"₹{amt:.2f}/sh" if amt and curr == "INR"
                       else f"${amt:.0f}M" if amt else "")
            lines.append(
                f"[Score {score}|{tag}] {atype}: {sub} (parent:{grp}) "
                f"NIH:${nih:,.0f}M {amt_str} — {hl[:100]}"
            )
        user_msg = (
            f"Today's top {len(lines)} corporate actions (INR-relevant only):\n\n"
            + "\n".join(lines)
            + "\n\nWrite the daily FX desk briefing."
        )
        return _call(BRIEFING_SYSTEM, user_msg, use_search=False, max_tokens=600)
    except Exception as ex:
        return f"_Briefing unavailable: {ex}_"


# ─── 3. Deep dive search ─────────────────────────────────────────────────────

def deep_dive_search(client_group: str, indian_subsidiary: str) -> list:
    """
    Gemini-powered deep dive: one grounded call replaces the old two-step
    (RSS fetch → Groq extraction). Reads full articles for better data quality.

    Returns list of event dicts with date, action_type, headline,
    fx_implication, significance, source_url.
    """
    if not GEMINI_API_KEY:
        return []

    user_msg = (
        f"Company: {indian_subsidiary}\n"
        f"MNC Parent: {client_group}\n\n"
        f"Search for all significant corporate actions involving {indian_subsidiary} "
        f"or its parent {client_group} in India over the last 12 months. "
        f"Read the actual news articles to find deal values, counterparties, "
        f"and exact dates. Focus on events with cross-border INR FX implications. "
        f"Return JSON array only."
    )

    try:
        raw    = _call(DEEP_DIVE_SYSTEM, user_msg, use_search=True, max_tokens=3000)
        events = _parse_json(raw)
        return events if isinstance(events, list) else []
    except Exception as ex:
        print(f"  Gemini deep dive error: {ex}")
        return []
