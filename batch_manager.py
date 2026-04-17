"""
batch_manager.py  v2
--------------------
Signal-triggered Groq web search with token-aware priority.

Priority order for Groq web search:
  P1 — Signal-triggered: RSS/Google News found M&A/FDI/Strategic/IPO/Buyback
       for this client this refresh → search regardless of tier
  P2 — Tier 1 fill: high-value clients with no RSS signal today
  P3 — Tier 2 fill: if budget still remains
  P4 — Everyone else: Google News RSS only

Budget cap: 65,000 tokens for web search per day
Resets midnight UTC (5:30am IST)
"""

import json, os, datetime, time
import streamlit as st

CACHE_FILE          = "web_search_cache.json"
BATCH_COOLDOWN_MINS = 0.5   # 30 seconds between batches


# ─── Cache I/O ────────────────────────────────────────────────────────────────

def load_cache() -> dict:
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                return json.load(f)
    except Exception as ex:
        print(f"  Cache load error: {ex}")
    return {}

def save_cache(data: dict):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as ex:
        print(f"  Cache save error: {ex}")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _client_key(rec: dict) -> str:
    return f"{rec.get('client_group','')}|{rec.get('indian_subsidiary','')}"

def _hours_since(iso_str: str) -> float:
    try:
        then = datetime.datetime.fromisoformat(iso_str)
        return (datetime.datetime.now() - then).total_seconds() / 3600
    except Exception:
        return 9999.0

def should_run_batch(cache: dict) -> bool:
    last = cache.get("_meta", {}).get("last_batch_run")
    if not last:
        return True
    return _hours_since(last) * 60 >= BATCH_COOLDOWN_MINS

def mark_batch_run(cache: dict) -> dict:
    if "_meta" not in cache:
        cache["_meta"] = {}
    cache["_meta"]["last_batch_run"] = datetime.datetime.now().isoformat()
    return cache

def mark_searched(cache: dict, rec: dict, events: list) -> dict:
    key = _client_key(rec)
    cache[key] = {
        "last_searched":  datetime.datetime.now().isoformat(),
        "events":         events,
        "client_group":   rec.get("client_group",""),
        "subsidiary":     rec.get("indian_subsidiary",""),
    }
    return cache


# ─── Priority queue builder ───────────────────────────────────────────────────

def build_priority_queue(registry: dict,
                         signal_clients: set,
                         cache: dict) -> list:
    """
    Build ordered list of clients to Groq web search.

    signal_clients: set of client_keys where RSS/GNews found
                    M&A/FDI/Strategic/IPO/Buyback this refresh

    Priority:
      P1 — in signal_clients (any tier)
      P2 — Tier 1, not in signal_clients, not searched today
      P3 — Tier 2, not in signal_clients, not searched today
      P4 — everyone else (skipped — RSS only)
    """
    from token_tracker import client_already_searched

    all_recs = [r for r in registry["all"]
                if r.get("indian_subsidiary") and r.get("client_group")]

    p1, p2, p3 = [], [], []

    for rec in all_recs:
        key = _client_key(rec)

        # Skip if already searched today (token tracker tracks this)
        if client_already_searched(key):
            continue

        tier = rec.get("priority_tier","") or ""

        if key in signal_clients:
            p1.append(rec)                         # always search
        elif "TIER 1" in tier.upper():
            p2.append(rec)
        elif "TIER 2" in tier.upper():
            p3.append(rec)

    # Sort within each priority by NIH exposure desc
    for lst in [p1, p2, p3]:
        lst.sort(key=lambda r: r.get("net_nih_exposure",0) or 0, reverse=True)

    return p1 + p2 + p3


# ─── Main runner ──────────────────────────────────────────────────────────────

def run_next_batch(registry: dict,
                   signal_clients: set = None) -> dict:
    """
    Called after main feed loads.
    signal_clients: set of client_keys that had trigger-worthy RSS signals.
    """
    from groq_engine import web_search_client, GROQ_API_KEY
    from token_tracker import can_afford, get_status

    if not GROQ_API_KEY:
        return load_cache()

    cache = load_cache()

    if not should_run_batch(cache):
        print("  Batch: cooldown active, skipping")
        return cache

    if signal_clients is None:
        signal_clients = set()

    queue = build_priority_queue(registry, signal_clients, cache)

    if not queue:
        print("  Batch: nothing to search")
        return cache

    print(f"  Batch: {len(queue)} clients queued "
          f"({len(signal_clients)} signal-triggered)")
    cache = mark_batch_run(cache)

    searched = 0
    for rec in queue:
        # Check token budget before each call
        if not can_afford("web_search", 1200):
            status = get_status()
            print(f"  Batch: web search budget reached "
                  f"({status['by_function'].get('web_search',0):,} / "
                  f"65,000 tokens used). "
                  f"Remaining clients will use RSS only.")
            break

        sub = rec.get("indian_subsidiary","")
        try:
            events = web_search_client(rec)
            cache  = mark_searched(cache, rec, events)
            print(f"    ✓ {sub[:35]:<35} {len(events)} events")
            searched += 1
            time.sleep(2)   # rate limit buffer
        except Exception as ex:
            err = str(ex)
            if "budget exhausted" in err.lower() or "rate_limit" in err.lower():
                print(f"  Batch stopped: {err[:80]}")
                break
            print(f"    ✗ {sub[:35]} — {err[:50]}")
            cache = mark_searched(cache, rec, [])

    save_cache(cache)
    print(f"  Batch complete: {searched} clients searched")
    return cache


# ─── Progress + cached events ────────────────────────────────────────────────

def get_progress(registry: dict, cache: dict) -> dict:
    from token_tracker import get_status
    tok = get_status()

    all_recs = [r for r in registry["all"]
                if r.get("indian_subsidiary") and r.get("client_group")]
    total    = len(all_recs)
    fresh    = sum(1 for r in all_recs
                   if _hours_since(cache.get(_client_key(r),{})
                                   .get("last_searched","")) < 24)

    last_run  = cache.get("_meta",{}).get("last_batch_run","")
    mins_ago  = int(_hours_since(last_run) * 60) if last_run else None
    next_in   = max(0, BATCH_COOLDOWN_MINS - (mins_ago or BATCH_COOLDOWN_MINS))

    return {
        "total":             total,
        "fresh_24h":         fresh,
        "pct":               round(100 * fresh / total) if total else 0,
        "next_in_mins":      round(next_in, 1),
        "token_used":        tok["total_used"],
        "token_budget":      tok["total_budget"],
        "token_pct":         tok["pct"],
        "token_web_clients": tok["web_search_clients"],
        "token_at_limit":    tok["at_limit"],
        "token_web_full":    tok["web_search_full"],
        "token_reset":       tok["ist_reset"],
        "hours_to_reset":    tok["hours_until_reset"],
    }

def get_all_cached_events(registry: dict, cache: dict) -> list:
    by_key = {_client_key(r): r for r in registry["all"]}
    out    = []
    for key, entry in cache.items():
        if key == "_meta": continue
        rec    = by_key.get(key)
        events = entry.get("events", [])
        for ev in events:
            out.append({
                "company_name":   entry.get("subsidiary","")[:60],
                "ticker":         rec.get("ticker") if rec else None,
                "action_type":    ev.get("action_type","Other"),
                "headline":       ev.get("headline","")[:200],
                "date":           str(ev.get("date",""))[:10],
                "amount":         ev.get("amount"),
                "currency":       ev.get("currency","USD"),
                "source":         "Groq web search",
                "raw_detail":     ev.get("fx_implication",
                                         ev.get("raw_detail",""))[:300],
                "url":            ev.get("url","") or "",
                "foreign_entity": ev.get("counterparty",
                                         ev.get("foreign_entity")),
                "_significance":  ev.get("significance","Medium"),
                "_pre_matched":   rec,
            })
    print(f"  Cache: {len(out)} events from {len(cache)-1} searched clients")
    return out
