import asyncio
import sys
from pathlib import Path

# Ensure app is in path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.db.session import engine


async def inspect_db():
    async with engine.connect() as conn:
        # Check Extensions
        res_ext = await conn.execute(
            text("SELECT extname, extversion FROM pg_extension WHERE extname IN ('postgis', 'uuid-ossp');")
        )
        extensions = res_ext.fetchall()
        print("EXTENSIONS:", extensions)

        # Check all tables by schema
        res_tables = await conn.execute(
            text("""
                SELECT table_schema, table_name 
                FROM information_schema.tables 
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name;
            """)
        )
        tables = res_tables.fetchall()
        print(f"TOTAL NON-SYSTEM TABLES: {len(tables)}")

        public_tables = [t[1] for t in tables if t[0] == "public"]
        system_tables = [f"{t[0]}.{t[1]}" for t in tables if t[0] != "public"]

        print(f"PUBLIC TABLES COUNT: {len(public_tables)}")
        print(f"PUBLIC TABLES: {public_tables}")
        print(f"SUPABASE SYSTEM TABLES COUNT: {len(system_tables)}")
        print(f"SUPABASE SYSTEM TABLES: {system_tables}")


if __name__ == "__main__":
    asyncio.run(inspect_db())
