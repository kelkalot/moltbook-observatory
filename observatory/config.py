"""Configuration loaded from environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class Config:
    """Application configuration."""
    
    # Moltbook API
    MOLTBOOK_API_KEY: str = os.getenv("MOLTBOOK_API_KEY", "")
    MOLTBOOK_BASE_URL: str = "https://www.moltbook.com/api/v1"
    
    # Database
    DATABASE_PATH: Path = Path(os.getenv("DATABASE_PATH", "./data/observatory.db"))
    
    # Polling intervals (in seconds)
    POLL_POSTS_INTERVAL: int = int(os.getenv("POLL_POSTS_INTERVAL", "120"))
    POLL_AGENTS_INTERVAL: int = int(os.getenv("POLL_AGENTS_INTERVAL", "900"))
    POLL_SUBMOLTS_INTERVAL: int = int(os.getenv("POLL_SUBMOLTS_INTERVAL", "3600"))
    
    # App settings
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    DISABLE_POLL: bool = os.getenv("DISABLE_POLL", "false").lower() == "true"
    
    # Footer
    FOOTER_COPYRIGHT_HTML: str = os.getenv("FOOTER_COPYRIGHT_HTML", '<span>&copy; 2026 <a href="https://simulamet.no" class="text-ocean-400 hover:text-ocean-300">SimulaMet</a></span>')
    
    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        if not cls.MOLTBOOK_API_KEY:
            raise ValueError("MOLTBOOK_API_KEY environment variable is required")
    
    @classmethod
    def ensure_data_dir(cls) -> None:
        """Ensure the data directory exists."""
        cls.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


config = Config()
