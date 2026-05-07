# macro_generator.py
# Calls Gemini API with Google Search grounding to identify macro stories

import json
import re
import google.generativeai as genai

# ── JSON extraction helper ────────────────────────────────────────────────────

def extract_json(text):
    """Robustly extract a JSON array from text (handles markdown fences)."""
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # Try to find array boundaries
    start = text.find('[')
    end   = text.rfind(']')
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass
    return None

# ── Fallback stories when API fails ──────────────────────────────────────────

def fallback_stories(n=3):
    return [{
        "tag": "Data Unavailable",
        "headline": "Macro stories could not be fetched — add manually",
        "body": "The Gemini API call did not return usable results. "
                "Please add the week's key macro events manually before distributing.",
        "inr_relevance": "📌 INR: Update this section with relevant macro context.",
        "links": [],
        "color": "blue"
    }] * n

# ── Weekly stories ────────────────────────────────────────────────────────────

def get_weekly_stories(api_key, week_start, week_end, week_num):
    """
    Use Gemini 1.5 Pro with Google Search grounding to find the 3 most
    important macro events of the past week relevant to India FX markets.
    Returns a list of story dicts.
    """
    genai.configure(api_key=api_key)

    prompt = f"""You are a senior FX analyst at Standard Chartered's India FM Sales desk.

Use Google Search to identify the 3 most important macro events from the week of {week_start} to {week_end} (Week {week_num}) that affected global FX markets, with particular relevance to USD/INR and INR vs G3 currencies (EUR, GBP, JPY, CNH).

Prioritise: central bank decisions (Fed, RBI, BoE, BoJ, ECB), major economic data surprises (GDP, CPI, PCE, jobs), geopolitical events affecting oil prices, and significant risk-on/risk-off events.

For each story provide:
1. tag: Short category and date (e.g. "Central Bank · {week_start[:6]}", "US Macro · Apr 30", "Geopolitics / Oil · {week_start[:6]}–{week_end[:6]}")
2. headline: Max 15 words, include key numbers
3. body: 2-3 concise sentences. Wrap key numbers and terms in <strong> tags.
4. inr_relevance: 1-2 sentences starting with "📌 INR:" explaining the direct impact on USD/INR or INR vs G3.
5. links: Array of 1-2 objects with "text" (e.g. "→ Fed statement") and "url" (real, working URL)
6. color: "red" for central bank/hawkish news, "amber" for geopolitics/oil/commodities, "blue" for macro data/growth

Return ONLY a valid JSON array. No markdown, no explanation, no preamble.

Example structure:
[
  {{
    "tag": "Central Bank · Apr 29",
    "headline": "FOMC holds 3.50–3.75% in most divided vote since 1992",
    "body": "The Fed held rates in an <strong>8-4 vote</strong>, the most divided since 1992. Three hawks dissented against the easing bias; one dove wanted an immediate cut. Core PCE cited at <strong>3.2%</strong>.",
    "inr_relevance": "📌 INR: Hawkish dissents pushed US 10Y to 4.45%, driving USD/INR above 95. Rate hike odds for Dec 2026 rose from 0% to 9.1%.",
    "links": [
      {{"text": "→ Fed statement", "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260429a.htm"}},
      {{"text": "→ CNBC", "url": "https://www.cnbc.com/2026/04/29/fed-interest-rate-decision-april-2026.html"}}
    ],
    "color": "red"
  }}
]"""

    try:
        model = genai.GenerativeModel(
            model_name='gemini-1.5-pro-latest',
            tools='google_search_retrieval'
        )
        response = model.generate_content(prompt)
        stories = extract_json(response.text)
        if stories and isinstance(stories, list) and len(stories) > 0:
            return stories[:3]  # cap at 3
        return fallback_stories(3)
    except Exception as e:
        # Try flash as fallback
        try:
            model = genai.GenerativeModel(
                model_name='gemini-1.5-flash-latest',
                tools='google_search_retrieval'
            )
            response = model.generate_content(prompt)
            stories = extract_json(response.text)
            if stories and isinstance(stories, list):
                return stories[:3]
        except Exception:
            pass
        return fallback_stories(3)


# ── Weekly ahead ─────────────────────────────────────────────────────────────

def get_week_ahead(api_key, current_week_end):
    """
    Use Gemini to identify key data releases and events for the coming week.
    Returns a list of calendar event dicts.
    """
    genai.configure(api_key=api_key)

    prompt = f"""You are an FX analyst at Standard Chartered's India FM Sales desk.

The current week just ended on {current_week_end}. Use Google Search to identify the 4-5 most important macro events, data releases, and central bank decisions for the COMING week that are relevant to India FX markets (USD/INR, INR vs G3).

Focus on: central bank meetings, major US/India/European data releases (GDP, CPI, jobs, PMI), geopolitical deadlines or summits.

Return ONLY a valid JSON array:
[
  {{
    "date": "Mon 5",
    "impact": "HIGH",
    "event": "Short description of the event and what to watch for",
    "url": "https://real-working-url.com"
  }}
]

impact must be exactly "HIGH" or "MED". Date format: "Day DD" e.g. "Tue 6", "Thu 8". No markdown, no explanation."""

    try:
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash-latest',
            tools='google_search_retrieval'
        )
        response = model.generate_content(prompt)
        events = extract_json(response.text)
        if events and isinstance(events, list):
            return events[:6]
        return []
    except Exception:
        return []


# ── Daily stories ─────────────────────────────────────────────────────────────

def get_daily_stories(api_key, date_str):
    """
    Use Gemini to find 2 key macro events from the last 24 hours.
    """
    genai.configure(api_key=api_key)

    prompt = f"""You are a senior FX analyst at Standard Chartered's India FM Sales desk.

Use Google Search to identify the 2 most important macro events from the last 24 hours (around {date_str}) that are relevant to India FX markets (USD/INR and INR vs G3 currencies).

Focus on: central bank statements, major economic data releases, geopolitical events affecting oil, significant FX moves.

Return ONLY a valid JSON array with exactly this structure (no markdown):
[
  {{
    "tag": "Category · {date_str}",
    "headline": "Headline max 15 words with key numbers",
    "body": "2-3 sentences. Key numbers in <strong> tags.",
    "inr_relevance": "📌 INR: Direct impact on USD/INR.",
    "links": [{{"text": "→ Source", "url": "https://real-url.com"}}],
    "color": "red | amber | blue"
  }}
]"""

    try:
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash-latest',
            tools='google_search_retrieval'
        )
        response = model.generate_content(prompt)
        stories = extract_json(response.text)
        if stories and isinstance(stories, list):
            return stories[:2]
        return fallback_stories(2)
    except Exception:
        return fallback_stories(2)
