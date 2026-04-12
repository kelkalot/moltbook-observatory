"""FastAPI routes for the Observatory web dashboard."""

import csv
import io
from typing import Optional
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse
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
from observatory.cache import get_cache

router = APIRouter()

# Set up templates
templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))

# Cache-Control header values
_CC_SHORT   = "public, max-age=30, s-maxage=60"     # live feed / index
_CC_MEDIUM  = "public, max-age=60, s-maxage=120"    # lists (agents, submolts)
_CC_LONG    = "public, max-age=120, s-maxage=300"   # profiles, trends, analytics
_CC_STATIC  = "public, max-age=300, s-maxage=600"   # posts, graph (rarely change)
_CC_NOSTORE = "no-store"                             # exports, search, refresh


# ============ PAGE ROUTES ============

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main dashboard page."""
    import asyncio

    cache = get_cache()
    cached = cache.get("index:dashboard")
    if cached is not None:
        stats, sentiment, trends, new_agents, posts = cached
    else:
        stats, sentiment, trends, new_agents, posts = await asyncio.gather(
            get_stats(),
            get_recent_sentiment(hours=24),
            get_trending_words(hours=24, limit=5),
            get_new_agents_today(),
            execute_query("""
                SELECT id, agent_name, submolt, title, content, score, comment_count, created_at
                FROM posts
                ORDER BY created_at DESC
                LIMIT 20
            """)
        )
        cache.set("index:dashboard", (stats, sentiment, trends, new_agents, posts), ttl_seconds=30)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "stats": stats,
        "sentiment": sentiment,
        "trends": trends,
        "new_agents": new_agents,
        "posts": posts,
        "config": config,
    }, headers={"Cache-Control": _CC_SHORT})


@router.get("/agents", response_class=HTMLResponse)
async def agents_page(
    request: Request,
    sort: str = Query("karma", pattern="^(karma|name|follower_count|first_seen_at)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
):
    """Agent directory page with pagination and search."""
    import asyncio
    order_sql = "DESC" if order == "desc" else "ASC"
    page_size = 20
    offset = (page - 1) * page_size

    where_clause = ""
    params = []
    if search:
        where_clause = "WHERE (name LIKE ? OR description LIKE ?)"
        search_term = f"%{search}%"
        params = [search_term, search_term]

    total_result, agents = await asyncio.gather(
        execute_query(f"SELECT COUNT(*) as count FROM agents {where_clause}", tuple(params)),
        execute_query(f"""
            SELECT name, description, karma, follower_count, following_count,
                   is_claimed, owner_x_handle, first_seen_at, created_at
            FROM agents
            {where_clause}
            ORDER BY {sort} {order_sql}
            LIMIT ? OFFSET ?
        """, tuple(params + [page_size, offset])),
    )

    total_agents = total_result[0]["count"] if total_result else 0
    total_pages = (total_agents + page_size - 1) // page_size

    return templates.TemplateResponse("agents.html", {
        "request": request,
        "agents": agents,
        "total": total_agents,
        "current_sort": sort,
        "current_order": order,
        "current_search": search or "",
        "page": page,
        "total_pages": total_pages,
        "page_size": page_size,
        "config": config,
    }, headers={"Cache-Control": _CC_MEDIUM})


@router.get("/agents/{name}", response_class=HTMLResponse)
async def agent_profile(
    request: Request,
    name: str,
    refresh: bool = Query(False, description="Refresh stats from API"),
):
    """Individual agent profile page."""
    import asyncio

    cache = get_cache()
    cache_key = f"agent_profile:{name}"

    if refresh:
        cache.clear(cache_key)
        try:
            from observatory.poller.client import get_client
            from observatory.poller.processors import process_agent_profile
            client = await get_client()
            profile = await client.get_agent_profile(name)
            await process_agent_profile(profile)
        except Exception as e:
            print(f"Failed to refresh agent {name}: {e}")

    cached = cache.get(cache_key)
    if cached is not None:
        agent_data, posts = cached
    else:
        agent, post_count_result, posts = await asyncio.gather(
            execute_query("""
                SELECT name, description, karma, follower_count, following_count,
                       is_claimed, owner_x_handle, first_seen_at, last_seen_at, created_at, avatar_url
                FROM agents WHERE name = ?
            """, (name,)),
            execute_query("SELECT COUNT(*) as count FROM posts WHERE agent_name = ?", (name,)),
            execute_query("""
                SELECT id, submolt, title, content, score, comment_count, created_at
                FROM posts
                WHERE agent_name = ?
                ORDER BY created_at DESC
                LIMIT 20
            """, (name,)),
        )

        if not agent:
            return templates.TemplateResponse("404.html", {
                "request": request,
                "message": f"Agent @{name} not found",
                "config": config,
            }, status_code=404)

        agent_data = dict(agent[0])
        agent_data["post_count"] = post_count_result[0]["count"] if post_count_result else 0
        if not refresh:
            cache.set(cache_key, (agent_data, posts), ttl_seconds=120)

    cc = _CC_NOSTORE if refresh else _CC_LONG
    return templates.TemplateResponse("agent.html", {
        "request": request,
        "agent": agent_data,
        "posts": posts,
        "config": config,
    }, headers={"Cache-Control": cc})


@router.get("/posts/{post_id}", response_class=HTMLResponse)
async def post_detail(request: Request, post_id: str):
    """Individual post detail page."""
    import asyncio

    cache = get_cache()
    cache_key = f"post_detail:{post_id}"
    cached = cache.get(cache_key)

    if cached is not None:
        post, comments = cached
    else:
        post, comments = await asyncio.gather(
            execute_query("""
                SELECT id, agent_name, submolt, title, content, score, comment_count, created_at
                FROM posts WHERE id = ?
            """, (post_id,)),
            execute_query("""
                SELECT id, agent_name, parent_id, content, score, created_at
                FROM comments WHERE post_id = ?
                ORDER BY created_at DESC LIMIT 50
            """, (post_id,)),
        )
        if post:
            cache.set(cache_key, (post, comments), ttl_seconds=300)

    if not post:
        return templates.TemplateResponse("404.html", {
            "request": request,
            "message": f"Post {post_id} not found",
            "config": config,
        }, status_code=404)

    return templates.TemplateResponse("post.html", {
        "request": request,
        "post": post[0],
        "comments": comments,
        "config": config,
    }, headers={"Cache-Control": _CC_STATIC})


@router.get("/submolts", response_class=HTMLResponse)
async def submolts_page(
    request: Request,
    sort: str = Query("subscriber_count", pattern="^(subscriber_count|name|post_count)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
):
    """Submolts (communities) directory page with pagination and search."""
    import asyncio
    order_sql = "DESC" if order == "desc" else "ASC"
    page_size = 20
    offset = (page - 1) * page_size

    where_clause = ""
    params = []
    if search:
        where_clause = "WHERE (name LIKE ? OR display_name LIKE ? OR description LIKE ?)"
        search_term = f"%{search}%"
        params = [search_term, search_term, search_term]

    total_result, submolts = await asyncio.gather(
        execute_query(f"SELECT COUNT(*) as count FROM submolts {where_clause}", tuple(params)),
        execute_query(f"""
            SELECT name, display_name, description, subscriber_count, post_count,
                   created_at, first_seen_at
            FROM submolts
            {where_clause}
            ORDER BY {sort} {order_sql}
            LIMIT ? OFFSET ?
        """, tuple(params + [page_size, offset])),
    )

    total_submolts = total_result[0]["count"] if total_result else 0
    total_pages = (total_submolts + page_size - 1) // page_size

    return templates.TemplateResponse("submolts.html", {
        "request": request,
        "submolts": submolts,
        "total": total_submolts,
        "current_sort": sort,
        "current_order": order,
        "current_search": search or "",
        "page": page,
        "total_pages": total_pages,
        "page_size": page_size,
        "config": config,
    }, headers={"Cache-Control": _CC_MEDIUM})


@router.get("/submolts/{name}", response_class=HTMLResponse)
async def submolt_detail(
    request: Request,
    name: str,
    refresh: bool = Query(False, description="Refresh stats from API"),
):
    """Individual submolt detail page."""
    import asyncio

    cache = get_cache()
    cache_key = f"submolt_detail:{name}"

    if refresh:
        cache.clear(cache_key)
        try:
            from observatory.poller.client import get_client
            from observatory.database.connection import get_db

            client = await get_client()
            data = await client.get_submolt(name)
            api_submolt_data = data.get("submolt", data)

            if api_submolt_data:
                db = await get_db()
                await db.execute("""
                    UPDATE submolts SET subscriber_count = ?, post_count = ?
                    WHERE name = ?
                """, (
                    api_submolt_data.get("subscriber_count", 0),
                    api_submolt_data.get("post_count", 0),
                    name,
                ))
                await db.commit()
        except Exception as e:
            print(f"Failed to refresh submolt {name}: {e}")

    cached = cache.get(cache_key)
    if cached is not None:
        submolt_data, posts = cached
    else:
        submolt, actual_post_count_result, posts = await asyncio.gather(
            execute_query("""
                SELECT name, display_name, description, subscriber_count, post_count,
                       created_at, first_seen_at, avatar_url, banner_url
                FROM submolts WHERE name = ?
            """, (name,)),
            execute_query("SELECT COUNT(*) as count FROM posts WHERE submolt = ?", (name,)),
            execute_query("""
                SELECT id, agent_name, title, content, score, comment_count, created_at
                FROM posts WHERE submolt = ?
                ORDER BY created_at DESC LIMIT 20
            """, (name,)),
        )

        if not submolt:
            return templates.TemplateResponse("404.html", {
                "request": request,
                "message": f"Submolt m/{name} not found",
                "config": config,
            }, status_code=404)

        submolt_data = dict(submolt[0])
        submolt_data["post_count"] = actual_post_count_result[0]["count"] if actual_post_count_result else 0
        if not refresh:
            cache.set(cache_key, (submolt_data, posts), ttl_seconds=120)

    cc = _CC_NOSTORE if refresh else _CC_LONG
    return templates.TemplateResponse("submolt.html", {
        "request": request,
        "submolt": submolt_data,
        "posts": posts,
        "config": config,
    }, headers={"Cache-Control": cc})


@router.get("/trends", response_class=HTMLResponse)
async def trends_page(
    request: Request,
    hours: int = Query(24, ge=1, le=720),
):
    """Trends and topic analysis page."""
    import asyncio

    cache = get_cache()
    cache_key = f"trends_page:{hours}"
    cached = cache.get(cache_key)
    if cached is not None:
        trends, top_words, sentiment, snapshots = cached
    else:
        trends, top_words, sentiment, snapshots = await asyncio.gather(
            get_trending_words(hours=hours, limit=10),
            get_top_words(hours=hours, limit=10),
            get_recent_sentiment(hours=hours),
            get_snapshot_history(hours=hours)
        )
        cache.set(cache_key, (trends, top_words, sentiment, snapshots), ttl_seconds=120)

    return templates.TemplateResponse("trends.html", {
        "request": request,
        "trends": trends,
        "top_words": top_words,
        "sentiment": sentiment,
        "snapshots": snapshots,
        "hours": hours,
        "config": config,
    }, headers={"Cache-Control": _CC_LONG})


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    """Analytics and insights page."""
    import asyncio
    import math

    cache = get_cache()
    cache_key = "analytics_page"
    cached = cache.get(cache_key)
    if cached is not None:
        top_posters, activity_by_hour, submolt_activity, stats = cached
    else:
        top_posters, activity_by_hour, submolt_activity, stats = await asyncio.gather(
            get_top_posters(limit=15),
            get_activity_by_hour(),
            get_submolt_activity(limit=15),
            get_stats()
        )
        cache.set(cache_key, (top_posters, activity_by_hour, submolt_activity, stats), ttl_seconds=120)

    hours_data = {h["hour"]: h["post_count"] for h in activity_by_hour}
    max_posts = max(hours_data.values()) if hours_data else 1
    full_activity = []
    for h in range(24):
        count = hours_data.get(h, 0)
        if count > 0 and max_posts > 0:
            sqrt_height = max(int((math.sqrt(count) / math.sqrt(max_posts)) * 100), 3)
        else:
            sqrt_height = 0
        full_activity.append({"hour": h, "post_count": count, "height_pct": sqrt_height})

    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "top_posters": top_posters,
        "activity_by_hour": full_activity,
        "submolt_activity": submolt_activity,
        "stats": stats,
        "config": config,
    }, headers={"Cache-Control": _CC_LONG})


@router.get("/export", response_class=HTMLResponse)
async def export_page(request: Request):
    """Data export page."""
    stats = await get_stats()

    return templates.TemplateResponse("export.html", {
        "request": request,
        "stats": stats,
        "config": config,
    }, headers={"Cache-Control": _CC_LONG})


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

    return JSONResponse({"posts": posts, "count": len(posts)},
                        headers={"Cache-Control": _CC_SHORT})


@router.get("/api/stats")
async def api_stats():
    """Get current platform statistics."""
    import asyncio

    cache = get_cache()
    cached = cache.get("api:stats")
    if cached is not None:
        stats, sentiment = cached
    else:
        stats, sentiment = await asyncio.gather(
            get_stats(),
            get_recent_sentiment(hours=24),
        )
        cache.set("api:stats", (stats, sentiment), ttl_seconds=60)

    return JSONResponse({**stats, "sentiment": sentiment},
                        headers={"Cache-Control": _CC_MEDIUM})


@router.get("/api/trends")
async def api_trends(hours: int = Query(24, ge=1, le=720)):
    """Get trending words."""
    cache = get_cache()
    cache_key = f"api:trends:{hours}"
    trends = cache.get(cache_key)
    if trends is None:
        trends = await get_trending_words(hours=hours, limit=10)
        cache.set(cache_key, trends, ttl_seconds=120)

    return JSONResponse({"trends": trends, "period_hours": hours},
                        headers={"Cache-Control": _CC_LONG})


@router.get("/api/trends/history")
async def api_trends_history(word: str, days: int = Query(7, ge=1, le=30)):
    """Get word frequency history."""
    history = await get_word_history(word, days=days)
    return JSONResponse({"word": word, "history": history},
                        headers={"Cache-Control": _CC_LONG})


@router.get("/api/agents")
async def api_agents(
    limit: int = Query(50, ge=1, le=200),
    sort: str = Query("karma", pattern="^(karma|name|follower_count)$"),
):
    """Get all agents."""
    cache = get_cache()
    cache_key = f"api:agents:{sort}:{limit}"
    agents = cache.get(cache_key)
    if agents is None:
        order = "DESC" if sort in ("karma", "follower_count") else "ASC"
        agents = await execute_query(f"""
            SELECT name, description, karma, follower_count, following_count, is_claimed
            FROM agents
            ORDER BY {sort} {order}
            LIMIT ?
        """, (limit,))
        cache.set(cache_key, agents, ttl_seconds=60)

    return JSONResponse({"agents": agents, "count": len(agents)},
                        headers={"Cache-Control": _CC_MEDIUM})


@router.get("/api/agents/{name}")
async def api_agent(name: str):
    """Get single agent details."""
    import asyncio

    cache = get_cache()
    cache_key = f"api:agent:{name}"
    cached = cache.get(cache_key)
    if cached is not None:
        agent_data, posts = cached
    else:
        agent, posts = await asyncio.gather(
            execute_query("""
                SELECT name, description, karma, follower_count, following_count,
                       is_claimed, owner_x_handle, first_seen_at, last_seen_at, created_at
                FROM agents WHERE name = ?
            """, (name,)),
            execute_query("""
                SELECT id, submolt, title, score, comment_count, created_at
                FROM posts WHERE agent_name = ?
                ORDER BY created_at DESC LIMIT 10
            """, (name,)),
        )

        if not agent:
            return JSONResponse({"error": "Agent not found"}, status_code=404)

        agent_data = agent[0]
        cache.set(cache_key, (agent_data, posts), ttl_seconds=120)

    return JSONResponse({"agent": agent_data, "recent_posts": posts},
                        headers={"Cache-Control": _CC_LONG})


@router.get("/api/submolts")
async def api_submolts():
    """Get all submolts."""
    cache = get_cache()
    submolts = cache.get("api:submolts")
    if submolts is None:
        submolts = await execute_query("""
            SELECT name, display_name, description, subscriber_count, post_count
            FROM submolts
            ORDER BY subscriber_count DESC
        """)
        cache.set("api:submolts", submolts, ttl_seconds=120)

    return JSONResponse({"submolts": submolts},
                        headers={"Cache-Control": _CC_LONG})


@router.get("/api/analytics/top-posters")
async def api_top_posters(limit: int = Query(20, ge=1, le=100)):
    """Get agents ranked by post count."""
    posters = await get_top_posters(limit=limit)
    return JSONResponse({"top_posters": posters},
                        headers={"Cache-Control": _CC_LONG})


@router.get("/api/analytics/activity-by-hour")
async def api_activity_by_hour():
    """Get post activity grouped by hour of day."""
    activity = await get_activity_by_hour()
    hours_data = {h["hour"]: h["post_count"] for h in activity}
    full_activity = [{"hour": h, "post_count": hours_data.get(h, 0)} for h in range(24)]
    return JSONResponse({"activity_by_hour": full_activity},
                        headers={"Cache-Control": _CC_LONG})


@router.get("/api/analytics/submolt-activity")
async def api_submolt_activity(limit: int = Query(20, ge=1, le=100)):
    """Get submolts ranked by post activity."""
    activity = await get_submolt_activity(limit=limit)
    return JSONResponse({"submolt_activity": activity},
                        headers={"Cache-Control": _CC_LONG})


@router.get("/api/graph")
async def api_graph():
    """Get social graph data for visualization."""
    import asyncio

    cache = get_cache()
    cached = cache.get("api:graph")
    if cached is not None:
        agents, edges = cached
    else:
        agents, edges = await asyncio.gather(
            execute_query("""
                SELECT name, karma, follower_count
                FROM agents WHERE karma > 0
                ORDER BY karma DESC LIMIT 100
            """),
            execute_query("SELECT follower_id, following_id FROM follows"),
        )
        cache.set("api:graph", (agents, edges), ttl_seconds=300)

    return JSONResponse({
        "nodes": [{"id": a["name"], "karma": a["karma"], "followers": a["follower_count"]} for a in agents],
        "links": [{"source": e["follower_id"], "target": e["following_id"]} for e in edges],
    }, headers={"Cache-Control": _CC_STATIC})


# ============ EXPORT ROUTES ============

@router.get("/api/export/posts.csv")
async def export_posts_csv():
    """Export all posts as CSV."""
    posts = await execute_query("""
        SELECT id, agent_name, submolt, title, content, score, comment_count, created_at
        FROM posts ORDER BY created_at DESC
    """)

    data = []
    for post in posts:
        row = dict(post)
        row["url"] = f"https://moltbook.com/post/{row['id']}"
        if row.get("content"):
            row["content"] = row["content"].replace('\r', '')
        if row.get("title"):
            row["title"] = row["title"].replace('\r', '')
        data.append(row)

    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=["id", "agent_name", "submolt", "title", "content", "url", "score", "comment_count", "created_at"], lineterminator='\n')
    writer.writeheader()
    writer.writerows(data)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=moltbook_posts.csv",
            "Cache-Control": _CC_NOSTORE,
        }
    )


@router.get("/api/export/agents.csv")
async def export_agents_csv():
    """Export all agents as CSV."""
    agents = await execute_query("""
        SELECT name, description, karma, follower_count, following_count,
               is_claimed, owner_x_handle, first_seen_at, created_at
        FROM agents ORDER BY karma DESC
    """)

    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=["name", "description", "karma", "follower_count", "following_count", "is_claimed", "owner_x_handle", "first_seen_at", "created_at"], lineterminator='\n')
    writer.writeheader()

    for agent in agents:
        row = dict(agent)
        if row.get("description"):
            row["description"] = row["description"].replace('\r', '')
        writer.writerow(row)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=moltbook_agents.csv",
            "Cache-Control": _CC_NOSTORE,
        }
    )


@router.get("/api/export/comments.csv")
async def export_comments_csv():
    """Export all comments as CSV."""
    comments = await execute_query("""
        SELECT id, post_id, agent_name, parent_id, content, score, created_at
        FROM comments ORDER BY created_at DESC
    """)

    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=["id", "post_id", "post_url", "agent_name", "parent_id", "content", "score", "created_at"], lineterminator='\n')
    writer.writeheader()

    for comment in comments:
        row = dict(comment)
        row["post_url"] = f"https://moltbook.com/post/{row['post_id']}"
        if row.get("content"):
            row["content"] = row["content"].replace('\r', '')
        writer.writerow(row)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=moltbook_comments.csv",
            "Cache-Control": _CC_NOSTORE,
        }
    )


@router.get("/api/export/database.db")
async def export_database():
    """Download the SQLite database file."""
    if config.DATABASE_PATH.exists():
        return FileResponse(
            config.DATABASE_PATH,
            media_type="application/x-sqlite3",
            filename="moltbook_observatory.db",
            headers={"Cache-Control": _CC_NOSTORE},
        )
    return JSONResponse({"error": "Database not found"}, status_code=404)


# ============ HTMX PARTIALS ============

@router.get("/partials/feed", response_class=HTMLResponse)
async def feed_partial(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100)
):
    """HTMX partial for feed updates with pagination."""
    import asyncio

    count_result, posts = await asyncio.gather(
        execute_query("SELECT COUNT(*) as count FROM posts"),
        execute_query("""
            SELECT id, agent_name, submolt, title, content, score, comment_count, created_at
            FROM posts
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (per_page, (page - 1) * per_page)),
    )

    total_posts = count_result[0]["count"] if count_result else 0
    total_pages = (total_posts + per_page - 1) // per_page if total_posts > 0 else 1

    return templates.TemplateResponse("feed.html", {
        "request": request,
        "posts": posts,
        "config": config,
        "page": page,
        "per_page": per_page,
        "total_posts": total_posts,
        "total_pages": total_pages,
    }, headers={"Cache-Control": _CC_SHORT})


@router.get("/search", response_class=HTMLResponse)
async def search_posts(
    request: Request,
    q: Optional[str] = Query(None, description="Search query for content/title"),
    author: Optional[str] = Query(None, description="Filter by author name"),
    submolt: Optional[str] = Query(None, description="Filter by submolt"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    min_score: Optional[int] = Query(None, ge=0, description="Minimum score"),
    sort: str = Query("created_at", pattern="^(created_at|score|comment_count)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """Search posts with multiple filters and pagination."""
    import asyncio
    where_conditions = []
    params = []

    if q:
        where_conditions.append("(content LIKE ? OR title LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    if author:
        where_conditions.append("agent_name LIKE ?")
        params.append(f"%{author}%")
    if submolt:
        where_conditions.append("submolt = ?")
        params.append(submolt)
    if date_from:
        where_conditions.append("DATE(created_at) >= ?")
        params.append(date_from)
    if date_to:
        where_conditions.append("DATE(created_at) <= ?")
        params.append(date_to)
    if min_score is not None:
        where_conditions.append("score >= ?")
        params.append(min_score)

    where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""
    order_sql = "DESC" if order == "desc" else "ASC"
    offset = (page - 1) * per_page

    count_result, posts = await asyncio.gather(
        execute_query(f"SELECT COUNT(*) as count FROM posts {where_clause}", tuple(params)),
        execute_query(f"""
            SELECT id, agent_name, submolt, title, content, score, comment_count, created_at
            FROM posts
            {where_clause}
            ORDER BY {sort} {order_sql}
            LIMIT ? OFFSET ?
        """, tuple(params + [per_page, offset])),
    )

    total_results = count_result[0]["count"] if count_result else 0
    total_pages = (total_results + per_page - 1) // per_page if total_results > 0 else 1

    return templates.TemplateResponse("search_results.html", {
        "request": request,
        "posts": posts,
        "config": config,
        "total_results": total_results,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "search_params": {
            "q": q or "",
            "author": author or "",
            "submolt": submolt or "",
            "date_from": date_from or "",
            "date_to": date_to or "",
            "min_score": min_score or "",
            "sort": sort,
            "order": order,
        },
    }, headers={"Cache-Control": _CC_NOSTORE})


@router.get("/partials/stats", response_class=HTMLResponse)
async def stats_partial(request: Request):
    """HTMX partial for stats updates."""
    import asyncio
    stats, sentiment = await asyncio.gather(
        get_stats(),
        get_recent_sentiment(hours=24),
    )

    return templates.TemplateResponse("stats_partial.html", {
        "request": request,
        "stats": stats,
        "sentiment": sentiment,
        "config": config,
    }, headers={"Cache-Control": _CC_SHORT})
