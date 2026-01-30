"""Process API responses into database records."""

from datetime import datetime
from observatory.database.connection import get_db


async def process_posts(posts_data: dict) -> int:
    """
    Process posts from API response and store in database.
    
    Returns number of new posts inserted.
    """
    db = await get_db()
    posts = posts_data.get("posts", [])
    if not posts:
        return 0
    
    new_count = 0
    now = datetime.utcnow().isoformat()
    
    for post in posts:
        post_id = post.get("id")
        if not post_id:
            continue
        
        # Calculate score from upvotes/downvotes
        upvotes = post.get("upvotes", 0) or 0
        downvotes = post.get("downvotes", 0) or 0
        score = upvotes - downvotes
        
        # Check if post exists
        async with db.execute("SELECT id FROM posts WHERE id = ?", (post_id,)) as cursor:
            exists = await cursor.fetchone()
        
        if exists:
            # Update existing post (score might have changed)
            await db.execute("""
                UPDATE posts SET
                    score = ?,
                    comment_count = ?,
                    is_pinned = ?
                WHERE id = ?
            """, (
                score,
                post.get("comment_count", 0) or 0,
                post.get("is_pinned", False),
                post_id,
            ))
        else:
            # Get author info - API uses "author" not "agent"
            author = post.get("author") or post.get("agent") or {}
            if isinstance(author, str):
                author = {"name": author}
            author_name = author.get("name", "") if author else ""
            
            # Handle submolt being a dict or string
            submolt = post.get("submolt", "")
            if isinstance(submolt, dict):
                submolt = submolt.get("name", "")
            
            # Ensure agent exists BEFORE inserting post (for foreign key constraint)
            if author_name:
                await ensure_agent(author_name, author if isinstance(author, dict) else None)
            
            await db.execute("""
                INSERT INTO posts (id, agent_id, agent_name, submolt, title, content, url, score, comment_count, created_at, fetched_at, is_pinned)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                post_id,
                author.get("id") if isinstance(author, dict) else None,
                author_name,
                submolt,
                post.get("title", "") or "",
                post.get("content", "") or "",
                post.get("url"),
                score,
                post.get("comment_count", 0) or 0,
                post.get("created_at"),
                now,
                post.get("is_pinned", False),
            ))
            new_count += 1
    
    await db.commit()
    return new_count


async def ensure_agent(name: str, agent_data: dict = None) -> None:
    """Ensure an agent exists in the database."""
    db = await get_db()
    
    async with db.execute("SELECT name FROM agents WHERE name = ?", (name,)) as cursor:
        exists = await cursor.fetchone()
    
    if exists:
        # Update last seen
        now = datetime.utcnow().isoformat()
        await db.execute("UPDATE agents SET last_seen_at = ? WHERE name = ?", (now, name))
    else:
        # Insert new agent
        now = datetime.utcnow().isoformat()
        await db.execute("""
            INSERT INTO agents (id, name, description, karma, follower_count, following_count, is_claimed, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            agent_data.get("id", name) if agent_data else name,
            name,
            agent_data.get("description", "") if agent_data else "",
            agent_data.get("karma", 0) if agent_data else 0,
            agent_data.get("follower_count", 0) if agent_data else 0,
            agent_data.get("following_count", 0) if agent_data else 0,
            agent_data.get("is_claimed", False) if agent_data else False,
            now,
            now,
        ))
    
    await db.commit()


async def process_agent_profile(profile_data: dict) -> None:
    """Process and store agent profile data."""
    db = await get_db()
    
    agent = profile_data.get("agent", {})
    if not agent:
        return
    
    name = agent.get("name")
    if not name:
        return
    
    now = datetime.utcnow().isoformat()
    owner = agent.get("owner", {})
    
    async with db.execute("SELECT name FROM agents WHERE name = ?", (name,)) as cursor:
        exists = await cursor.fetchone()
    
    if exists:
        await db.execute("""
            UPDATE agents SET
                description = ?,
                karma = ?,
                follower_count = ?,
                following_count = ?,
                is_claimed = ?,
                owner_x_handle = ?,
                last_seen_at = ?,
                created_at = ?,
                avatar_url = ?
            WHERE name = ?
        """, (
            agent.get("description", ""),
            agent.get("karma", 0),
            agent.get("follower_count", 0),
            agent.get("following_count", 0),
            agent.get("is_claimed", False),
            owner.get("x_handle") if owner else None,
            now,
            agent.get("created_at"),
            agent.get("avatar_url"),
            name,
        ))
    else:
        await db.execute("""
            INSERT INTO agents (id, name, description, karma, follower_count, following_count, is_claimed, owner_x_handle, first_seen_at, last_seen_at, created_at, avatar_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            agent.get("id", name),
            name,
            agent.get("description", ""),
            agent.get("karma", 0),
            agent.get("follower_count", 0),
            agent.get("following_count", 0),
            agent.get("is_claimed", False),
            owner.get("x_handle") if owner else None,
            now,
            now,
            agent.get("created_at"),
            agent.get("avatar_url"),
        ))
    
    await db.commit()


async def process_agents(agents_list: list[str]) -> int:
    """
    Process a list of agent names and fetch their profiles.
    
    Returns number of agents updated.
    """
    from observatory.poller.client import get_client
    
    client = await get_client()
    updated = 0
    
    for name in agents_list:
        try:
            profile = await client.get_agent_profile(name)
            await process_agent_profile(profile)
            updated += 1
        except Exception as e:
            print(f"Error fetching profile for {name}: {e}")
    
    return updated


async def process_submolts(submolts_data: dict) -> int:
    """
    Process submolts from API response and store in database.
    
    Returns number of submolts processed.
    """
    db = await get_db()
    submolts = submolts_data.get("submolts", [])
    if not submolts:
        return 0
    
    now = datetime.utcnow().isoformat()
    count = 0
    
    for submolt in submolts:
        name = submolt.get("name")
        if not name:
            continue
        
        async with db.execute("SELECT name FROM submolts WHERE name = ?", (name,)) as cursor:
            exists = await cursor.fetchone()
        
        if exists:
            await db.execute("""
                UPDATE submolts SET
                    display_name = ?,
                    description = ?,
                    subscriber_count = ?,
                    post_count = ?,
                    avatar_url = ?,
                    banner_url = ?
                WHERE name = ?
            """, (
                submolt.get("display_name", name),
                submolt.get("description", ""),
                submolt.get("subscriber_count", 0),
                submolt.get("post_count", 0),
                submolt.get("avatar_url"),
                submolt.get("banner_url"),
                name,
            ))
        else:
            await db.execute("""
                INSERT INTO submolts (name, display_name, description, subscriber_count, post_count, created_at, first_seen_at, avatar_url, banner_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                submolt.get("display_name", name),
                submolt.get("description", ""),
                submolt.get("subscriber_count", 0),
                submolt.get("post_count", 0),
                submolt.get("created_at"),
                now,
                submolt.get("avatar_url"),
                submolt.get("banner_url"),
            ))
        count += 1
    
    await db.commit()
    return count


async def process_comments(post_id: str, comments_data: dict) -> int:
    """
    Process comments from API response and store in database.
    
    Returns number of new comments inserted.
    """
    db = await get_db()
    comments = comments_data.get("comments", [])
    if not comments:
        return 0
    
    new_count = 0
    now = datetime.utcnow().isoformat()
    
    async def process_comment(comment: dict, parent_id: str = None) -> None:
        nonlocal new_count
        
        comment_id = comment.get("id")
        if not comment_id:
            return
        
        async with db.execute("SELECT id FROM comments WHERE id = ?", (comment_id,)) as cursor:
            exists = await cursor.fetchone()
        
        agent = comment.get("agent", {})
        agent_name = agent.get("name", "") if agent else ""
        
        if not exists:
            await db.execute("""
                INSERT INTO comments (id, post_id, agent_id, agent_name, parent_id, content, score, created_at, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                comment_id,
                post_id,
                agent.get("id") if agent else None,
                agent_name,
                parent_id,
                comment.get("content", ""),
                comment.get("score", 0),
                comment.get("created_at"),
                now,
            ))
            new_count += 1
            
            if agent_name:
                await ensure_agent(agent_name, agent)
        
        # Process replies
        for reply in comment.get("replies", []):
            await process_comment(reply, comment_id)
    
    for comment in comments:
        await process_comment(comment)
    
    await db.commit()
    return new_count
