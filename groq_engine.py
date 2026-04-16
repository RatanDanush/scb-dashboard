"""
groq_engine.py
--------------
Central module for all Groq interactions.

Five functions:
  1. batch_classify()     — classify headlines (live feed)
  2. fx_implication()     — one-line FX implication per card
  3. is_noise()           — filter irrelevant active search results
  4. web_search_client()  — Groq web search for a specific client
  5. daily_briefing()     — FX desk summary (replaces groq_summarizer)
"""

import os, re, json, time
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ─── Prompts ──────────────────────────────────────────────────────────────────

CLASSIFIER_SYSTEM = """You are a financial news classifier for Standard Chartered Bank India.
Given headlines, classify each one and return a JSON array.

For each headline return:
{
  "action_type": "M&A" | "FDI" | "Dividend" | "Buyback" | "Strategic" | "IPO" | "Delisting" | "Restructuring" | "Other",
  "confidence": "high" | "medium" | "low",
  "is_india_relevant": true | false,
  "foreign_entity": "counterparty name or null",
  "deal_value_usd_m": number or null,
  "is_significant": true | false
}

Rules:
- M&A: acquisitions, mergers, stake purchases, open offers, demergers
- FDI: capital infusions, equity raises, greenfield investments, new facilities
- Dividend: any dividend declaration or repatriation
- Buyback: share repurchases, open offers by the company itself
- Strategic: JVs, MoUs, licensing, royalty agreements, partnerships
- IPO: listings, DRHP filings, delistings
- is_significant: true only if the event has genuine FX or capital markets implications
- is_india_relevant: true if it involves an Indian company or India operations
- Return ONLY a valid JSON array. No other text."""

FX_IMPLICATION_SYSTEM = """You are an FX salesperson at Standard Chartered Bank.
Given a corporate action, write EXACTLY ONE sentence (max 30 words) explaining:
1. The cross-border currency flow this creates
2. The most relevant SC product

Be specific: name the currency pair, direction (INR→USD, EUR→INR etc), and product.
Infer the parent company's home currency from its name/country.
Examples of good output:
- "Maruti dividend repatriation creates INR→JPY flow for Suzuki Japan — FX forward opportunity for FM desk."
- "ABB India capital raise brings CHF→INR inflow from ABB Switzerland — PrismFX conversion play."
- "Siemens stake acquisition triggers EUR→INR FDI flow — cross-currency swap to hedge translation exposure."

Return only the sentence. No preamble."""

NOISE_FILTER_SYSTEM = """You are a relevance filter for a financial markets intelligence system at Standard Chartered Bank India.

Given a news headline and the client it supposedly relates to, answer: is this headline
genuinely relevant to the client and significant enough to show to an FX salesperson?

Return JSON: {"relevant": true|false, "reason": "one short phrase"}

Mark as NOT relevant if:
- It's a generic industry article that mentions the company in passing
- It's about the company's products/services, not corporate structure or finance
- It's clearly about a different company with a similar name
- It's older than 12 months
- It's a press release about awards, CSR, or marketing

Mark as RELEVANT if:
- It involves M&A, capital raises, dividends, stake changes, restructuring
- It involves the foreign parent company and India
- It involves significant capex, plant setup, or strategic investment

Return ONLY valid JSON."""

WEB_SEARCH_SYSTEM = """You are a corporate intelligence analyst at Standard Chartered Bank India.
Search for recent corporate actions by the given company.

Focus ONLY on:
- Acquisitions, mergers, stake sales, open offers
- Capital raises, FDI, equity infusions, rights issues  
- Dividends (especially large or special ones)
- IPOs, delistings, major restructuring
- Joint ventures, strategic partnerships with financial implications
- Significant capex announcements (new plants, expansions)

For each finding return a JSON array:
[{
  "date": "YYYY-MM or YYYY-MM-DD",
  "action_type": "M&A|FDI|Dividend|Strategic|IPO|Buyback|Other",
  "headline": "clean one-line description",
  "fx_implication": "one sentence on FX/financial implication for Standard Chartered",
  "significance": "High|Medium|Low",
  "deal_value": "e.g. $420M or ₹3,200cr or null",
  "counterparty": "name of acquirer/target/partner or null"
}]

Rules:
- Only include events from the last 12 months
- Only include events with genuine financial markets significance  
- Maximum 8 events
- Return ONLY valid JSON array, no other text"""

BRIEFING_SYSTEM = """You are a senior financial markets analyst at Standard Chartered Bank.
Write a concise daily briefing for the FX sales desk based on today's corporate actions.

Rules:
- Maximum 5 bullet points
- Each bullet: company name + action + specific FX implication + SC product opportunity
- Lead with the highest FX-significance event
- Infer currency pairs from company names (Siemens=EUR, Maruti/Suzuki=JPY, HUL/Unilever=GBP etc)
- Flag unusually large or one-time events explicitly
- Mention NIH exposure size where relevant
- No fluff, no disclaimers, no sign-off
- Format: • **Company** — action — implication"""


# ─── Groq client helper ───────────────────────────────────────────────────────

def _client():
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set")
    from groq import Groq
    return Groq(api_key=GROQ_API_KEY)

def _call(system: str, user: str, model="llama-3.3-70b-versatile",
          max_tokens=1000, temperature=0.1) -> str:
    """Single Groq call — returns content string."""
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
    """Strip markdown fences and parse JSON."""
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$',          '', text, flags=re.MULTILINE)
    return json.loads(text.strip())


# ─── 1. Batch classifier ─────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def batch_classify(headlines_tuple: tuple) -> list:
    """
    Classify a batch of headlines.
    Input is a tuple of (headline, summary) pairs — hashable for cache.
    Returns list of classification dicts, same order as input.
    """
    if not GROQ_API_KEY or not headlines_tuple:
        return [_default_classify(h) for h, _ in headlines_tuple]

    headlines = list(headlines_tuple)
    results   = []

    # Process in chunks of 10
    chunk_size = 10
    for i in range(0, len(headlines), chunk_size):
        chunk = headlines[i:i + chunk_size]
        numbered = "\n".join(
            f"{j+1}. HEADLINE: {h}\n   CONTEXT: {s[:100]}"
            for j, (h, s) in enumerate(chunk)
        )
        user_msg = (
            f"Classify these {len(chunk)} headlines. "
            f"Return a JSON array of exactly {len(chunk)} objects in order:\n\n"
            f"{numbered}"
        )
        try:
            raw  = _call(CLASSIFIER_SYSTEM, user_msg, max_tokens=800)
            data = _parse_json(raw)
            if isinstance(data, list) and len(data) == len(chunk):
                results.extend(data)
            else:
                results.extend([_default_classify(h) for h, _ in chunk])
        except Exception as ex:
            print(f"  Groq classifier error (chunk {i}): {ex}")
            results.extend([_default_classify(h) for h, _ in chunk])

        if i + chunk_size < len(headlines):
            time.sleep(1)   # respect rate limits

    return results

def _default_classify(headline: str) -> dict:
    """Fallback classification using keywords."""
    h = headline.lower()
    if any(k in h for k in ["acqui","merger","takeover","stake","open offer","divest"]):
        atype = "M&A"
    elif any(k in h for k in ["dividend","ex-date","record date","repatriat"]):
        atype = "Dividend"
    elif any(k in h for k in ["invest","fdi","capital","raise","infusion","greenfield"]):
        atype = "FDI"
    elif any(k in h for k in ["ipo","listing","drhp","delist"]):
        atype = "IPO"
    elif any(k in h for k in ["buyback","buy-back","repurchase"]):
        atype = "Buyback"
    elif any(k in h for k in ["jv","joint venture","mou","partnership","licensing"]):
        atype = "Strategic"
    else:
        atype = "Other"
    return {
        "action_type":      atype,
        "confidence":       "medium",
        "is_india_relevant": True,
        "foreign_entity":   None,
        "deal_value_usd_m": None,
        "is_significant":   atype != "Other",
    }


# ─── 2. FX implication ───────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def fx_implication(headline: str, action_type: str,
                   company: str, mnc_parent: str,
                   amount_str: str, nih_usd_m: float) -> str:
    """
    Generate one-sentence FX implication for a card.
    Only called for high/critical scored actions.
    """
    if not GROQ_API_KEY:
        return ""
    try:
        user_msg = (
            f"Corporate action: {action_type}\n"
            f"Company: {company} (subsidiary of {mnc_parent})\n"
            f"Amount: {amount_str or 'not specified'}\n"
            f"NIH exposure: ${nih_usd_m:,.0f}M\n"
            f"Headline: {headline}\n\n"
            f"Write the FX implication sentence."
        )
        result = _call(FX_IMPLICATION_SYSTEM, user_msg, max_tokens=60, temperature=0.2)
        # Clean up — remove quotes if Groq wrapped in them
        return result.strip('"').strip("'").strip()
    except Exception as ex:
        print(f"  FX implication error: {ex}")
        return ""


# ─── 3. Noise filter ─────────────────────────────────────────────────────────

@st.cache_data(ttl=1800)
def is_noise(headline: str, client_group: str, subsidiary: str) -> bool:
    """
    Returns True if the headline should be filtered out.
    Used on active search results before adding to feed.
    """
    if not GROQ_API_KEY:
        return False   # if no key, include everything
    try:
        user_msg = (
            f"Client: {subsidiary} (parent: {client_group})\n"
            f"Headline: {headline}\n\n"
            f"Is this relevant?"
        )
        raw  = _call(NOISE_FILTER_SYSTEM, user_msg, max_tokens=60)
        data = _parse_json(raw)
        return not data.get("relevant", True)
    except Exception:
        return False   # on error, include the item


# ─── 4. Web search for a client ──────────────────────────────────────────────

def web_search_client(rec: dict) -> list:
    """
    Use Groq web search to find corporate actions for a specific client.
    Falls back to empty list if web search not available.
    Returns list of event dicts.
    """
    if not GROQ_API_KEY:
        return []

    sub = rec.get("indian_subsidiary", "") or ""
    grp = rec.get("client_group", "") or ""
    exp = rec.get("net_nih_exposure", 0) or 0

    user_msg = (
        f"Company: {sub}\n"
        f"MNC Parent: {grp}\n"
        f"NIH Exposure: ${exp:,.0f}M\n\n"
        f"Search for corporate actions, deals, investments and significant financial events "
        f"involving {sub} or its parent {grp} in India from the last 12 months. "
        f"Include M&A deals, capital raises, stake sales, large dividends, IPOs, "
        f"strategic partnerships. Return as JSON array."
    )

    try:
        # Try Groq with web search tool
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

        # Extract content from response
        content = ""
        for block in resp.choices[0].message.content if isinstance(
                resp.choices[0].message.content, list) else []:
            if hasattr(block, "text"):
                content += block.text
        if not content:
            content = resp.choices[0].message.content or ""

        if not content.strip():
            return []

        events = _parse_json(content)
        if not isinstance(events, list):
            return []

        # Normalise to our action dict format
        results = []
        for ev in events:
            sig = ev.get("significance", "Medium")
            results.append({
                "company_name":   sub[:60],
                "ticker":         rec.get("ticker"),
                "action_type":    ev.get("action_type", "Other"),
                "headline":       ev.get("headline", "")[:200],
                "date":           str(ev.get("date", ""))[:10] or _today_str(),
                "amount":         _parse_amount(str(ev.get("deal_value", "") or "")),
                "currency":       "USD",
                "source":         "Groq web search",
                "raw_detail":     ev.get("fx_implication", "")[:300],
                "url":            "",
                "foreign_entity": ev.get("counterparty"),
                "_significance":  sig,
                "_pre_matched":   rec,
            })
        return results

    except Exception as ex:
        print(f"  Groq web search error for {sub}: {ex}")
        # Graceful fallback — return empty, active_searcher handles RSS fallback
        return []


# ─── 5. Daily briefing ───────────────────────────────────────────────────────

@st.cache_data(ttl=1800)
def daily_briefing(action_snapshot: tuple) -> str:
    """
    Generate FX desk briefing from top scored actions.
    action_snapshot is a hashable tuple for caching.
    """
    if not GROQ_API_KEY or not action_snapshot:
        return ""
    try:
        lines = []
        for s in action_snapshot:
            score, atype, hl, co, amt, curr, is_client, grp, sub, nih = s
            client_tag = "SCB CLIENT" if is_client else "non-client"
            amt_str    = f"₹{amt:.2f}/sh" if amt and curr == "INR" else (
                         f"${amt:.0f}M" if amt else "")
            lines.append(
                f"[Score {score} | {client_tag}] {atype}: {sub} "
                f"(parent: {grp}) | NIH: ${nih:,.0f}M | {amt_str} | {hl[:100]}"
            )

        user_msg = (
            f"Today's top {len(lines)} corporate actions:\n\n"
            + "\n".join(lines)
            + "\n\nWrite the daily FX desk briefing."
        )
        return _call(BRIEFING_SYSTEM, user_msg, max_tokens=500, temperature=0.2)
    except Exception as ex:
        return f"_Briefing unavailable: {ex}_"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _today_str() -> str:
    import datetime
    return datetime.date.today().isoformat()

def _parse_amount(text: str):
    """Extract numeric amount from strings like '$420M' or '₹3,200cr'."""
    import re
    # Billion
    m = re.search(r'[\$₹]?\s*([\d,\.]+)\s*(?:bn|billion|B\b)', text, re.I)
    if m:
        try: return float(m.group(1).replace(",","")) * 1000
        except: pass
    # Million
    m = re.search(r'[\$₹]?\s*([\d,\.]+)\s*(?:mn|million|M\b|cr)', text, re.I)
    if m:
        try: return float(m.group(1).replace(",",""))
        except: pass
    # Plain number
    m = re.search(r'[\$₹]\s*([\d,\.]+)', text)
    if m:
        try: return float(m.group(1).replace(",",""))
        except: pass
    return None


def make_snapshot(actions: list) -> tuple:
    """Convert actions to hashable tuple for briefing cache key."""
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
