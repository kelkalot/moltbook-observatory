"""Aggregate statistics and snapshots."""

import json
from datetime import datetime, timedelta
from observatory.database.connection import get_db, execute_query


async def get_stats() -> dict:
    """Get current platform statistics."""
    db = await get_db()
    
    # Total counts
    agents_result = await execute_query("SELECT COUNT(*) as count FROM agents")
    posts_result = await execute_query("SELECT COUNT(*) as count FROM posts")
    comments_result = await execute_query("SELECT COUNT(*) as count FROM comments")
    submolts_result = await execute_query("SELECT COUNT(*) as count FROM submolts")
    
    # Today's counts
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    posts_today = await execute_query(
        "SELECT COUNT(*) as count FROM posts WHERE created_at >= ?",
        (today_start,)
    )
    
    # Active in last hour
    one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    active_1h = await execute_query("""
        SELECT COUNT(DISTINCT agent_name) as count FROM posts
        WHERE created_at >= ?
    """, (one_hour_ago,))
    
    # Active in last 24 hours
    one_day_ago = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    active_24h = await execute_query("""
        SELECT COUNT(DISTINCT agent_name) as count FROM posts
        WHERE created_at >= ?
    """, (one_day_ago,))
    
    return {
        "total_agents": agents_result[0]["count"] if agents_result else 0,
        "total_posts": posts_result[0]["count"] if posts_result else 0,
        "total_comments": comments_result[0]["count"] if comments_result else 0,
        "total_submolts": submolts_result[0]["count"] if submolts_result else 0,
        "posts_today": posts_today[0]["count"] if posts_today else 0,
        "active_agents_1h": active_1h[0]["count"] if active_1h else 0,
        "active_agents_24h": active_24h[0]["count"] if active_24h else 0,
    }


async def get_new_agents_today() -> list[dict]:
    """Get agents first seen today."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    return await execute_query("""
        SELECT name, description, karma, first_seen_at
        FROM agents
        WHERE first_seen_at >= ?
        ORDER BY first_seen_at DESC
        LIMIT 10
    """, (today_start,))


async def create_snapshot() -> None:
    """Create an hourly snapshot of platform metrics."""
    from observatory.analyzer.trends import get_top_words
    from observatory.analyzer.sentiment import get_recent_sentiment
    
    db = await get_db()
    stats = await get_stats()
    sentiment = await get_recent_sentiment(hours=1)
    top_words = await get_top_words(hours=1, limit=10)
    
    await db.execute("""
        INSERT INTO snapshots (
            timestamp, total_agents, total_posts, total_comments,
            active_agents_24h, avg_sentiment, top_words
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
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
    """Get snapshot history for the given number of hours."""
    start = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    
    snapshots = await execute_query("""
        SELECT timestamp, total_agents, total_posts, total_comments,
               active_agents_24h, avg_sentiment, top_words
        FROM snapshots
        WHERE timestamp >= ?
        ORDER BY timestamp ASC
    """, (start,))
    
    # Parse top_words JSON
    for s in snapshots:
        if s.get("top_words"):
            try:
                s["top_words"] = json.loads(s["top_words"])
            except json.JSONDecodeError:
                s["top_words"] = []
    
    return snapshots
