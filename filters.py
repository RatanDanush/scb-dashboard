"""
filters.py
----------
Centralised keyword filters shared across corporate_fetcher.py
and client_registry.py.

Keeps filter logic in one place so updates propagate everywhere.
"""

# ─── Market commentary / equity noise ────────────────────────────────────────
# Headlines matching these are NOT corporate actions

MARKET_COMMENTARY_PHRASES = [
    # Share price updates
    "share price live", "stock price live", "live update", "live updates",
    "price performance", "performance snapshot", "market behavior",
    "share price today", "stock price today", "trading session",
    # Analyst ratings
    "rated buy", "rated sell", "rated hold", "rates buy", "rates sell",
    "price target", "initiates coverage", "upgrades to", "downgrades to",
    "outperform", "underperform", "neutral rating", "buy rating",
    "sell rating", "hold rating", "target price",
    # Post-IPO stock performance
    "trades below issue price", "trades above issue price",
    "below ipo price", "above ipo price", "ipo performance",
    "how india's biggest ipos", "biggest ipos performing",
    "stock falls", "stock rises", "shares fall", "shares rise",
    "shares tumble", "shares surge", "shares drop",
    # General market commentary
    "wall street gains", "wall street falls", "market roundup",
    "weekly wrap", "market wrap", "earnings beat", "earnings miss",
    "revenue miss", "quarterly results", "q1 results", "q2 results",
    "q3 results", "q4 results", "annual results",
    # Technical analysis
    "support level", "resistance level", "rsi", "moving average",
    "52-week high", "52-week low", "market cap",
    # ── Stock pick / investment list articles (Issue 5 — Honeywell) ──────────
    "stocks to invest", "stocks to buy", "stocks to watch",
    "high-priced stocks", "best stocks", "top stocks",
    "stocks in india in", "stocks for", "stocks to consider",
    "shares to buy", "shares to watch",
    # ── Smart investing / retail investor content (Issue 8) ──────────────────
    "what you need to know for smart investing",
    "smart investing", "stock: what you need to know",
    "invest in india in april", "invest in india in",
    "investing now", "for smart investing",
    # ── Executive appointments / HR news — NOT capital flows ─────────────────
    "extends tenure", "extend his tenure", "extend her tenure",
    "cfo extends", "ceo extends", "md extends", "director extends",
    "appoints cfo", "appoints ceo", "appoints md", "names new cfo",
    "names new ceo", "new managing director", "new chief financial",
    "new chief executive", "joins as cfo", "joins as ceo",
    "promoted to cfo", "promoted to ceo",
    "annual report", "fy2025 annual report", "fy2026 annual report",
    "strong performance marks milestone",
]
    "raises prices on select plans", "cuts benefits and raises prices",
    "new plans rolled out", "plan prices", "price hike on plans",
    "service tariff", "prepaid plans", "postpaid plans",
    "broadband prices", "data plan",
]

# ─── Aggregator / list articles ───────────────────────────────────────────────
AGGREGATOR_PHRASES = [
    "list of ", "top acquisitions", "acquisitions by ",
    "tracxn", "crunchbase", "cb insights",
    "deal tracker", "m&a tracker", "acquisition tracker",
    "funding rounds", "latest funding",
]

# ─── Secondary reference patterns ────────────────────────────────────────────
# Article is primarily about another company — client is only mentioned
SECONDARY_REFERENCE_TEMPLATES = [
    "ceo joins", "cfo joins", "executive joins", "director joins",
    "adds {name} ceo", "hires {name}", "appoints {name} ceo",
    "ex-{name}", "former {name} ceo", "former {name} executive",
    "{name} ceo joins", "{name} executive joins",
    "{name} board member joins", "board of {name}",
]

# ─── Commonly confused company pairs ─────────────────────────────────────────
# Never cross-match these even if name fragments overlap
NEVER_MATCH = {
    "basf":           ["bayer", "bayercrop", "bayer cropscience"],
    "bayer":          ["basf"],
    "abbvie":         ["abbott", "abbotindia"],
    "abbott":         ["abbvie"],
    "siemens energy": ["siemens"],
    "siemens":        ["siemens energy"],
    "linde":          ["lindeindia"],
    "pfizer":         ["piramal"],
    "glaxo":          ["haleon"],
    "shell":          [],
    "unilever":       [],
    "novartis":       [],
}

# ─── Words stripped from names before matching ───────────────────────────────
NAME_STOP_WORDS = {
    "ltd", "pvt", "limited", "india", "private", "of", "the", "and",
    "group", "corp", "corporation", "holdings", "plc", "ag", "sa",
    "bv", "inc", "llc", "gmbh", "nv",
}

# ─── Action types worth triggering Groq web search ───────────────────────────
# If RSS finds these types for a client, escalate to Groq web search
WEB_SEARCH_TRIGGER_TYPES = {"M&A", "FDI", "Strategic", "IPO", "Buyback", "Restructuring"}

# ─── Helpers ─────────────────────────────────────────────────────────────────

def is_market_commentary(headline: str) -> bool:
    h = headline.lower()
    if any(p in h for p in MARKET_COMMENTARY_PHRASES):
        return True
    if any(p in h for p in AGGREGATOR_PHRASES):
        return True
    return False

def is_object_in_stake_action(headline: str, client_name: str) -> bool:
    """
    Returns True if the matched company is the OBJECT of a stake action,
    not the subject — i.e. someone else is acting on the company's shares.

    Keep  (subject): "Siemens cuts stake in Innomotics"
    Filter (object): "Goldman Sachs cuts Siemens Energy stake"

    Safety rule: if company name appears BEFORE the verb, it's the actor → keep.
    Safety rule: if both company and a parent/related name appear, default keep.
    """
    import re
    h    = headline.lower()
    name = client_name.lower()
    for w in ["group", "corporation", "holdings", "plc", "ag", "sa", "inc",
              "ltd", "limited", "india", "pvt", "private"]:
        name = re.sub(r'\b' + re.escape(w) + r'\b', '', name).strip()
    name = re.sub(r'\s+', ' ', name).strip()
    if not name or len(name) < 4:
        return False
    if name not in h:
        return False

    STAKE_VERBS = (
        r"cuts?|reduces?|trims?|sells?|offloads?|divests?|exits?|"
        r"raises?|increases?|lifts?|boosts?|buys?|acquires?|adds?"
    )
    # Pattern: [anything] [verb] [company] [stake/shares/holding/interest]
    # This means company is the object
    obj_pattern = re.compile(
        rf".+?\b({STAKE_VERBS})\b.{{0,40}}{re.escape(name)}.{{0,30}}"
        rf"\b(stake|shares?|holding|interest|position|equity)\b",
        re.IGNORECASE,
    )
    # Pattern: [company] [verb] — company is the subject
    subj_pattern = re.compile(
        rf"^{re.escape(name)}\b.{{0,60}}\b({STAKE_VERBS})\b",
        re.IGNORECASE,
    )

    if subj_pattern.match(h):
        return False   # company is the actor — keep

    if obj_pattern.search(h):
        # Safety: if company name appears before the first stake verb, it's
        # probably the subject in a different clause — default keep
        first_verb_match = re.search(rf"\b({STAKE_VERBS})\b", h)
        if first_verb_match:
            name_pos = h.find(name)
            verb_pos = first_verb_match.start()
            if name_pos < verb_pos:
                return False  # name before verb → subject → keep
        return True   # company is the object → filter

    return False


def is_secondary_reference(headline: str, client_name: str) -> bool:
    """True if client appears as secondary reference in the headline."""
    h    = headline.lower()
    name = client_name.lower()
    # Strip generic words for cleaner matching
    for w in ["group", "corporation", "holdings", "plc", "ag", "sa", "inc"]:
        name = name.replace(w, "").strip()
    if not name or len(name) < 4:
        return False
    patterns = [
        f"adds {name} ceo", f"hires {name}", f"appoints {name}",
        f"{name} ceo joins", f"{name} executive joins",
        f"former {name}", f"ex-{name}",
        f"{name} board member", f"board of ",
    ]
    if any(p in h for p in patterns):
        return True
    # Stake-action object detection
    if is_object_in_stake_action(headline, client_name):
        return True
    return False

def pre_filter(headline: str) -> bool:
    """
    Fast keyword pre-filter before sending to Groq.
    Returns True if headline should be KEPT (not filtered).
    Returns False if headline is obvious noise.
    """
    return not is_market_commentary(headline)
