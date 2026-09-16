from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with Session() as session:
        yield session


async def commit(session: AsyncSession) -> None:
    if session.info.get("defer_commit"):
        await session.flush()
    else:
        await session.commit()
