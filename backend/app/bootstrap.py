import asyncio

from sqlalchemy import select

from app.config import get_settings
from app.db import Session, engine
from app.models import User
from app.security import hash_password


async def seed() -> None:
    settings = get_settings()
    async with Session.begin() as db:
        exists = await db.scalar(select(User).where(User.username == settings.admin_username))
        if exists is None:
            db.add(
                User(
                    username=settings.admin_username,
                    password_hash=await asyncio.to_thread(hash_password, settings.admin_password),
                )
            )


async def main() -> None:
    try:
        await seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
