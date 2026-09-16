"""Requires TEST_POSTGRES_URL pointing to a disposable PostgreSQL database."""

import asyncio
import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import worker
from app.models import Base, User, WebhookLog


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not configured")
async def test_postgres_skip_locked_and_parallel_claim(monkeypatch):
    url = os.environ["TEST_POSTGRES_URL"]
    schema = "test_" + uuid.uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as db:
        await db.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "Session", sessions)
    try:
        async with engine.begin() as db:
            await db.run_sync(Base.metadata.create_all)
        async with sessions.begin() as db:
            db.add(User(id="a" * 32, username="admin", password_hash="test"))
            await db.flush()
            for index in range(3):
                db.add(
                    WebhookLog(
                        id=str(index) * 32,
                        wid="b" * 32,
                        user_id="a" * 32,
                        webhook_name="test",
                        trace_id=f"trace-{index}",
                        event="push",
                        input_payload={},
                        config_snapshot="test",
                        status="pending",
                    )
                )
        # A transaction holding the first row must not block a different worker.
        async with sessions.begin() as lock_session:
            await lock_session.scalar(
                select(WebhookLog).where(WebhookLog.id == "0" * 32).with_for_update()
            )
            claimed = await asyncio.wait_for(worker.claim_job(), timeout=5)
            assert claimed != "0" * 32
        claims = await asyncio.gather(worker.claim_job(), worker.claim_job())
        assert len(set([claimed, *claims])) == 3
        assert None not in claims
        assert await worker.claim_job() is None
    finally:
        await engine.dispose()
        async with admin.begin() as db:
            await db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()
