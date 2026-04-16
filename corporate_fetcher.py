"""
corporate_fetcher.py  —  v2
---------------------------
Fetches corporate actions from 4 sources.
Window: past 30 days + upcoming 30 days (captures both history and ex-dates).

Sources (in priority order):
  1. NSE RSS  — no key needed, India-specific, real-time
  2. yfinance — no key needed, dividend/split history
  3. FMP      — needs free key, dividend calendar + M&A feed
  4. Finnhub  — needs free key, company news with action detection
"""

import os, re, datetime, requests, feedparser
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

FINNHUB_KEY    = os.getenv("FINNHUB_API_KEY", "")
FMP_KEY        = os.getenv("FMP_API_KEY", "")
LOOKBACK_DAYS  = 30
LOOKAHEAD_DAYS = 30

# ─── Date helpers ─────────────────────────────────────────────────────────────

def _today():   return datetime.date.today()
def _from_dt(): return _today() - datetime.timedelta(days=LOOKBACK_DAYS)
def _to_dt():   return _today() + datetime.timedelta(days=LOOKAHEAD_DAYS)
def _fmt(d):    return d.strftime("%Y-%m-%d")

def _in_window(date_str: str) -> bool:
    try:
        d = datetime.date.fromisoformat(str(date_str)[:10])
        return _from_dt() <= d <= _to_dt()
    except Exception:
        return True


# ─── Action classification ────────────────────────────────────────────────────

KEYWORDS = {
    "Dividend":   ["dividend", "interim dividend", "final dividend",
                   "special dividend", "repatriat", "payout", "ex-date",
                   "ex date", "record date", "distribution"],
    "M&A":        ["acqui", "merger", "takeover", "buyout", "stake purchase",
                   "open offer", "delisting", "demerger", "amalgamat",
                   "scheme of arrangement", "strategic stake"],
    "FDI":        ["fdi", "foreign direct investment", "capital infusion",
                   "equity infusion", "rights issue", "preferential allotment",
                   "qip", "fpo", "fresh capital", "capital raise"],
    "Buyback":    ["buyback", "buy-back", "share repurchase"],
    "Strategic":  ["joint venture", " jv ", "partnership", "licensing",
                   "technology agreement", "royalty", "strategic alliance",
                   "collaboration", "mou"],
    "Stock Split": ["stock split", "bonus share", "sub-division", "split"],
}

def classify(text: str) -> str:
    t = text.lower()
    for action, kws in KEYWORDS.items():
        if any(k in t for k in kws):
            return action
    return "Other"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _company(title: str) -> str:
    return re.split(r"[-:|/]", title)[0].strip()[:80]

def _amount(text: str):
    for pat in [r"rs\.?\s*([\d,]+(?:\.\d+)?)\s*per\s+share",
                r"([\d,]+(?:\.\d+)?)\s*per\s+share",
                r"dividend\s+of\s+rs\.?\s*([\d,]+(?:\.\d+)?)",
                r"₹\s*([\d,]+(?:\.\d+)?)",
                r"inr\s*([\d,]+(?:\.\d+)?)"]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try: return float(m.group(1).replace(",", ""))
            except: pass
    return None

def _ticker(text: str, known: set):
    for t in known:
        if re.search(r'\b' + re.escape(t) + r'\b', text.upper()):
            return t
    return None

def _foreign(text: str):
    for pat in [r"\bto\s+([A-Z][A-Za-z &]{3,35}(?:Ltd|Limited|Inc|Corp|AG|SA|PLC|Group|Holdings))",
                r"\bby\s+([A-Z][A-Za-z &]{3,35}(?:Ltd|Limited|Inc|Corp|AG|SA|PLC|Group|Holdings))"]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            n = m.group(1).strip()
            if len(n) > 4: return n
    return None

def _parse_date(raw: str) -> str:
    raw = raw.strip().replace(" ", "-")
    for fmt in ["%d-%b-%Y", "%d-%B-%Y", "%d/%b/%Y", "%d-%m-%Y", "%Y-%m-%d"]:
        try: return datetime.datetime.strptime(raw, fmt).date().isoformat()
        except: pass
    return _fmt(_today())

def _pub_date(entry) -> str:
    pub = entry.get("published", "")
    if pub:
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(pub).date().isoformat()
        except: pass
    return _fmt(_today())


# ─── SOURCE 1: NSE RSS ────────────────────────────────────────────────────────

NSE_FEEDS = [
    ("Corporate Actions",  "https://nsearchives.nseindia.com/content/RSS/Corporate_action.xml"),
    ("Board Meetings",     "https://nsearchives.nseindia.com/content/RSS/BoardMeeting.xml"),
    ("Announcements",      "https://nsearchives.nseindia.com/content/RSS/Announcement.xml"),
    ("Corp Announcements", "https://nsearchives.nseindia.com/content/RSS/CorporateAnnouncement.xml"),
]
HDR = {"User-Agent": "Mozilla/5.0 (SCB-Dashboard)", "Accept": "application/xml, */*"}

def fetch_nse(known_tickers: set) -> list:
    out = []
    for name, url in NSE_FEEDS:
        try:
            resp = requests.get(url, headers=HDR, timeout=15)
            feed = feedparser.parse(resp.content)
            n = 0
            for e in feed.entries:
                title   = e.get("title", "")
                summary = e.get("summary", "")
                combined = title + " " + summary

                # Use ex-date from title if present, else published date
                date_str = _pub_date(e)
                m = re.search(
                    r"ex[-\s]?date[:\s]+(\d{1,2}[-\s/]\w{3,9}[-\s/]\d{4}|\d{4}-\d{2}-\d{2})",
                    combined, re.IGNORECASE
                )
                if m:
                    date_str = _parse_date(m.group(1))

                if not _in_window(date_str):
                    continue

                out.append({
                    "company_name":   _company(title),
                    "ticker":         _ticker(title, known_tickers),
                    "action_type":    classify(combined),
                    "headline":       title[:200],
                    "date":           date_str,
                    "amount":         _amount(combined),
                    "currency":       "INR",
                    "source":         f"NSE — {name}",
                    "raw_detail":     summary[:300],
                    "url":            e.get("link", ""),
                    "foreign_entity": None,
                })
                n += 1
            print(f"  NSE [{name}]: {n} items in window (feed has {len(feed.entries)} total)")
        except Exception as ex:
            print(f"  NSE [{name}] error: {ex}")
    return out


# ─── SOURCE 2: yfinance ───────────────────────────────────────────────────────


def fetch_yfinance(tickers: list) -> list:
    out, n = [], 0
    wide_from = _today() - datetime.timedelta(days=730)  # 2 years

    for ticker in tickers:
        try:
            t = yf.Ticker(f"{ticker}.NS")
            # history(actions=True) is most reliable for Indian NSE stocks
            hist = t.history(period="2y", actions=True)
            if hist is None or hist.empty:
                continue
            for col, atype in [("Dividends", "Dividend"), ("Stock Splits", "Stock Split")]:
                if col not in hist.columns:
                    continue
                series = hist[col][hist[col] > 0]
                for dt_idx, val in series.items():
                    try:
                        d = dt_idx.date() if hasattr(dt_idx, "date") else datetime.date.fromisoformat(str(dt_idx)[:10])
                    except Exception:
                        continue
                    if d < wide_from:
                        continue
                    label = f"₹{val:.2f}/share" if atype == "Dividend" else f"{val}:1"
                    out.append({
                        "company_name": ticker, "ticker": ticker,
                        "action_type": atype,
                        "headline": f"{ticker} — {atype.lower()} {label}",
                        "date": d.isoformat(), "amount": float(val),
                        "currency": "INR" if atype == "Dividend" else None,
                        "source": "yfinance",
                        "raw_detail": "Yahoo Finance dividend/split history",
                        "url": f"https://finance.yahoo.com/quote/{ticker}.NS",
                        "foreign_entity": None,
                    })
                    n += 1
        except Exception:
            pass
    print(f"  yfinance: {n} actions across {len(tickers)} tickers (last 2 years)")
    return out


# ─── SOURCE 3: FMP ────────────────────────────────────────────────────────────

def fetch_fmp(tickers: list) -> list:
    out = []
    if not FMP_KEY:
        print("  FMP: skipped — add FMP_API_KEY to .env for dividend calendar + M&A")
        return out
    ticker_set = {t.upper() for t in tickers}
    try:
        url = (f"https://financialmodelingprep.com/api/v3/stock_dividend_calendar"
               f"?from={_fmt(_from_dt())}&to={_fmt(_to_dt())}&apikey={FMP_KEY}")
        data = requests.get(url, timeout=15).json()
        n = 0
        for item in (data if isinstance(data, list) else []):
            sym = item.get("symbol", "").replace(".NS", "").upper()
            if sym not in ticker_set: continue
            date_str = str(item.get("date", _fmt(_today())))[:10]
            if not _in_window(date_str): continue
            out.append({
                "company_name": sym, "ticker": sym, "action_type": "Dividend",
                "headline": f"{sym} — dividend ₹{item.get('dividend','?')} | ex-date {date_str}",
                "date": date_str, "amount": item.get("dividend"),
                "currency": "INR", "source": "FMP",
                "raw_detail": str(item)[:200], "url": "",
                "foreign_entity": None,
            })
            n += 1
        print(f"  FMP dividends: {n} matched tickers")
    except Exception as ex:
        print(f"  FMP error: {ex}")
    try:
        url = (f"https://financialmodelingprep.com/api/v4/mergers-acquisitions-rss-feed"
               f"?page=0&apikey={FMP_KEY}")
        data = requests.get(url, timeout=15).json()
        n = 0
        for item in (data if isinstance(data, list) else [])[:50]:
            title  = item.get("title", "")
            detail = item.get("description", "")
            date   = str(item.get("date", _fmt(_today())))[:10]
            if not _in_window(date): continue
            if "india" not in (title + detail).lower(): continue
            out.append({
                "company_name": _company(title), "ticker": None, "action_type": "M&A",
                "headline": title[:200], "date": date, "amount": _amount(title + detail),
                "currency": "USD", "source": "FMP M&A",
                "raw_detail": detail[:300], "url": item.get("url", ""),
                "foreign_entity": _foreign(title),
            })
            n += 1
        print(f"  FMP M&A: {n} India-related deals")
    except Exception as ex:
        print(f"  FMP M&A error: {ex}")
    return out


# ─── SOURCE 4: Indian Financial News RSS ─────────────────────────────────────
# Replaces Finnhub — much better Indian corporate coverage, no API key needed

INDIA_NEWS_FEEDS = [
    ("Economic Times Markets",    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("Economic Times Companies",  "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("Business Standard Markets", "https://www.business-standard.com/rss/markets-106.rss"),
    ("Business Standard Corps",   "https://www.business-standard.com/rss/companies-101.rss"),
    ("Moneycontrol Corporate",    "https://www.moneycontrol.com/rss/corporatenews.xml"),
    ("Mint Markets",              "https://www.livemint.com/rss/markets"),
]

def fetch_india_news(registry: dict) -> list:
    """Scrape Indian financial news, match to SCB clients by company name."""
    from client_registry import match_by_name
    out, n = [], 0
    # Build name fragments for fast matching
    fragments = []
    for rec in registry["all"]:
        sub = rec.get("indian_subsidiary", "") or ""
        clean = re.sub(r"\b(india|limited|ltd|pvt|private|of|the)\b", "",
                       sub.lower(), flags=re.IGNORECASE).strip()
        if len(clean) > 5:
            fragments.append((clean, rec))

    for feed_name, url in INDIA_NEWS_FEEDS:
        try:
            resp = requests.get(url, headers=HDR, timeout=12)
            feed = feedparser.parse(resp.content)
            fc = 0
            for e in feed.entries[:60]:
                title   = e.get("title", "")
                summary = e.get("summary", "")
                link    = e.get("link", "")
                combined = title + " " + summary
                date_str = _pub_date(e)
                if not _in_window(date_str):
                    continue
                atype = classify(combined)
                # Match to SCB client
                matched = None
                cl = combined.lower()
                for frag, rec in fragments:
                    if frag in cl:
                        matched = rec
                        break
                # Only include if matches SCB client OR strong action signal
                if not matched and atype in ("Other",):
                    continue
                item = {
                    "company_name": _company(title),
                    "ticker":       matched["ticker"] if matched else None,
                    "action_type":  atype if atype != "Other" else "Strategic",
                    "headline":     title[:200],
                    "date":         date_str,
                    "amount":       _amount(combined),
                    "currency":     "INR",
                    "source":       f"News — {feed_name}",
                    "raw_detail":   summary[:300],
                    "url":          link,
                    "foreign_entity": _foreign(combined),
                }
                if matched:
                    item["_pre_matched"] = matched
                out.append(item)
                fc += 1; n += 1
            print(f"  News [{feed_name}]: {fc} relevant items (feed: {len(feed.entries)} total)")
        except Exception as ex:
            print(f"  News [{feed_name}] error: {ex}")
    print(f"  Indian news RSS total: {n} items")
    return out


def fetch_finnhub(tickers: list) -> list:
    """Kept for compatibility — replaced by Indian news RSS."""
    if FINNHUB_KEY:
        print("  Finnhub: has key but skipped — poor Indian NSE coverage; using Indian news RSS")
    return []

def fetch_all_corporate_actions(registry: dict) -> list:
    from client_registry import match_by_name

    all_tickers = list(registry["by_ticker"].keys())

    print(f"\n{'='*60}")
    print(f"Fetching | window {_fmt(_from_dt())} → {_fmt(_to_dt())}")
    print(f"Tickers: {len(all_tickers)} total")
    print(f"{'='*60}")

    # ── Structured sources ────────────────────────────────────────────────────
    raw  = fetch_nse(set(all_tickers))
    raw += fetch_yfinance(all_tickers)
    raw += fetch_fmp(all_tickers)
    raw += fetch_india_news(registry)

    # ── Active Google News search ─────────────────────────────────────────────
    try:
        from active_searcher import fetch_active_search, get_search_keys
        t1, t2, snap = get_search_keys(registry)
        active = fetch_active_search(t1, t2, snap)
        raw += active
        print(f"  Active search: {len(active)} items")
    except Exception as ex:
        print(f"  Active search error: {ex}")

    # ── Groq web search cache (batch results) ─────────────────────────────────
    try:
        from batch_manager import load_cache, get_all_cached_events
        cache        = load_cache()
        cached_items = get_all_cached_events(registry, cache)
        raw += cached_items
    except Exception as ex:
        print(f"  Batch cache error: {ex}")

    print(f"\nRaw items before classify: {len(raw)}")

    # ── Groq classifier ───────────────────────────────────────────────────────
    # Only classify items that came from news sources (not NSE/yfinance structured data)
    news_sources = {"Google News", "NSE — Announcements", "NSE — Corp Announcements",
                    "yfinance"}  # yfinance already classified structurally
    to_classify  = [(i, a) for i, a in enumerate(raw)
                    if any(ns in a.get("source","") for ns in
                           ["Google News","News —","Groq web"])
                    and a.get("action_type") in ("Other","Strategic")]

    if to_classify:
        try:
            from groq_engine import batch_classify, GROQ_API_KEY
            if GROQ_API_KEY:
                print(f"  Groq classifying {len(to_classify)} news items...")
                headlines_tuple = tuple(
                    (a["headline"], a.get("raw_detail","")[:100])
                    for _, a in to_classify
                )
                classifications = batch_classify(headlines_tuple)
                for (idx, action), clf in zip(to_classify, classifications):
                    if clf.get("confidence") in ("high","medium"):
                        raw[idx]["action_type"]    = clf.get("action_type", action["action_type"])
                        raw[idx]["foreign_entity"] = clf.get("foreign_entity") or action.get("foreign_entity")
                        if clf.get("deal_value_usd_m"):
                            raw[idx]["amount"]   = clf["deal_value_usd_m"]
                            raw[idx]["currency"] = "USD"
                        raw[idx]["_groq_confidence"] = clf.get("confidence","medium")
                        raw[idx]["_groq_significant"] = clf.get("is_significant", True)
                    elif clf.get("confidence") == "low":
                        raw[idx]["_groq_confidence"] = "low"
                        raw[idx]["_groq_significant"] = clf.get("is_significant", False)
        except Exception as ex:
            print(f"  Groq classifier error: {ex}")

    # ── Noise filter for active search items ──────────────────────────────────
    try:
        from groq_engine import is_noise, GROQ_API_KEY
        if GROQ_API_KEY:
            filtered_raw = []
            noise_count  = 0
            for a in raw:
                if a.get("source") == "Google News" and a.get("_groq_confidence") == "low":
                    client = a.get("_pre_matched") or {}
                    if is_noise(a["headline"],
                                client.get("client_group",""),
                                client.get("indian_subsidiary","")):
                        noise_count += 1
                        continue
                filtered_raw.append(a)
            if noise_count:
                print(f"  Noise filter removed {noise_count} low-confidence items")
            raw = filtered_raw
    except Exception as ex:
        print(f"  Noise filter error: {ex}")

    # ── Enrich + deduplicate ──────────────────────────────────────────────────
    seen, enriched = set(), []
    for a in raw:
        key = a["headline"][:70].lower().strip()
        if key in seen:
            continue
        seen.add(key)

        if "client" not in a:
            client = a.pop("_pre_matched", None)
            if not client and a.get("ticker") and a["ticker"] in registry["by_ticker"]:
                client = registry["by_ticker"][a["ticker"]]
            if not client and a.get("company_name"):
                client = match_by_name(
                    a["company_name"] + " " + a["headline"], registry)
            a["client"]        = client
            a["is_scb_client"] = client is not None
        elif "_pre_matched" in a:
            if not a.get("client"):
                a["client"]        = a.pop("_pre_matched")
                a["is_scb_client"] = a["client"] is not None
            else:
                a.pop("_pre_matched", None)

        enriched.append(a)

    enriched.sort(key=lambda x: x["date"], reverse=True)

    scb = sum(1 for a in enriched if a["is_scb_client"])
    print(f"After dedup: {len(enriched)} unique | {scb} SCB clients")
    print(f"{'='*60}\n")
    return enriched
