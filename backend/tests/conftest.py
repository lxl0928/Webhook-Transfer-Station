import os
import uuid

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET"] = "unit-test-only-secret-key-not-for-production-123"
os.environ["ENCRYPTION_KEY"] = "dGVzdC10ZXN0LXRlc3QtdGVzdC10ZXN0LXRlc3QtdGU="
os.environ["LOGIN_MAX_ATTEMPTS"] = "100"

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app import worker  # noqa: E402
from app.api import login_attempts  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, User  # noqa: E402
from app.security import hash_password  # noqa: E402

TEST_PASSWORD_HASH = hash_password("Admin#123.")


@pytest.fixture
async def database(tmp_path, monkeypatch):
    pg_url = os.getenv("TEST_POSTGRES_URL")
    schema = "test_" + uuid.uuid4().hex
    admin = None
    if pg_url:
        admin = create_async_engine(pg_url)
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            pg_url, connect_args={"server_settings": {"search_path": schema}}
        )
    else:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as db:
        db.add(User(id="a" * 32, username="admin", password_hash=TEST_PASSWORD_HASH))

    async def override():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(worker, "Session", sessions)
    login_attempts.clear()
    yield sessions
    app.dependency_overrides.clear()
    await engine.dispose()
    if admin:
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.fixture
async def client(database):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
async def auth(client):
    response = await client.post(
        "/api/auth/login", json={"username": "admin", "password": "Admin#123."}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def hook_body():
    return {
        "name": "测试仓库",
        "source_url": "https://gitee.com/team/repo",
        "source_secret": "gitee-secret-123",
        "target_type": "feishu",
        "target_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
        "llm_enabled": False,
        "source_template": "{{event}}: {{repository}}",
        "target_template": "{{llm_output}}",
    }


@pytest.fixture
async def hook(client, auth, hook_body):
    response = await client.post("/api/webhooks", json=hook_body, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def payload():
    return {
        "password": "gitee-secret-123",
        "repository": {"html_url": "https://gitee.com/team/repo"},
        "ref": "refs/heads/main",
        "commits": [{"message": "hello"}],
    }
