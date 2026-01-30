"""Trend detection using word frequency analysis."""

import re
from collections import Counter
from datetime import datetime, timedelta
from observatory.database.connection import get_db, execute_query

# Common stop words to ignore
STOP_WORDS = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'i', 'you', 'we', 'they',
    'it', 'this', 'that', 'to', 'of', 'and', 'or', 'for', 'in', 'on', 'at',
    'be', 'have', 'has', 'had', 'do', 'does', 'did', 'but', 'not', 'what',
    'all', 'would', 'there', 'their', 'from', 'with', 'as', 'my', 'just',
    'been', 'being', 'can', 'could', 'will', 'would', 'should', 'may', 'might',
    'must', 'shall', 'if', 'then', 'else', 'when', 'where', 'why', 'how',
    'which', 'who', 'whom', 'whose', 'than', 'too', 'very', 'much', 'many',
    'some', 'any', 'no', 'nor', 'only', 'own', 'same', 'so', 'such',
    'also', 'about', 'into', 'through', 'during', 'before', 'after',
    'above', 'below', 'between', 'under', 'again', 'further', 'once',
    'here', 'there', 'each', 'few', 'more', 'most', 'other', 'some',
    'these', 'those', 'your', 'its', 'his', 'her', 'our', 'out', 'up',
    'down', 'off', 'over', 'again', 'then', 'once', 'here', 'there',
    'even', 'now', 'just', 'well', 'also', 'back', 'way', 'new', 'one',
    'two', 'first', 'like', 'get', 'got', 'make', 'made', 'know', 'think',
    'see', 'come', 'want', 'look', 'use', 'find', 'give', 'tell', 'try',
    'really', 'still', 'thing', 'things', 'something', 'anything', 'nothing'
}


def extract_words(text: str) -> list[str]:
    """Extract meaningful words from text."""
    if not text:
        return []
    # Find words with 3+ characters
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    return [w for w in words if w not in STOP_WORDS]


async def update_word_frequency() -> None:
    """Update word frequency counts for recent posts."""
    db = await get_db()
    
    # Get posts from the last hour
    one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    
    posts = await execute_query("""
        SELECT title, content FROM posts
        WHERE fetched_at >= ?
    """, (one_hour_ago,))
    
    if not posts:
        return
    
    # Count words
    word_counts = Counter()
    for post in posts:
        text = f"{post.get('title', '')} {post.get('content', '')}"
        word_counts.update(extract_words(text))
    
    # Store in database
    current_hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0).isoformat()
    
    for word, count in word_counts.most_common(100):
        await db.execute("""
            INSERT INTO word_frequency (word, hour, count)
            VALUES (?, ?, ?)
            ON CONFLICT (word, hour) DO UPDATE SET count = count + excluded.count
        """, (word, current_hour, count))
    
    await db.commit()


async def get_trending_words(hours: int = 24, limit: int = 10) -> list[dict]:
    """
    Get trending words comparing current period to previous period.
    
    Returns list of {word, count, previous_count, change_percent}
    """
    now = datetime.utcnow()
    current_start = (now - timedelta(hours=hours)).isoformat()
    previous_start = (now - timedelta(hours=hours * 2)).isoformat()
    previous_end = current_start
    
    # Get current period counts
    current = await execute_query("""
        SELECT word, SUM(count) as total
        FROM word_frequency
        WHERE hour >= ?
        GROUP BY word
        ORDER BY total DESC
        LIMIT 50
    """, (current_start,))
    
    # Get previous period counts
    previous = await execute_query("""
        SELECT word, SUM(count) as total
        FROM word_frequency
        WHERE hour >= ? AND hour < ?
        GROUP BY word
    """, (previous_start, previous_end))
    
    previous_counts = {p['word']: p['total'] for p in previous}
    
    trends = []
    for word_data in current:
        word = word_data['word']
        current_count = word_data['total']
        prev_count = previous_counts.get(word, 0)
        
        if prev_count == 0:
            change = float('inf') if current_count > 2 else 0
        else:
            change = ((current_count - prev_count) / prev_count) * 100
        
        if current_count >= 3:
            trends.append({
                'word': word,
                'count': current_count,
                'previous_count': prev_count,
                'change_percent': change if change != float('inf') else 999,
            })
    
    # Sort by change percentage
    trends.sort(key=lambda x: x['change_percent'], reverse=True)
    return trends[:limit]


async def get_top_words(hours: int = 24, limit: int = 20) -> list[dict]:
    """Get most frequent words in the given time period."""
    start = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    
    return await execute_query("""
        SELECT word, SUM(count) as total
        FROM word_frequency
        WHERE hour >= ?
        GROUP BY word
        ORDER BY total DESC
        LIMIT ?
    """, (start, limit))


async def get_word_history(word: str, days: int = 7) -> list[dict]:
    """Get hourly frequency history for a specific word."""
    start = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    return await execute_query("""
        SELECT hour, count
        FROM word_frequency
        WHERE word = ? AND hour >= ?
        ORDER BY hour ASC
    """, (word, start))
