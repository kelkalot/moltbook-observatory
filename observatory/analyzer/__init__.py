"""Analyzer module - trend detection, sentiment, and statistics."""

from observatory.analyzer.trends import get_trending_words, update_word_frequency
from observatory.analyzer.sentiment import analyze_sentiment, average_sentiment
from observatory.analyzer.stats import get_stats, create_snapshot

__all__ = [
    "get_trending_words",
    "update_word_frequency",
    "analyze_sentiment",
    "average_sentiment",
    "get_stats",
    "create_snapshot",
]
