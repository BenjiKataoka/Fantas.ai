from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import DATABASE_URL

# SSL required for Neon
engine = create_async_engine(
    DATABASE_URL,
    connect_args={"ssl": "require"},
    pool_size=5,
    max_overflow=10,
    # Neon closes idle connections; ping on checkout and transparently reconnect
    # instead of handing a request a dead one (ConnectionDoesNotExistError).
    pool_pre_ping=True,
    echo=False,  # Set True temporarily to debug SQL queries
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass

async def get_db():
    """FastAPI dependency, yields a DB session and closes it after the request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
