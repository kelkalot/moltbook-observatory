"""Database schema and migrations."""

from observatory.database.connection import get_db

SCHEMA = """
-- All agents we've ever seen
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    karma INTEGER DEFAULT 0,
    follower_count INTEGER DEFAULT 0,
    following_count INTEGER DEFAULT 0,
    is_claimed BOOLEAN DEFAULT FALSE,
    owner_x_handle TEXT,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP,
    avatar_url TEXT
);

-- All posts
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    agent_id TEXT REFERENCES agents(id),
    agent_name TEXT,
    submolt TEXT,
    title TEXT,
    content TEXT,
    url TEXT,
    score INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    created_at TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_pinned BOOLEAN DEFAULT FALSE
);

-- All comments
CREATE TABLE IF NOT EXISTS comments (
    id TEXT PRIMARY KEY,
    post_id TEXT REFERENCES posts(id),
    agent_id TEXT REFERENCES agents(id),
    agent_name TEXT,
    parent_id TEXT,
    content TEXT,
    score INTEGER DEFAULT 0,
    created_at TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- All submolts (communities)
CREATE TABLE IF NOT EXISTS submolts (
    name TEXT PRIMARY KEY,
    display_name TEXT,
    description TEXT,
    subscriber_count INTEGER DEFAULT 0,
    post_count INTEGER DEFAULT 0,
    created_at TIMESTAMP,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    avatar_url TEXT,
    banner_url TEXT
);

-- Follows relationships (for social graph)
CREATE TABLE IF NOT EXISTS follows (
    follower_id TEXT REFERENCES agents(id),
    following_id TEXT REFERENCES agents(id),
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (follower_id, following_id)
);

-- Hourly snapshots for time-series analysis
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_agents INTEGER,
    total_posts INTEGER,
    total_comments INTEGER,
    active_agents_24h INTEGER,
    avg_sentiment REAL,
    top_words TEXT
);

-- For trend detection
CREATE TABLE IF NOT EXISTS word_frequency (
    word TEXT,
    hour TIMESTAMP,
    count INTEGER,
    PRIMARY KEY (word, hour)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_submolt ON posts(submolt);
CREATE INDEX IF NOT EXISTS idx_posts_agent_id ON posts(agent_id);
CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);
CREATE INDEX IF NOT EXISTS idx_agents_karma ON agents(karma DESC);
CREATE INDEX IF NOT EXISTS idx_word_frequency_hour ON word_frequency(hour DESC);
"""


async def init_db() -> None:
    """Initialize the database schema."""
    db = await get_db()
    await db.executescript(SCHEMA)
    await db.commit()
    print("Database initialized successfully")
