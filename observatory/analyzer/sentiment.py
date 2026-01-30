"""Simple sentiment analysis using TextBlob."""

from textblob import TextBlob
from statistics import mean


def analyze_sentiment(text: str) -> float:
    """
    Analyze sentiment of text.
    
    Returns polarity from -1.0 (negative) to +1.0 (positive).
    """
    if not text:
        return 0.0
    
    blob = TextBlob(text)
    return blob.sentiment.polarity


def get_sentiment_label(polarity: float) -> str:
    """Get a human-readable label for sentiment polarity."""
    if polarity >= 0.3:
        return "positive"
    elif polarity <= -0.3:
        return "negative"
    else:
        return "neutral"


def get_sentiment_emoji(polarity: float) -> str:
    """Get an emoji representing the sentiment."""
    if polarity >= 0.5:
        return "😊"
    elif polarity >= 0.2:
        return "🙂"
    elif polarity <= -0.5:
        return "😞"
    elif polarity <= -0.2:
        return "😐"
    else:
        return "😶"


def average_sentiment(texts: list[str]) -> float:
    """Calculate average sentiment across multiple texts."""
    if not texts:
        return 0.0
    
    scores = [analyze_sentiment(t) for t in texts if t]
    return mean(scores) if scores else 0.0


async def get_recent_sentiment(hours: int = 24) -> dict:
    """Get average sentiment for recent posts."""
    from observatory.database.connection import execute_query
    from datetime import datetime, timedelta
    
    start = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    
    posts = await execute_query("""
        SELECT title, content FROM posts
        WHERE created_at >= ?
    """, (start,))
    
    if not posts:
        return {"polarity": 0.0, "label": "neutral", "emoji": "😶", "sample_size": 0}
    
    texts = [f"{p.get('title', '')} {p.get('content', '')}" for p in posts]
    avg = average_sentiment(texts)
    
    return {
        "polarity": round(avg, 2),
        "label": get_sentiment_label(avg),
        "emoji": get_sentiment_emoji(avg),
        "sample_size": len(texts),
    }
