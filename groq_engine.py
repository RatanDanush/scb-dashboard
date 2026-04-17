"""
groq_engine.py  v2
------------------
All Groq interactions in one place.

Functions:
  1. batch_classify()      — classify + INR filter + India-India check
  2. fx_implication()      — one-line FX implication per card
  3. is_noise()            — filter irrelevant items
  4. web_search_client()   — Groq web search for a client
  5. daily_briefing()      — FX desk summary
  6. check_inr_relevance() — standalone INR check for a single item
"""

import os, re, json, time
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


# ─── Prompts ─────────────────────────────────────────────────────────────────

CLASSIFIER_SYSTEM = """You are a financial news classifier for Standard Chartered Bank India.
You classify headlines and apply strict relevance filters for the FX desk.

For each headline return a JSON object with:
{
  "action_type": "M&A" | "FDI" | "Dividend" | "Buyback" | "Strategic" | "IPO" | "Delisting" | "Restructuring" | "Other",
  "confidence": "high" | "medium" | "low",
  "is_india_relevant": true | false,
  "inr_involved": true | false,
  "skip_india_india": true | false,
  "is_indian_subsidiary_dividend": true | false,
  "foreign_entity": "counterparty name or null",
  "deal_value_usd_m": number or null,
  "is_significant": true | false,
  "event_date": "YYYY-MM-DD or YYYY-MM or null"
}

CRITICAL RULES — apply these strictly:

inr_involved = true ONLY if the transaction creates a cross-border INR flow:
  - Foreign MNC → Indian company (FDI, acquisition, funding) ✅
  - Indian company → foreign parent (dividend repatriation, royalty) ✅
  - Foreign company acquiring Indian company (deal settlement involves INR) ✅
  - Indian subsidiary funded by foreign parent ECB ✅
  - Indian conglomerate acquiring using foreign currency bonds ✅
  - Any cross-border capital flow touching India ✅
  - Purely domestic Indian deal with no foreign funding or cross-border element ❌
  - Global deal that only mentions India in passing ❌

skip_india_india = true if:
  - Both the acquirer AND target are Indian domestic entities
  - No foreign parent, no ECB, no cross-border funding element
  - Pure domestic M&A with no FX angle
  EXCEPTION: keep (skip=false) if Indian company uses foreign currency bonds,
  ECB proceeds, or foreign parent funding to make the acquisition

is_indian_subsidiary_dividend = true ONLY if:
  - The dividend is declared BY an Indian company/subsidiary
  - The dividend will flow TO a foreign parent (creates INR→foreign currency repatriation)
  - NOT: a foreign parent declaring dividend to all shareholders
  - NOT: a global dividend announcement that incidentally includes Indian operations

event_date: extract the actual date the EVENT occurred (not when reported).
  Look for phrases like "signed on", "announced on", "effective from", "declared on".
  If only a month/year is clear, use YYYY-MM format.

Return ONLY a valid JSON array of objects, one per headline. No other text."""

FX_IMPLICATION_SYSTEM = """You are an FX salesperson at Standard Chartered Bank India.
Write EXACTLY ONE sentence (max 35 words) on the cross-border FX opportunity.

Be specific:
- Name the exact currency pair (e.g. INR→EUR, USD→INR, JPY→INR)
- Name the SC product (FX Forward, PrismFX, Cross-Currency Swap, NDF, FX Option)
- Infer parent currency from company name/country (Siemens=EUR, Maruti/Suzuki=JPY,
  HUL/Unilever=GBP, Nestle=CHF, ABB=CHF, Bosch=EUR, Hyundai=KRW, Samsung=KRW)

Good examples:
"Bosch dividend repatriation creates ₹→EUR flow for Bosch GmbH — FX Forward to lock conversion rate."
"ABB India capital raise brings CHF→INR inflow from ABB Switzerland — PrismFX for conversion."
"Siemens stake deal triggers EUR→INR FDI flow — Cross-Currency Swap to hedge translation exposure."

Return ONLY the sentence. No quotes, no preamble."""

NOISE_FILTER_SYSTEM = """You are a relevance filter for Standard Chartered Bank India FX desk.
Given a headline and the client it relates to, answer: is this relevant?

Return JSON: {"relevant": true|false, "reason": "brief phrase"}

NOT relevant:
- Generic industry news mentioning company in passing
- Product launches, awards, CSR, marketing campaigns
- Operational news with no financial/capital markets angle
- Clearly about a different company with similar name

RELEVANT:
- M&A, capital raises, stake changes, dividends, restructuring
- Foreign parent involvement in India operations
- Significant capex with cross-border funding

Return ONLY valid JSON."""

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

Return JSON array (max 8 items):
[{
  "date": "YYYY-MM-DD or YYYY-MM",
  "event_date": "actual event date, not report date",
  "action_type": "M&A|FDI|Dividend|Strategic|IPO|Buyback|Other",
  "headline": "clean one-line description",
  "fx_implication": "one sentence — currency pair + SC product",
  "significance": "High|Medium|Low",
  "inr_involved": true|false,
  "deal_value": "e.g. $420M or ₹3200cr or null",
  "counterparty": "name or null",
  "source_url": "article URL if found, else null"
}]

Return ONLY valid JSON array. No other text."""

BRIEFING_SYSTEM = """You are a senior financial markets analyst at Standard Chartered Bank.
Write a concise daily briefing for the FX sales desk.

Rules:
- Maximum 5 bullet points
- Format: • **Company Name** (Parent) — action — FX implication — SC product
- Infer currency pairs from company names
- Lead with highest FX-significance event
- Flag large or unusual events explicitly
- Mention NIH exposure where >$500M
- No fluff, no sign-off
- Only include events with clear INR cross-border angle"""


# ─── Groq helpers ────────────────────────────────────────────────────────────

def _client():
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set")
    from groq import Groq
    return Groq(api_key=GROQ_API_KEY)

def _call(system: str, user: str, model="llama-3.3-70b-versatile",
          max_tokens=1200, temperature=0.1) -> str:
    c = _client()
    resp = c.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()

def _parse_json(text: str):
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$',          '', text, flags=re.MULTILINE)
    return json.loads(text.strip())


# ─── 1. Batch classifier (with all filters) ───────────────────────────────────

@st.cache_data(ttl=3600)
def batch_classify(headlines_tuple: tuple) -> list:
    """
    Classify headlines AND apply INR filter, India-India skip, dividend filter.
    Returns list of classification dicts in same order as input.
    """
    if not GROQ_API_KEY or not headlines_tuple:
        return [_fallback_classify(h) for h, _ in headlines_tuple]

    headlines = list(headlines_tuple)
    results   = []
    chunk_size = 10

    for i in range(0, len(headlines), chunk_size):
        chunk    = headlines[i:i + chunk_size]
        numbered = "\n".join(
            f"{j+1}. HEADLINE: {h}\n   CONTEXT: {s[:120]}"
            for j, (h, s) in enumerate(chunk)
        )
        user_msg = (
            f"Classify these {len(chunk)} headlines.\n"
            f"Apply ALL filters (inr_involved, skip_india_india, is_indian_subsidiary_dividend).\n"
            f"Return a JSON array of exactly {len(chunk)} objects in order:\n\n"
            f"{numbered}"
        )
        try:
            raw  = _call(CLASSIFIER_SYSTEM, user_msg, max_tokens=1000)
            data = _parse_json(raw)
            if isinstance(data, list) and len(data) == len(chunk):
                results.extend(data)
            else:
                results.extend([_fallback_classify(h) for h, _ in chunk])
        except Exception as ex:
            print(f"  Classifier error chunk {i}: {ex}")
            results.extend([_fallback_classify(h) for h, _ in chunk])
        if i + chunk_size < len(headlines):
            time.sleep(0.5)

    return results

def _fallback_classify(headline: str) -> dict:
    """Keyword-based fallback when Groq unavailable."""
    h = headline.lower()
    if any(k in h for k in ["acqui","merger","takeover","stake","divest","open offer"]):
        atype = "M&A"
    elif any(k in h for k in ["dividend","ex-date","record date","repatriat"]):
        atype = "Dividend"
    elif any(k in h for k in ["invest","fdi","capital","raise","infusion","greenfield"]):
        atype = "FDI"
    elif any(k in h for k in ["ipo","listing","drhp","delist"]):
        atype = "IPO"
    elif any(k in h for k in ["buyback","buy-back","repurchase"]):
        atype = "Buyback"
    elif any(k in h for k in ["jv","joint venture","mou","partnership"]):
        atype = "Strategic"
    else:
        atype = "Other"
    return {
        "action_type":               atype,
        "confidence":                "medium",
        "is_india_relevant":         True,
        "inr_involved":              True,
        "skip_india_india":          False,
        "is_indian_subsidiary_dividend": atype == "Dividend",
        "foreign_entity":            None,
        "deal_value_usd_m":          None,
        "is_significant":            atype != "Other",
        "event_date":                None,
    }


# ─── 2. FX implication ───────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def fx_implication(headline: str, action_type: str,
                   company: str, mnc_parent: str,
                   amount_str: str, nih_usd_m: float) -> str:
    if not GROQ_API_KEY:
        return ""
    try:
        user_msg = (
            f"Action: {action_type}\n"
            f"Company: {company} (subsidiary of {mnc_parent})\n"
            f"Amount: {amount_str or 'not specified'}\n"
            f"NIH exposure: ${nih_usd_m:,.0f}M\n"
            f"Headline: {headline}\n\n"
            f"Write the FX implication sentence."
        )
        result = _call(FX_IMPLICATION_SYSTEM, user_msg, max_tokens=80, temperature=0.2)
        return result.strip('"').strip("'").strip()
    except Exception as ex:
        print(f"  FX implication error: {ex}")
        return ""


# ─── 3. Noise filter ─────────────────────────────────────────────────────────

@st.cache_data(ttl=1800)
def is_noise(headline: str, client_group: str, subsidiary: str) -> bool:
    if not GROQ_API_KEY:
        return False
    try:
        user_msg = (
            f"Client: {subsidiary} (parent: {client_group})\n"
            f"Headline: {headline}\n\nIs this relevant?"
        )
        raw  = _call(NOISE_FILTER_SYSTEM, user_msg, max_tokens=60)
        data = _parse_json(raw)
        return not data.get("relevant", True)
    except Exception:
        return False


# ─── 4. Web search ───────────────────────────────────────────────────────────

def web_search_client(rec: dict) -> list:
    """Groq web search for a specific client. Returns list of event dicts."""
    if not GROQ_API_KEY:
        return []

    sub = rec.get("indian_subsidiary", "") or ""
    grp = rec.get("client_group", "") or ""
    exp = rec.get("net_nih_exposure", 0) or 0

    user_msg = (
        f"Company: {sub}\nMNC Parent: {grp}\nNIH Exposure: ${exp:,.0f}M\n\n"
        f"Search for corporate actions involving {sub} or its parent {grp} in India, "
        f"last 12 months. Focus on cross-border INR flows only. "
        f"Return as JSON array."
    )

    try:
        c = _client()
        resp = c.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": WEB_SEARCH_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            tools=[{"type": "web_search"}],
            temperature=0.1,
            max_tokens=1500,
        )

        # Extract text content
        content = ""
        msg = resp.choices[0].message
        if isinstance(getattr(msg, 'content', None), list):
            for block in msg.content:
                if hasattr(block, 'text'):
                    content += block.text
        elif isinstance(getattr(msg, 'content', None), str):
            content = msg.content or ""

        if not content.strip():
            return []

        events = _parse_json(content)
        if not isinstance(events, list):
            return []

        results = []
        for ev in events:
            if not ev.get("inr_involved", True):
                continue
            results.append({
                "company_name":   sub[:60],
                "ticker":         rec.get("ticker"),
                "action_type":    ev.get("action_type", "Other"),
                "headline":       ev.get("headline", "")[:200],
                "date":           str(ev.get("event_date") or ev.get("date",""))[:10],
                "amount":         _parse_amount(str(ev.get("deal_value","") or "")),
                "currency":       "USD",
                "source":         "Groq web search",
                "raw_detail":     ev.get("fx_implication","")[:300],
                "url":            ev.get("source_url","") or "",
                "foreign_entity": ev.get("counterparty"),
                "_significance":  ev.get("significance","Medium"),
                "_inr_involved":  True,
                "_pre_matched":   rec,
            })
        return results

    except Exception as ex:
        print(f"  Groq web search error {sub[:30]}: {ex}")
        return []


# ─── 5. Daily briefing ───────────────────────────────────────────────────────

@st.cache_data(ttl=1800)
def daily_briefing(action_snapshot: tuple) -> str:
    if not GROQ_API_KEY or not action_snapshot:
        return ""
    try:
        lines = []
        for s in action_snapshot:
            score, atype, hl, co, amt, curr, is_client, grp, sub, nih = s
            tag    = "SCB CLIENT" if is_client else "non-client"
            amt_str = (f"₹{amt:.2f}/sh" if amt and curr=="INR"
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
        return _call(BRIEFING_SYSTEM, user_msg, max_tokens=500, temperature=0.2)
    except Exception as ex:
        return f"_Briefing unavailable: {ex}_"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _parse_amount(text: str):
    if not text: return None
    m = re.search(r'([\d,\.]+)\s*(?:bn|billion)', text, re.I)
    if m:
        try: return float(m.group(1).replace(",","")) * 1000
        except: pass
    m = re.search(r'([\d,\.]+)\s*(?:mn|million|M\b|cr)', text, re.I)
    if m:
        try: return float(m.group(1).replace(",",""))
        except: pass
    m = re.search(r'[\$₹]\s*([\d,\.]+)', text)
    if m:
        try: return float(m.group(1).replace(",",""))
        except: pass
    return None

def make_snapshot(actions: list) -> tuple:
    top = sorted(
        [a for a in actions if a.get("_score",0) >= 50],
        key=lambda x: x["_score"], reverse=True
    )[:12]
    return tuple(
        (
            a.get("_score",0), a.get("action_type",""),
            a.get("headline","")[:100], a.get("company_name",""),
            a.get("amount"), a.get("currency"),
            a.get("is_scb_client",False),
            (a.get("client") or {}).get("client_group",""),
            (a.get("client") or {}).get("indian_subsidiary",""),
            (a.get("client") or {}).get("net_nih_exposure",0) or 0,
        )
        for a in top
    )
