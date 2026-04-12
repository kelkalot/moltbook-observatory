"""Aggregate statistics and snapshots."""

import json
import time
from datetime import datetime, timedelta
from observatory.database.connection import get_db, execute_query

# ---------------------------------------------------------------------------
# Cache entries: (monotonic_time, value)
# ---------------------------------------------------------------------------
_cache: dict[str, tuple[float, object]] = {}

def _cached(key: str, ttl: int):
    entry = _cache.get(key)
    if entry and time.monotonic() - entry[0] < ttl:
        return entry[1]
    return None

def _store(key: str, value):
    _cache[key] = (time.monotonic(), value)
    return value


def invalidate_stats_cache() -> None:
    """Invalidate all stats caches."""
    _cache.clear()


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

async def get_stats() -> dict:
    """Get current platform statistics (cached 5 min)."""
    cached = _cached("stats", 300)
    if cached is not None:
        return cached

    now = datetime.utcnow()
    today_start   = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    one_hour_ago  = (now - timedelta(hours=1)).isoformat()
    one_day_ago   = (now - timedelta(hours=24)).isoformat()

    # Single round-trip; covering index idx_posts_created_agent handles
    # the COUNT(DISTINCT agent_name) subqueries without touching the heap.
    result = await execute_query("""
        SELECT
            (SELECT COUNT(*) FROM agents)   AS total_agents,
            (SELECT COUNT(*) FROM posts)    AS total_posts,
            (SELECT COUNT(*) FROM comments) AS total_comments,
            (SELECT COUNT(*) FROM submolts) AS total_submolts,
            (SELECT COUNT(*)               FROM posts WHERE created_at >= ?) AS posts_today,
            (SELECT COUNT(DISTINCT agent_name) FROM posts WHERE created_at >= ?) AS active_agents_1h,
            (SELECT COUNT(DISTINCT agent_name) FROM posts WHERE created_at >= ?) AS active_agents_24h
    """, (today_start, one_hour_ago, one_day_ago))

    value = dict(result[0]) if result else {
        "total_agents": 0, "total_posts": 0, "total_comments": 0,
        "total_submolts": 0, "posts_today": 0,
        "active_agents_1h": 0, "active_agents_24h": 0,
    }
    return _store("stats", value)


async def get_new_agents_today() -> list[dict]:
    """Get agents first seen today (cached 5 min)."""
    cached = _cached("new_agents_today", 300)
    if cached is not None:
        return cached

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    # idx_agents_first_seen covers this query.
    result = await execute_query("""
        SELECT name, description, karma, first_seen_at
        FROM agents
        WHERE first_seen_at >= ?
        ORDER BY first_seen_at DESC
        LIMIT 10
    """, (today_start,))
    return _store("new_agents_today", result)


async def create_snapshot() -> None:
    """Create an hourly snapshot of platform metrics."""
    from observatory.analyzer.trends import get_top_words
    from observatory.analyzer.sentiment import get_recent_sentiment

    db = await get_db()
    stats     = await get_stats()
    sentiment = await get_recent_sentiment(hours=1)
    top_words = await get_top_words(hours=1, limit=10)

    await db.execute("""
        INSERT INTO snapshots (
            timestamp, total_agents, total_posts, total_comments,
            active_agents_24h, avg_sentiment, top_words
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().isoformat(),
        stats["total_agents"],
        stats["total_posts"],
        stats["total_comments"],
        stats["active_agents_24h"],
        sentiment["polarity"],
        json.dumps([w["word"] for w in top_words]),
    ))
    await db.commit()


async def get_snapshot_history(hours: int = 168) -> list[dict]:
    """Get snapshot history for the given number of hours (cached 5 min)."""
    cache_key = f"snapshot_history:{hours}"
    cached = _cached(cache_key, 300)
    if cached is not None:
        return cached

    start = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    # idx_snapshots_timestamp covers this range scan.
    snapshots = await execute_query("""
        SELECT timestamp, total_agents, total_posts, total_comments,
               active_agents_24h, avg_sentiment, top_words
        FROM snapshots
        WHERE timestamp >= ?
        ORDER BY timestamp ASC
    """, (start,))

    for s in snapshots:
        if s.get("top_words"):
            try:
                s["top_words"] = json.loads(s["top_words"])
            except json.JSONDecodeError:
                s["top_words"] = []

    return _store(cache_key, snapshots)


async def get_top_posters(limit: int = 20) -> list[dict]:
    """Get agents with the most posts (cached 5 min).

    idx_posts_agent_score (agent_name, score, created_at DESC) lets SQLite
    satisfy GROUP BY agent_name + SUM/AVG/MAX via an index-only scan.
    """
    cache_key = f"top_posters:{limit}"
    cached = _cached(cache_key, 300)
    if cached is not None:
        return cached

    result = await execute_query("""
        SELECT
            agent_name  AS name,
            COUNT(*)    AS post_count,
            SUM(score)  AS total_score,
            AVG(score)  AS avg_score,
            MAX(created_at) AS last_post
        FROM posts
        WHERE agent_name IS NOT NULL AND agent_name != ''
        GROUP BY agent_name
        ORDER BY post_count DESC
        LIMIT ?
    """, (limit,))
    return _store(cache_key, result)


async def get_activity_by_hour() -> list[dict]:
    """Get post activity grouped by hour of day UTC (cached 15 min).

    All-time histogram — changes slowly, so a longer TTL is appropriate.
    """
    cached = _cached("activity_by_hour", 900)
    if cached is not None:
        return cached

    result = await execute_query("""
        SELECT
            CAST(strftime('%H', created_at) AS INTEGER) AS hour,
            COUNT(*) AS post_count
        FROM posts
        WHERE created_at IS NOT NULL
        GROUP BY hour
        ORDER BY hour ASC
    """)
    return _store("activity_by_hour", result)


async def get_submolt_activity(limit: int = 20) -> list[dict]:
    """Get submolts ranked by post activity (cached 5 min).

    idx_posts_submolt_agent (submolt, agent_name, score, created_at DESC)
    lets SQLite resolve the GROUP BY + COUNT DISTINCT + aggregates without
    hitting the table heap.
    """
    cache_key = f"submolt_activity:{limit}"
    cached = _cached(cache_key, 300)
    if cached is not None:
        return cached

    result = await execute_query("""
        SELECT
            submolt                     AS name,
            COUNT(*)                    AS post_count,
            COUNT(DISTINCT agent_name)  AS unique_posters,
            SUM(score)                  AS total_score,
            AVG(score)                  AS avg_score,
            MAX(created_at)             AS last_post
        FROM posts
        WHERE submolt IS NOT NULL AND submolt != ''
        GROUP BY submolt
        ORDER BY post_count DESC
        LIMIT ?
    """, (limit,))
    return _store(cache_key, result)
