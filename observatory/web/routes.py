"""FastAPI routes for the Observatory web dashboard."""

import csv
import io
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from observatory.database.connection import execute_query
from observatory.analyzer.stats import (
    get_stats, get_new_agents_today, get_snapshot_history,
    get_top_posters, get_activity_by_hour, get_submolt_activity
)
from observatory.analyzer.trends import get_trending_words, get_top_words, get_word_history
from observatory.analyzer.sentiment import get_recent_sentiment
from observatory.config import config

router = APIRouter()

# Set up templates
templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))


# ============ PAGE ROUTES ============

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main dashboard page."""
    stats = await get_stats()
    sentiment = await get_recent_sentiment(hours=24)
    trends = await get_trending_words(hours=24, limit=5)
    new_agents = await get_new_agents_today()
    
    # Get recent posts
    posts = await execute_query("""
        SELECT id, agent_name, submolt, title, content, score, comment_count, created_at
        FROM posts
        ORDER BY created_at DESC
        LIMIT 20
    """)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "stats": stats,
        "sentiment": sentiment,
        "trends": trends,
        "new_agents": new_agents,
        "posts": posts,
    })


@router.get("/agents", response_class=HTMLResponse)
async def agents_page(
    request: Request,
    sort: str = Query("karma", pattern="^(karma|name|follower_count|first_seen_at)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    """Agent directory page."""
    order_sql = "DESC" if order == "desc" else "ASC"
    
    agents = await execute_query(f"""
        SELECT name, description, karma, follower_count, following_count,
               is_claimed, owner_x_handle, first_seen_at, created_at
        FROM agents
        ORDER BY {sort} {order_sql}
        LIMIT 100
    """)
    
    total_agents = await execute_query("SELECT COUNT(*) as count FROM agents")
    
    return templates.TemplateResponse("agents.html", {
        "request": request,
        "agents": agents,
        "total": total_agents[0]["count"] if total_agents else 0,
        "current_sort": sort,
        "current_order": order,
    })


@router.get("/agents/{name}", response_class=HTMLResponse)
async def agent_profile(request: Request, name: str):
    """Individual agent profile page."""
    agent = await execute_query("""
        SELECT name, description, karma, follower_count, following_count,
               is_claimed, owner_x_handle, first_seen_at, last_seen_at, created_at, avatar_url
        FROM agents WHERE name = ?
    """, (name,))
    
    if not agent:
        return templates.TemplateResponse("404.html", {
            "request": request,
            "message": f"Agent @{name} not found",
        }, status_code=404)
    
    # Get agent's posts
    posts = await execute_query("""
        SELECT id, submolt, title, content, score, comment_count, created_at
        FROM posts
        WHERE agent_name = ?
        ORDER BY created_at DESC
        LIMIT 20
    """, (name,))
    
    return templates.TemplateResponse("agent.html", {
        "request": request,
        "agent": agent[0],
        "posts": posts,
    })


@router.get("/trends", response_class=HTMLResponse)
async def trends_page(
    request: Request,
    hours: int = Query(24, ge=1, le=720),
):
    """Trends page with word frequency analysis."""
    trends = await get_trending_words(hours=hours, limit=20)
    top_words = await get_top_words(hours=hours, limit=20)
    sentiment = await get_recent_sentiment(hours=hours)
    
    # Get snapshot history for charts
    snapshots = await get_snapshot_history(hours=hours)
    
    return templates.TemplateResponse("trends.html", {
        "request": request,
        "trends": trends,
        "top_words": top_words,
        "sentiment": sentiment,
        "snapshots": snapshots,
        "hours": hours,
    })


@router.get("/submolts", response_class=HTMLResponse)
async def submolts_page(request: Request):
    """Submolts (communities) directory page."""
    submolts = await execute_query("""
        SELECT name, display_name, description, subscriber_count, post_count,
               created_at, first_seen_at
        FROM submolts
        ORDER BY subscriber_count DESC
    """)
    
    return templates.TemplateResponse("submolts.html", {
        "request": request,
        "submolts": submolts,
    })


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    """Analytics and insights page."""
    top_posters = await get_top_posters(limit=15)
    activity_by_hour = await get_activity_by_hour()
    submolt_activity = await get_submolt_activity(limit=15)
    stats = await get_stats()
    
    # Fill in missing hours and calculate log height
    hours_data = {h["hour"]: h["post_count"] for h in activity_by_hour}
    full_activity = []
    
    # Calculate max for log scaling
    max_posts = max(hours_data.values()) if hours_data else 1
    import math
    
    for h in range(24):
        count = hours_data.get(h, 0)
        # Log scale: log(count+1) / log(max+1) * 100
        if count > 0:
            log_height = int((math.log(count + 1) / math.log(max_posts + 1)) * 100)
            # Ensure minimum visibility for small non-zero counts
            log_height = max(log_height, 5) 
        else:
            log_height = 0
            
        full_activity.append({
            "hour": h, 
            "post_count": count,
            "height_pct": log_height
        })
    
    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "top_posters": top_posters,
        "activity_by_hour": full_activity,
        "submolt_activity": submolt_activity,
        "stats": stats,
    })


@router.get("/export", response_class=HTMLResponse)
async def export_page(request: Request):
    """Data export page."""
    stats = await get_stats()
    
    return templates.TemplateResponse("export.html", {
        "request": request,
        "stats": stats,
    })


# ============ API ROUTES ============

@router.get("/api/feed")
async def api_feed(
    since: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
):
    """Get recent posts, optionally filtered by timestamp."""
    if since:
        posts = await execute_query("""
            SELECT id, agent_name, submolt, title, content, score, comment_count, created_at
            FROM posts
            WHERE created_at > ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (since, limit))
    else:
        posts = await execute_query("""
            SELECT id, agent_name, submolt, title, content, score, comment_count, created_at
            FROM posts
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
    
    return {"posts": posts, "count": len(posts)}


@router.get("/api/stats")
async def api_stats():
    """Get current platform statistics."""
    stats = await get_stats()
    sentiment = await get_recent_sentiment(hours=24)
    
    return {**stats, "sentiment": sentiment}


@router.get("/api/trends")
async def api_trends(hours: int = Query(24, ge=1, le=720)):
    """Get trending words."""
    trends = await get_trending_words(hours=hours, limit=10)
    return {"trends": trends, "period_hours": hours}


@router.get("/api/trends/history")
async def api_trends_history(word: str, days: int = Query(7, ge=1, le=30)):
    """Get word frequency history."""
    history = await get_word_history(word, days=days)
    return {"word": word, "history": history}


@router.get("/api/agents")
async def api_agents(
    limit: int = Query(50, ge=1, le=200),
    sort: str = Query("karma", pattern="^(karma|name|follower_count)$"),
):
    """Get all agents."""
    order = "DESC" if sort in ("karma", "follower_count") else "ASC"
    
    agents = await execute_query(f"""
        SELECT name, description, karma, follower_count, following_count, is_claimed
        FROM agents
        ORDER BY {sort} {order}
        LIMIT ?
    """, (limit,))
    
    return {"agents": agents, "count": len(agents)}


@router.get("/api/agents/{name}")
async def api_agent(name: str):
    """Get single agent details."""
    agent = await execute_query("""
        SELECT name, description, karma, follower_count, following_count,
               is_claimed, owner_x_handle, first_seen_at, last_seen_at, created_at
        FROM agents WHERE name = ?
    """, (name,))
    
    if not agent:
        return {"error": "Agent not found"}, 404
    
    posts = await execute_query("""
        SELECT id, submolt, title, score, comment_count, created_at
        FROM posts WHERE agent_name = ?
        ORDER BY created_at DESC LIMIT 10
    """, (name,))
    
    return {"agent": agent[0], "recent_posts": posts}


@router.get("/api/submolts")
async def api_submolts():
    """Get all submolts."""
    submolts = await execute_query("""
        SELECT name, display_name, description, subscriber_count, post_count
        FROM submolts
        ORDER BY subscriber_count DESC
    """)
    
    return {"submolts": submolts}


@router.get("/api/analytics/top-posters")
async def api_top_posters(limit: int = Query(20, ge=1, le=100)):
    """Get agents ranked by post count."""
    posters = await get_top_posters(limit=limit)
    return {"top_posters": posters}


@router.get("/api/analytics/activity-by-hour")
async def api_activity_by_hour():
    """Get post activity grouped by hour of day."""
    activity = await get_activity_by_hour()
    # Fill in missing hours with 0
    hours_data = {h["hour"]: h["post_count"] for h in activity}
    full_activity = [{"hour": h, "post_count": hours_data.get(h, 0)} for h in range(24)]
    return {"activity_by_hour": full_activity}


@router.get("/api/analytics/submolt-activity")
async def api_submolt_activity(limit: int = Query(20, ge=1, le=100)):
    """Get submolts ranked by post activity."""
    activity = await get_submolt_activity(limit=limit)
    return {"submolt_activity": activity}


@router.get("/api/graph")
async def api_graph():
    """Get social graph data for visualization."""
    # Get all agents as nodes
    agents = await execute_query("""
        SELECT name, karma, follower_count
        FROM agents
        WHERE karma > 0
        ORDER BY karma DESC
        LIMIT 100
    """)
    
    nodes = [{"id": a["name"], "karma": a["karma"], "followers": a["follower_count"]} for a in agents]
    
    # Get follow relationships
    edges = await execute_query("""
        SELECT follower_id, following_id
        FROM follows
    """)
    
    links = [{"source": e["follower_id"], "target": e["following_id"]} for e in edges]
    
    return {"nodes": nodes, "links": links}


# ============ EXPORT ROUTES ============

@router.get("/api/export/posts.csv")
async def export_posts_csv():
    """Export all posts as CSV."""
    posts = await execute_query("""
        SELECT id, agent_name, submolt, title, content, score, comment_count, created_at
        FROM posts ORDER BY created_at DESC
    """)
    
    # Convert rows to dicts and construct URLs
    data = []
    for post in posts:
        row = dict(post)
        row["url"] = f"https://moltbook.com/post/{row['id']}"
        data.append(row)
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id", "agent_name", "submolt", "title", "content", "url", "score", "comment_count", "created_at"])
    writer.writeheader()
    writer.writerows(data)
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=moltbook_posts.csv"}
    )


@router.get("/api/export/agents.csv")
async def export_agents_csv():
    """Export all agents as CSV."""
    agents = await execute_query("""
        SELECT name, description, karma, follower_count, following_count,
               is_claimed, owner_x_handle, first_seen_at, created_at
        FROM agents ORDER BY karma DESC
    """)
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["name", "description", "karma", "follower_count", "following_count", "is_claimed", "owner_x_handle", "first_seen_at", "created_at"])
    writer.writeheader()
    writer.writerows(agents)
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=moltbook_agents.csv"}
    )


@router.get("/api/export/database.db")
async def export_database():
    """Download the SQLite database file."""
    if config.DATABASE_PATH.exists():
        return FileResponse(
            config.DATABASE_PATH,
            media_type="application/x-sqlite3",
            filename="moltbook_observatory.db"
        )
    return {"error": "Database not found"}, 404


# ============ HTMX PARTIALS ============

@router.get("/partials/feed", response_class=HTMLResponse)
async def feed_partial(request: Request, since: Optional[str] = None):
    """HTMX partial for feed updates."""
    if since:
        posts = await execute_query("""
            SELECT id, agent_name, submolt, title, content, score, comment_count, created_at
            FROM posts
            WHERE created_at > ?
            ORDER BY created_at DESC
            LIMIT 10
        """, (since,))
    else:
        posts = await execute_query("""
            SELECT id, agent_name, submolt, title, content, score, comment_count, created_at
            FROM posts
            ORDER BY created_at DESC
            LIMIT 10
        """)
    
    return templates.TemplateResponse("feed.html", {
        "request": request,
        "posts": posts,
    })


@router.get("/partials/stats", response_class=HTMLResponse)
async def stats_partial(request: Request):
    """HTMX partial for stats updates."""
    stats = await get_stats()
    sentiment = await get_recent_sentiment(hours=24)
    
    return templates.TemplateResponse("stats_partial.html", {
        "request": request,
        "stats": stats,
        "sentiment": sentiment,
    })
