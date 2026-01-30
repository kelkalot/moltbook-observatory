"""Background scheduler for polling Moltbook."""

import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from observatory.config import config


async def poll_posts() -> None:
    """Fetch new posts from Moltbook."""
    from observatory.poller.client import get_client
    from observatory.poller.processors import process_posts
    
    try:
        client = await get_client()
        
        # Fetch newest posts
        data = await client.get_posts(sort="new", limit=50)
        new_count = await process_posts(data)
        
        if new_count > 0:
            print(f"[{datetime.now().isoformat()}] Fetched {new_count} new posts")
        
        # Also fetch hot posts to catch trending content
        data = await client.get_posts(sort="hot", limit=25)
        await process_posts(data)
        
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] Error polling posts: {e}")


async def poll_submolts() -> None:
    """Fetch submolt list and info."""
    from observatory.poller.client import get_client
    from observatory.poller.processors import process_submolts
    
    try:
        client = await get_client()
        data = await client.get_submolts()
        count = await process_submolts(data)
        print(f"[{datetime.now().isoformat()}] Updated {count} submolts")
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] Error polling submolts: {e}")


async def poll_agents() -> None:
    """Update agent profiles for known agents."""
    from observatory.database.connection import execute_query
    from observatory.poller.processors import process_agents
    
    try:
        # Get agents we haven't updated recently
        agents = await execute_query("""
            SELECT name FROM agents
            ORDER BY last_seen_at ASC
            LIMIT 20
        """)
        
        agent_names = [a["name"] for a in agents]
        if agent_names:
            updated = await process_agents(agent_names)
            print(f"[{datetime.now().isoformat()}] Updated {updated} agent profiles")
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] Error polling agents: {e}")


async def calculate_trends() -> None:
    """Calculate trending words from recent posts."""
    from observatory.analyzer.trends import update_word_frequency
    
    try:
        await update_word_frequency()
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] Error calculating trends: {e}")


async def take_snapshot() -> None:
    """Take an hourly snapshot of platform metrics."""
    from observatory.analyzer.stats import create_snapshot
    
    try:
        await create_snapshot()
        print(f"[{datetime.now().isoformat()}] Snapshot created")
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] Error taking snapshot: {e}")


def setup_scheduler() -> AsyncIOScheduler:
    """Set up and return the background scheduler."""
    scheduler = AsyncIOScheduler()
    
    # Poll posts every 2 minutes
    scheduler.add_job(
        poll_posts,
        IntervalTrigger(seconds=config.POLL_POSTS_INTERVAL),
        id="poll_posts",
        name="Poll new posts",
        replace_existing=True,
    )
    
    # Poll submolts every hour
    scheduler.add_job(
        poll_submolts,
        IntervalTrigger(seconds=config.POLL_SUBMOLTS_INTERVAL),
        id="poll_submolts",
        name="Poll submolts",
        replace_existing=True,
    )
    
    # Update agent profiles every 15 minutes
    scheduler.add_job(
        poll_agents,
        IntervalTrigger(seconds=config.POLL_AGENTS_INTERVAL),
        id="poll_agents",
        name="Poll agent profiles",
        replace_existing=True,
    )
    
    # Calculate trends every 10 minutes
    scheduler.add_job(
        calculate_trends,
        IntervalTrigger(minutes=10),
        id="calculate_trends",
        name="Calculate trends",
        replace_existing=True,
    )
    
    # Take snapshot every hour
    scheduler.add_job(
        take_snapshot,
        IntervalTrigger(hours=1),
        id="take_snapshot",
        name="Take hourly snapshot",
        replace_existing=True,
    )
    
    return scheduler


async def run_initial_poll() -> None:
    """Run an initial poll on startup."""
    print("Running initial data fetch...")
    await poll_submolts()
    await poll_posts()
    print("Initial fetch complete")
