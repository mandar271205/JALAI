import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.db.session import engine


async def test_postgis():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        res = await conn.execute(
            text("SELECT extname, extversion FROM pg_extension WHERE extname = 'postgis';")
        )
        print("POSTGIS EXTENSION:", res.fetchall())


if __name__ == "__main__":
    asyncio.run(test_postgis())
