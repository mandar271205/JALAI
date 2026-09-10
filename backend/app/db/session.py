from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

connect_args = {}
if "asyncpg" in settings.DATABASE_URL:
    if (
        "6543" in settings.DATABASE_URL
        or "pooler" in settings.DATABASE_URL
        or getattr(settings, "DB_STATEMENT_CACHE_SIZE", 0) == 0
    ):
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_cache_size"] = 0

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    pool_pre_ping=True,
    connect_args=connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False
)


async def get_db_session():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


get_db = get_db_session
