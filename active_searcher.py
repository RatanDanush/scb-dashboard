"""
active_searcher.py
------------------
Actively searches Google News RSS for each client in the pipeline.
Targets M&A, FDI, investments, acquisitions — the things NSE RSS misses entirely.

Tier 1 clients (22): searched every refresh
Tier 2 clients (~30): searched every refresh
Others: passive name-matching only

Each client gets up to 3 targeted queries:
  1. "{subsidiary} acquisition OR deal OR investment India"
  2. "{MNC parent} India acquisition OR investment OR expansion"
  3. "{subsidiary} merger OR stake OR JV"
"""

import re
import datetime
import requests
import feedparser
import streamlit as st

HDR = {"User-Agent": "Mozilla/5.0 (SCB-Dashboard)", "Accept": "application/xml, */*"}
LOOKBACK_DAYS  = 30
LOOKAHEAD_DAYS = 30

# ─── Action classifier ───────────────────────────────────────────────────────

ACTION_KEYWORDS = {
    "M&A":       ["acqui", "merger", "takeover", "buyout", "stake purchase",
                  "open offer", "demerger", "amalgamat", "definitive agreement",
                  "signs agreement", "completes acquisition", "strategic investment",
                  "stake sale", "sells stake", "offloads stake", "divests"],
    "FDI":       ["capital infusion", "equity infusion", "rights issue",
                  "preferential allotment", "qip", "fpo", "fresh capital",
                  "capital raise", "foreign investment", "invests in india",
                  "sets up plant", "establishes", "greenfield", "expands india",
                  "new facility", "new plant", "india expansion"],
    "IPO":       ["ipo", "initial public offering", "lists on", "stock exchange listing",
                  "files drhp", "sebi approval for listing"],
    "Buyback":   ["buyback", "buy-back", "share repurchase"],
    "Strategic": ["joint venture", " jv ", "partnership", "licensing agreement",
                  "technology agreement", "royalty agreement", "strategic alliance",
                  "mou", "memorandum of understanding", "signs mou",
                  "collaboration agreement"],
}

def _classify(text: str) -> str:
    t = text.lower()
    for action, kws in ACTION_KEYWORDS.items():
        if any(k in t for k in kws):
            return action
    return "Other"

def _clean(name: str, stops: list) -> str:
    r = name
    for w in stops:
        r = re.sub(r'\b' + re.escape(w) + r'\b', '', r, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', r).strip()

def _amount(text: str):
    for pat in [r"₹\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr|lakh)?",
                r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:mn|million|bn|billion)?",
                r"rs\.?\s*([\d,]+(?:\.\d+)?)",
                r"([\d,]+(?:\.\d+)?)\s*per\s+share"]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try: return float(m.group(1).replace(",", ""))
            except: pass
    return None

def _foreign(text: str):
    for pat in [
        r"(?:to|by|with|from)\s+([A-Z][A-Za-z\s&]{3,35}(?:Ltd|Limited|Inc|Corp|AG|SA|PLC|Group|Holdings|Management|Capital|Partners))",
        r"([A-Z][A-Za-z\s]{2,25}(?:Asset Management|Capital Partners|Investments|Ventures))",
    ]:
        m = re.search(pat, text)
        if m:
            n = m.group(1).strip()
            if len(n) > 5: return n
    return None

def _parse_pub(entry) -> str:
    pub = entry.get("published", "")
    if pub:
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(pub).date().isoformat()
        except Exception:
            pass
    return datetime.date.today().isoformat()

def _in_window(date_str: str) -> bool:
    try:
        d = datetime.date.fromisoformat(str(date_str)[:10])
        f = datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)
        t = datetime.date.today() + datetime.timedelta(days=LOOKAHEAD_DAYS)
        return f <= d <= t
    except Exception:
        return True

def _gnews(query: str) -> list:
    """Hit Google News RSS with a targeted query."""
    enc = query.replace(" ", "+").replace('"', '%22').replace("&", "%26")
    url = f"https://news.google.com/rss/search?q={enc}&hl=en-IN&gl=IN&ceid=IN:en"
    out = []
    try:
        resp = requests.get(url, headers=HDR, timeout=12)
        feed = feedparser.parse(resp.content)
        for e in feed.entries[:20]:
            title   = e.get("title", "")
            summary = e.get("summary", "")
            date_str = _parse_pub(e)
            if title and _in_window(date_str):
                out.append({
                    "title":   title,
                    "summary": summary[:300],
                    "date":    date_str,
                    "url":     e.get("link", ""),
                })
    except Exception:
        pass
    return out


def _search_one_client(rec: dict) -> list:
    """Run targeted Google News searches for a single client."""
    sub    = rec.get("indian_subsidiary", "") or ""
    grp    = rec.get("client_group", "") or ""
    ticker = rec.get("ticker")

    GEN_STOPS  = ["india","limited","ltd","pvt","private","of","the","and"]
    GRP_STOPS  = ["group","corp","corporation","holdings","plc","ag","sa","bv","inc"]

    sub_q = _clean(sub, GEN_STOPS)
    grp_q = _clean(grp, GEN_STOPS + GRP_STOPS)

    queries = []
    if len(sub_q) > 4:
        queries.append(f'"{sub_q}" acquisition OR merger OR deal OR investment')
        queries.append(f'"{sub_q}" stake OR IPO OR JV OR expansion')
        queries.append(f'"{sub_q}" India 2025 OR 2026')
    if len(grp_q) > 4:
        queries.append(f'"{grp_q}" India acquisition OR investment OR expansion 2025 OR 2026')

    seen    = set()
    actions = []

    for q in queries[:4]:
        for item in _gnews(q):
            key = item["title"][:60].lower()
            if key in seen:
                continue
            seen.add(key)

            combined = item["title"] + " " + item["summary"]
            atype    = _classify(combined)

            # NSE RSS handles dividends — skip them here to avoid duplicates
            if atype == "Dividend":
                continue

            actions.append({
                "company_name":   sub[:60],
                "ticker":         ticker,
                "action_type":    atype,
                "headline":       item["title"][:200],
                "date":           item["date"],
                "amount":         _amount(combined),
                "currency":       "INR" if ("₹" in combined or
                                            "crore" in combined.lower()) else "USD",
                "source":         "Google News",
                "raw_detail":     item["summary"][:300],
                "url":            item["url"],
                "foreign_entity": _foreign(combined),
                "_pre_matched":   rec,
            })

    return actions


@st.cache_data(ttl=1800)
def fetch_active_search(tier1_keys: tuple, tier2_keys: tuple,
                        tier3_keys: tuple, _snapshot: tuple) -> list:
    """
    Cached active search for Tier 1 + Tier 2 + top Tier 3 clients.
    _snapshot is used only as a cache key.
    """
    from client_registry import load_registry
    try:
        reg = load_registry()
    except Exception:
        return []

    by_key = {
        (r.get("client_group",""), r.get("indian_subsidiary","")): r
        for r in reg["all"]
    }

    all_actions = []
    searched    = 0
    # Tier 1 + Tier 2 (full); Tier 3 top-40 by NIH
    all_keys    = list(tier1_keys) + list(tier2_keys[:50]) + list(tier3_keys)

    for key in all_keys:
        rec = by_key.get(key)
        if rec:
            found = _search_one_client(rec)
            all_actions += found
            searched += 1

    print(f"  Active search: {searched} clients → {len(all_actions)} M&A/FDI/Strategic items")
    return all_actions


def get_search_keys(registry: dict):
    """Return hashable keys for Tier 1 + Tier 2 clients, plus top Tier 3 by NIH."""
    tier1 = tuple(
        (r.get("client_group",""), r.get("indian_subsidiary",""))
        for r in registry["all"]
        if "TIER 1" in (r.get("priority_tier",""))
    )
    tier2 = tuple(
        (r.get("client_group",""), r.get("indian_subsidiary",""))
        for r in registry["all"]
        if "TIER 2" in (r.get("priority_tier",""))
    )
    # Top 40 Tier 3 / untiered companies by NIH exposure — ensures BASF, etc. get RSS scanned
    tier3_top = tuple(
        (r.get("client_group",""), r.get("indian_subsidiary",""))
        for r in sorted(
            [r for r in registry["all"]
             if "TIER 1" not in (r.get("priority_tier","") or "").upper()
             and "TIER 2" not in (r.get("priority_tier","") or "").upper()
             and r.get("indian_subsidiary")],
            key=lambda r: r.get("net_nih_exposure", 0) or 0,
            reverse=True
        )[:40]
    )
    snap = tuple(r.get("indian_subsidiary","")[:15] for r in registry["all"][:10])
    return tier1, tier2, tier3_top, snap
