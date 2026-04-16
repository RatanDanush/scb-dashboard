"""
batch_manager.py
----------------
Manages the staggered Groq web search across all 390 clients.

Every app refresh (30 min), processes the next batch of 20 clients.
Results stored in web_search_cache.json on disk.

Batch priority order:
  1. Never searched  → highest priority
  2. Searched > 24h ago
  3. Searched 12-24h ago
  4. Searched < 12h ago  → skip

Full cycle: 390 clients ÷ 20 per batch = ~20 batches = ~10 hours
"""

import json
import os
import datetime
import time
import streamlit as st

CACHE_FILE  = "web_search_cache.json"
BATCH_SIZE  = 20
MIN_REFRESH_HOURS   = 12    # don't re-search a client within 12 hours
BATCH_COOLDOWN_MINS = 25    # don't run two batches within 25 minutes


# ─── Cache I/O ───────────────────────────────────────────────────────────────

def load_cache() -> dict:
    """Load the web search results cache from disk."""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
    except Exception as ex:
        print(f"  Cache load error: {ex}")
    return {}

def save_cache(data: dict):
    """Save cache to disk."""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as ex:
        print(f"  Cache save error: {ex}")


# ─── Batch logic ─────────────────────────────────────────────────────────────

def _client_key(rec: dict) -> str:
    """Unique key for a client record."""
    return f"{rec.get('client_group','')}|{rec.get('indian_subsidiary','')}"

def _hours_since(iso_str: str) -> float:
    """Hours since a given ISO datetime string."""
    try:
        then = datetime.datetime.fromisoformat(iso_str)
        return (datetime.datetime.now() - then).total_seconds() / 3600
    except Exception:
        return 9999.0

def get_next_batch(registry: dict, cache: dict) -> list:
    """
    Returns the next 20 clients to search, prioritised by staleness.
    Skips clients searched within MIN_REFRESH_HOURS.
    """
    all_recs = [r for r in registry["all"]
                if r.get("indian_subsidiary") and r.get("client_group")]

    # Score each client for priority (higher = search sooner)
    def priority(rec):
        key   = _client_key(rec)
        entry = cache.get(key, {})
        last  = entry.get("last_searched")
        hours = _hours_since(last) if last else 9999.0
        prio  = rec.get("priority_score", 0) or 0

        if hours >= 9999:     return (0, -prio)   # never searched — top priority
        if hours >= 24:       return (1, -prio)   # stale
        if hours >= 12:       return (2, -prio)   # semi-fresh
        return (99, 0)                             # fresh — skip

    ranked = sorted(all_recs, key=priority)
    # Filter out those searched within 12h
    batch = [r for r in ranked
             if _hours_since(cache.get(_client_key(r), {}).get("last_searched",""))
             >= MIN_REFRESH_HOURS]

    return batch[:BATCH_SIZE]

def mark_searched(cache: dict, rec: dict, events: list) -> dict:
    """Record search results for a client."""
    key = _client_key(rec)
    cache[key] = {
        "last_searched": datetime.datetime.now().isoformat(),
        "events":        events,
        "client_group":  rec.get("client_group", ""),
        "subsidiary":    rec.get("indian_subsidiary", ""),
    }
    return cache

def should_run_batch(cache: dict) -> bool:
    """
    Returns True if enough time has passed since the last batch ran.
    Prevents double-running on manual refreshes.
    """
    last_run = cache.get("_meta", {}).get("last_batch_run")
    if not last_run:
        return True
    mins = _hours_since(last_run) * 60
    return mins >= BATCH_COOLDOWN_MINS

def mark_batch_run(cache: dict) -> dict:
    """Record that a batch just ran."""
    if "_meta" not in cache:
        cache["_meta"] = {}
    cache["_meta"]["last_batch_run"] = datetime.datetime.now().isoformat()
    return cache


# ─── Progress ────────────────────────────────────────────────────────────────

def get_progress(registry: dict, cache: dict) -> dict:
    """
    Returns progress info for the UI status chip.
    """
    all_recs  = [r for r in registry["all"]
                 if r.get("indian_subsidiary") and r.get("client_group")]
    total     = len(all_recs)
    searched  = sum(1 for r in all_recs
                    if _client_key(r) in cache and
                    _client_key(r) != "_meta")
    fresh     = sum(1 for r in all_recs
                    if _hours_since(cache.get(_client_key(r), {})
                                    .get("last_searched","")) < 24)

    last_run  = cache.get("_meta", {}).get("last_batch_run", "")
    mins_ago  = int(_hours_since(last_run) * 60) if last_run else None
    next_in   = max(0, BATCH_COOLDOWN_MINS - (mins_ago or BATCH_COOLDOWN_MINS))

    # Estimate batches remaining for full cycle
    stale     = sum(1 for r in all_recs
                    if _hours_since(cache.get(_client_key(r), {})
                                    .get("last_searched","")) >= MIN_REFRESH_HOURS)
    batches_left = max(0, -(-stale // BATCH_SIZE))   # ceiling division

    return {
        "total":        total,
        "searched":     searched,
        "fresh_24h":    fresh,
        "stale":        stale,
        "pct":          round(100 * fresh / total) if total else 0,
        "next_in_mins": next_in,
        "batches_left": batches_left,
        "last_run_mins_ago": mins_ago,
    }


# ─── All events from cache ────────────────────────────────────────────────────

def get_all_cached_events(registry: dict, cache: dict) -> list:
    """
    Pull all web-search-found events from the cache and return
    them as action dicts ready for the main feed.
    """
    # Build lookup: key → registry record
    by_key = {_client_key(r): r for r in registry["all"]}

    all_actions = []
    for key, entry in cache.items():
        if key == "_meta":
            continue
        events = entry.get("events", [])
        rec    = by_key.get(key)
        for ev in events:
            action = {
                "company_name":   entry.get("subsidiary", "")[:60],
                "ticker":         rec.get("ticker") if rec else None,
                "action_type":    ev.get("action_type", "Other"),
                "headline":       ev.get("headline", "")[:200],
                "date":           str(ev.get("date", ""))[:10],
                "amount":         ev.get("amount"),
                "currency":       ev.get("currency", "USD"),
                "source":         "Groq web search",
                "raw_detail":     ev.get("fx_implication", ev.get("raw_detail",""))[:300],
                "url":            ev.get("url", ""),
                "foreign_entity": ev.get("counterparty", ev.get("foreign_entity")),
                "_significance":  ev.get("significance", "Medium"),
                "_pre_matched":   rec,
            }
            all_actions.append(action)

    print(f"  Cache: {len(all_actions)} events from {len(cache)-1} searched clients")
    return all_actions


# ─── Main runner ─────────────────────────────────────────────────────────────

def run_next_batch(registry: dict) -> dict:
    """
    Called on each app refresh.
    Loads cache, runs next batch of web searches, saves cache.
    Returns updated cache.
    """
    from groq_engine import web_search_client, GROQ_API_KEY
    if not GROQ_API_KEY:
        return load_cache()

    cache = load_cache()

    if not should_run_batch(cache):
        print("  Batch manager: cooldown active, skipping this refresh")
        return cache

    batch = get_next_batch(registry, cache)
    if not batch:
        print("  Batch manager: all clients fresh, nothing to search")
        return cache

    print(f"  Batch manager: searching {len(batch)} clients...")
    cache = mark_batch_run(cache)

    for rec in batch:
        sub = rec.get("indian_subsidiary","")
        try:
            events = web_search_client(rec)
            cache  = mark_searched(cache, rec, events)
            print(f"    ✓ {sub[:40]} — {len(events)} events")
            time.sleep(2)   # rate limit buffer
        except Exception as ex:
            print(f"    ✗ {sub[:40]} — error: {ex}")
            cache = mark_searched(cache, rec, [])   # mark as searched even on error

    save_cache(cache)
    print(f"  Batch complete. Cache now has {len(cache)-1} clients.")
    return cache
