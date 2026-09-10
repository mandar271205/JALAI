"""Safe Supabase PostgreSQL connection & diagnostic verification script.

Tests connection, SELECT 1, and inspects existing database schema.
Never logs passwords or full credentials.
"""
import asyncio
import os
import sys
import time
import urllib.parse
from pathlib import Path

# Try asyncpg
try:
    import asyncpg
except ImportError:
    asyncpg = None

# Try sqlalchemy
try:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
except ImportError:
    create_async_engine = None


def get_connection_urls():
    # Read from environment or load from .env
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        # Check parent or current directory .env
        for env_path in [Path(".env"), Path("../.env"), Path("../../.env"), Path("../../../sih backend/.env")]:
            if env_path.is_file():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("DATABASE_URL=") and not line.startswith("DATABASE_URL=postgresql+asyncpg://jalrakshak:"):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if "CHANGE_ME" not in val and "@" in val:
                            db_url = val
                            break
            if db_url:
                break
                
    if not db_url:
        print("[ERROR] DATABASE_URL not set in environment or .env file.")
        print("Set DATABASE_URL=postgresql+asyncpg://postgres.<project_ref>:<password>@<pooler_host>:6543/postgres")
        sys.exit(1)

    # Raw asyncpg url (without +asyncpg driver prefix)
    raw_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    return db_url, raw_url


async def test_asyncpg_connection(raw_url: str):
    print("=== Testing Direct / Pooler Connection with asyncpg ===")
    masked_url = raw_url.split("@")[-1] if "@" in raw_url else "unknown_host"
    print(f"Connecting to host endpoint: {masked_url}")
    
    t0 = time.perf_counter()
    try:
        conn = await asyncpg.connect(
            raw_url,
            statement_cache_size=0,  # PgBouncer transaction mode compatibility
            timeout=15.0
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        print(f"asyncpg Connect: SUCCESS (latency: {latency_ms:.1f}ms)")
        
        # Test SELECT 1
        val = await conn.fetchval("SELECT 1")
        print(f"SELECT 1: SUCCESS (result={val})")
        
        # Test version
        ver = await conn.fetchval("SELECT version()")
        print(f"Database version: {ver}")
        
        # Inspect schemas and tables
        tables = await conn.fetch("""
            SELECT table_schema, table_name 
            FROM information_schema.tables 
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema, table_name;
        """)
        print(f"User tables count: {len(tables)}")
        for r in tables:
            print(f"  - {r['table_schema']}.{r['table_name']}")
            
        await conn.close()
        return True, latency_ms, ver, [f"{r['table_schema']}.{r['table_name']}" for r in tables]
    except Exception as e:
        print(f"asyncpg Connect: FAILED ({type(e).__name__}: {e})")
        return False, 0.0, str(e), []


async def test_sqlalchemy_engine(async_url: str):
    print("\n=== Testing SQLAlchemy AsyncEngine with Session Pooler ===")
    t0 = time.perf_counter()
    try:
        engine = create_async_engine(
            async_url,
            echo=False,
            future=True,
            connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
            pool_pre_ping=True
        )
        async with engine.connect() as conn:
            latency_ms = (time.perf_counter() - t0) * 1000
            val = await conn.scalar(text("SELECT 1"))
            print(f"SQLAlchemy Connect: SUCCESS (latency: {latency_ms:.1f}ms, SELECT 1={val})")
        await engine.dispose()
        return True
    except Exception as e:
        print(f"SQLAlchemy Connect: FAILED ({type(e).__name__}: {e})")
        return False


async def main():
    async_url, raw_url = get_connection_urls()
    ok1, latency, ver, tables = await test_asyncpg_connection(raw_url)
    ok2 = await test_sqlalchemy_engine(async_url)
    
    print("\n=== DIAGNOSTIC SUMMARY ===")
    print(f"DATABASE_CONNECTION_SUCCESS={ok1 and ok2}")
    print(f"DATABASE_SELECT_1_PASS={ok1 and ok2}")
    print(f"DATABASE_LATENCY_MS={latency:.1f}")
    print(f"DATABASE_TABLES_FOUND={len(tables)}")


if __name__ == "__main__":
    asyncio.run(main())
