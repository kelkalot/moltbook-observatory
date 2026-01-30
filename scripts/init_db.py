#!/usr/bin/env python3
"""Initialize the database."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from observatory.database import init_db, close_db


async def main():
    print("Initializing database...")
    await init_db()
    await close_db()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
