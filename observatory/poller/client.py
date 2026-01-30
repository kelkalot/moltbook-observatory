"""Moltbook API client - read-only access to public data."""

import httpx
from typing import Optional
from observatory.config import config


class MoltbookClient:
    """Async client for the Moltbook API."""
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=config.MOLTBOOK_BASE_URL,
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {config.MOLTBOOK_API_KEY}",
                "User-Agent": "MoltbookObservatory/1.0",
            }
        )
    
    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
    
    async def get_posts(
        self,
        sort: str = "new",
        limit: int = 25,
        submolt: Optional[str] = None,
    ) -> dict:
        """
        Fetch posts from Moltbook.
        
        Args:
            sort: Sort order - 'hot', 'new', 'top', 'rising'
            limit: Number of posts to fetch
            submolt: Optional submolt to filter by
        
        Returns:
            API response with posts
        """
        params = {"sort": sort, "limit": limit}
        if submolt:
            params["submolt"] = submolt
        
        response = await self.client.get("/posts", params=params)
        response.raise_for_status()
        return response.json()
    
    async def get_post(self, post_id: str) -> dict:
        """Fetch a single post by ID."""
        response = await self.client.get(f"/posts/{post_id}")
        response.raise_for_status()
        return response.json()
    
    async def get_post_comments(
        self,
        post_id: str,
        sort: str = "top",
    ) -> dict:
        """
        Fetch comments on a post.
        
        Args:
            post_id: The post ID
            sort: Sort order - 'top', 'new', 'controversial'
        """
        response = await self.client.get(
            f"/posts/{post_id}/comments",
            params={"sort": sort}
        )
        response.raise_for_status()
        return response.json()
    
    async def get_submolts(self) -> dict:
        """List all submolts."""
        response = await self.client.get("/submolts")
        response.raise_for_status()
        return response.json()
    
    async def get_submolt(self, name: str) -> dict:
        """Get info about a specific submolt."""
        response = await self.client.get(f"/submolts/{name}")
        response.raise_for_status()
        return response.json()
    
    async def get_agent_profile(self, name: str) -> dict:
        """
        Get public profile of an agent.
        
        Returns agent info including karma, follower counts, recent posts.
        """
        response = await self.client.get("/agents/profile", params={"name": name})
        response.raise_for_status()
        return response.json()
    
    async def search(self, query: str, limit: int = 25) -> dict:
        """
        Search posts, agents, and submolts.
        
        Returns matching posts, agents, and submolts.
        """
        response = await self.client.get(
            "/search",
            params={"q": query, "limit": limit}
        )
        response.raise_for_status()
        return response.json()
    
    async def get_my_profile(self) -> dict:
        """Get the observatory agent's own profile (for testing connection)."""
        response = await self.client.get("/agents/me")
        response.raise_for_status()
        return response.json()


# Global client instance
_client: MoltbookClient | None = None


async def get_client() -> MoltbookClient:
    """Get the global Moltbook client instance."""
    global _client
    if _client is None:
        _client = MoltbookClient()
    return _client


async def close_client() -> None:
    """Close the global client."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
