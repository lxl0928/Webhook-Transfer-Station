import json
from datetime import timedelta
from unittest.mock import AsyncMock

import jwt
import pytest
from sqlalchemy import func, select

from app import worker
from app.api import detect_event
from app.config import get_settings
from app.models import User, Webhook, WebhookLog, now
from app.outbound import DeliveryError
from app.security import create_token, decrypt, encrypt, hash_password, verify_password


async def test_auth_profile_logout_and_trace(client, auth):
    response = await client.get("/api/users/me", headers=auth | {"X-Trace-Id": "test.trace-123"})
    assert response.headers["X-Trace-Id"] == "test.trace-123"
    assert response.json()["username"] == "admin"
    assert "password_hash" not in response.json()
    assert "llm_api_key" not in response.json()
    assert (await client.get("/api/users/me")).status_code == 401
    assert (await client.post("/api/auth/logout", headers=auth)).status_code == 204
    assert (await client.get("/api/users/me", headers=auth)).status_code == 401


async def test_invalid_login_and_expired_token(client):
    response = await client.post("/api/auth/login", json={"username": "admin", "password": "bad"})
    assert response.status_code == 401
    token = jwt.encode(
        {
            "sub": "a" * 32,
            "ver": 0,
            "iat": now() - timedelta(hours=2),
            "exp": now() - timedelta(hours=1),
            "iss": "webhook-station",
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    assert (
        await client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    ).status_code == 401


async def test_password_change_revokes_old_token(client, auth):
    body = {"current_password": "wrong", "new_password": "NewPassword!123"}
    assert (await client.patch("/api/users/me", headers=auth, json=body)).status_code == 400
    body["current_password"] = "Admin#123."
    assert (await client.patch("/api/users/me", headers=auth, json=body)).status_code == 200
    assert (await client.get("/api/users/me", headers=auth)).status_code == 401
    assert (
        await client.post(
            "/api/auth/login", json={"username": "admin", "password": "NewPassword!123"}
        )
    ).status_code == 200


async def test_secrets_encrypted_and_not_echoed(client, auth, hook, database):
    response = await client.patch(
        "/api/users/me",
        headers=auth,
        json={"llm_api_key": "sk-secret-test", "llm_model": "test-model"},
    )
    assert response.json()["llm_api_key_set"] is True
    assert "sk-secret-test" not in response.text
    async with database() as db:
        user = await db.get(User, "a" * 32)
        stored = await db.get(Webhook, hook["wid"])
        assert user.llm_api_key != "sk-secret-test"
        assert decrypt(user.llm_api_key) == "sk-secret-test"
        assert "test-token" not in stored.target_url
        assert decrypt(stored.source_secret) == "gitee-secret-123"
    assert "target_url" not in hook
    assert "source_secret" not in hook


async def test_rule_crud_and_secret_retention(client, auth, hook, hook_body, database):
    edited = dict(hook_body, name="Updated", enabled=False)
    del edited["source_secret"]
    del edited["target_url"]
    assert (
        await client.put(f"/api/webhooks/{hook['wid']}", json=edited, headers=auth)
    ).status_code == 200
    response = await client.get("/api/webhooks?q=Updated", headers=auth)
    assert response.json()["total"] == 1
    async with database() as db:
        record = await db.get(Webhook, hook["wid"])
        assert decrypt(record.source_secret) == "gitee-secret-123"
    assert (await client.delete(f"/api/webhooks/{hook['wid']}", headers=auth)).status_code == 204
    assert (await client.get(f"/api/webhooks/{hook['wid']}", headers=auth)).status_code == 404


async def test_rule_validation_no_secret_echo(client, auth, hook_body):
    for values in (
        {"target_url": "http://127.0.0.1/secrets"},
        {"target_type": "slack"},
        {"source_template": "{{arbitrary_expression}}"},
        {"events": []},
    ):
        response = await client.post("/api/webhooks", headers=auth, json=hook_body | values)
        assert response.status_code == 422
        assert "gitee-secret-123" not in response.text
        assert "test-token" not in response.text
    assert (
        await client.patch(
            "/api/users/me", headers=auth, json={"llm_host": "http://169.254.169.254/metadata"}
        )
    ).status_code == 422


async def test_callback_dedup_and_redaction(client, auth, hook, payload, database):
    headers = {
        "X-Gitee-Event": "Push Hook",
        "X-Gitee-Delivery": "delivery-123",
        "X-Trace-Id": "callback-trace",
    }
    response = await client.post(hook["url"], headers=headers, json=payload)
    assert response.status_code == 202
    again = await client.post(hook["url"], headers=headers, json=payload)
    assert again.status_code == 200 and again.json()["duplicate"]
    assert again.json()["id"] == response.json()["id"]
    detail = (await client.get(f"/api/webhook-logs/{response.json()['id']}", headers=auth)).json()
    assert detail["trace_id"] == "callback-trace"
    assert detail["input_payload"]["password"] == "[REDACTED]"
    assert "config_snapshot" not in detail
    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(WebhookLog)) == 1
        log = await db.get(WebhookLog, detail["id"])
        assert "test-token" not in log.config_snapshot
        assert json.loads(decrypt(log.config_snapshot))["target_url"].endswith("test-token")


async def test_callback_rejects_bad_auth_repo_payload_and_size(client, hook, payload, monkeypatch):
    assert (await client.post(hook["url"], json=payload | {"password": "wrong"})).status_code == 401
    assert (
        await client.post(
            hook["url"], json=payload | {"repository": {"html_url": "https://gitee.com/other/repo"}}
        )
    ).status_code == 403
    assert (await client.post(hook["url"], content="no json")).status_code == 400
    assert (await client.post(hook["url"], json=[])).status_code == 400
    monkeypatch.setattr(get_settings(), "max_payload_bytes", 10)
    assert (await client.post(hook["url"], json=payload)).status_code == 413


async def test_disabled_and_ignored_events(client, auth, hook, hook_body, payload):
    ignored = await client.post(hook["url"], json=payload, headers={"X-Gitee-Event": "Issue Hook"})
    assert ignored.json()["status"] == "ignored"
    await client.put(
        f"/api/webhooks/{hook['wid']}", headers=auth, json=hook_body | {"enabled": False}
    )
    assert (await client.post(hook["url"], json=payload)).status_code == 409


async def test_tenant_isolation(client, auth, hook, payload, database):
    async with database.begin() as db:
        other = User(id="b" * 32, username="other", password_hash=hash_password("other-password"))
        db.add(other)
    headers = {"Authorization": f"Bearer {create_token(other)}"}
    log = (
        await client.post(hook["url"], json=payload, headers={"X-Gitee-Event": "Push Hook"})
    ).json()
    assert (await client.get(f"/api/webhooks/{hook['wid']}", headers=headers)).status_code == 404
    assert (await client.delete(f"/api/webhooks/{hook['wid']}", headers=headers)).status_code == 404
    assert (await client.get(f"/api/webhook-logs/{log['id']}", headers=headers)).status_code == 404
    assert (await client.get("/api/webhooks", headers=headers)).json()["total"] == 0
    assert (await client.get("/api/webhook-logs", headers=headers)).json()["total"] == 0


async def test_worker_success_preserves_snapshot_after_delete(
    client, auth, hook, payload, monkeypatch
):
    mocked = AsyncMock(return_value={"http_status": 200, "code": 0})
    monkeypatch.setattr(worker, "deliver", mocked)
    response = await client.post(hook["url"], json=payload, headers={"X-Gitee-Event": "Push Hook"})
    await client.delete(f"/api/webhooks/{hook['wid']}", headers=auth)
    job_id = await worker.claim_job()
    assert job_id == response.json()["id"]
    assert await worker.claim_job() is None
    await worker.process_job(job_id)
    detail = (await client.get(f"/api/webhook-logs/{job_id}", headers=auth)).json()
    assert detail["status"] == "succeeded" and detail["attempts"] == 1
    assert detail["output_payload"]["content"]["text"].startswith("push:")
    assert detail["output_at"] and detail["cost_ms"] is not None
    assert mocked.call_args.args[0]["target_url"].endswith("test-token")
    assert (
        await client.post(f"/api/webhook-logs/{job_id}/retries", headers=auth)
    ).status_code == 409


async def test_worker_failure_retry_and_llm(client, auth, hook, hook_body, payload, monkeypatch):
    await client.put(
        f"/api/webhooks/{hook['wid']}", headers=auth, json=hook_body | {"llm_enabled": True}
    )
    complete = AsyncMock(return_value="summary")
    deliver = AsyncMock(side_effect=DeliveryError("目标平台拒绝消息，code=100"))
    monkeypatch.setattr(worker, "complete", complete)
    monkeypatch.setattr(worker, "deliver", deliver)
    await client.post(hook["url"], json=payload, headers={"X-Gitee-Event": "Merge Request Hook"})
    job_id = await worker.claim_job()
    await worker.process_job(job_id)
    detail = (await client.get(f"/api/webhook-logs/{job_id}", headers=auth)).json()
    assert detail["status"] == "failed" and detail["output_payload"]["content"]["text"] == "summary"
    assert detail["output_at"] is None and detail["finished_at"]
    assert "password" not in complete.call_args.args[1]
    assert (
        await client.post(f"/api/webhook-logs/{job_id}/retries", headers=auth)
    ).status_code == 202
    assert (
        await client.post(f"/api/webhook-logs/{job_id}/retries", headers=auth)
    ).status_code == 409
    deliver.side_effect = None
    deliver.return_value = {"code": 0}
    assert await worker.claim_job() == job_id
    await worker.process_job(job_id)
    detail = (await client.get(f"/api/webhook-logs/{job_id}", headers=auth)).json()
    assert detail["status"] == "succeeded" and detail["attempts"] == 2


async def test_recover_stale_jobs(client, auth, hook, payload, database):
    await client.post(hook["url"], json=payload, headers={"X-Gitee-Event": "Push Hook"})
    job_id = await worker.claim_job()
    async with database.begin() as db:
        job = await db.get(WebhookLog, job_id)
        job.started_at = now() - timedelta(minutes=10)
    await worker.recover_stale_jobs()
    detail = (await client.get(f"/api/webhook-logs/{job_id}", headers=auth)).json()
    assert detail["status"] == "failed" and "结果未知" in detail["error"]
    assert await worker.claim_job() is None


async def test_log_filter_pagination(client, auth, hook, payload):
    for event in ["Push Hook", "Issue Hook"]:
        await client.post(hook["url"], json=payload, headers={"X-Gitee-Event": event})
    response = await client.get("/api/webhook-logs?page_size=1", headers=auth)
    assert response.json()["total"] == 2 and len(response.json()["items"]) == 1
    response = await client.get("/api/webhook-logs?status=ignored", headers=auth)
    assert response.json()["total"] == 1
    assert (await client.get("/api/webhook-logs?page_size=101", headers=auth)).status_code == 422


async def test_health_endpoints(client, auth, monkeypatch):
    assert (await client.get("/health/live")).json()["status"] == "ok"
    assert (await client.get("/health/ready")).json()["postgresql"] == "ok"
    assert (await client.post("/api/health/llm")).status_code == 401
    from app import api

    monkeypatch.setattr(api, "complete", AsyncMock(return_value="OK"))
    assert (await client.post("/api/health/llm", headers=auth)).json()["llm"] == "ok"
    monkeypatch.setattr(api, "complete", AsyncMock(side_effect=RuntimeError("secret")))
    response = await client.post("/api/health/llm", headers=auth)
    assert response.status_code == 503 and "secret" not in response.text


@pytest.mark.parametrize(
    ("header", "payload", "expected"),
    [
        ("Push Hook", {}, "push"),
        ("Push Hook", {"ref": "refs/tags/v1"}, "tag"),
        ("Tag Push Hook", {}, "tag"),
        ("Merge Request Hook", {}, "pull_request"),
        ("Note Hook", {}, "comment"),
        ("Issue Hook", {}, "unsupported"),
    ],
)
def test_event_normalization(header, payload, expected):
    assert detect_event(header, payload) == expected


def test_password_and_encryption():
    digest = hash_password("Admin#123.")
    assert digest != hash_password("Admin#123.")
    assert verify_password("Admin#123.", digest)
    assert not verify_password("wrong", digest)
    assert not verify_password("wrong", "invalid")
    assert decrypt(encrypt("private")) == "private"


async def test_trace_validation_and_request_cost(client, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="station.http"):
        response = await client.get("/health/live", headers={"X-Trace-Id": "a" * 100})
    assert len(response.headers["X-Trace-Id"]) == 32
    assert "cost_ms=" in caplog.text
    assert response.headers["X-Trace-Id"] in caplog.text


async def test_login_rate_limit(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "login_max_attempts", 1)
    body = {"username": "admin", "password": "wrong"}
    assert (await client.post("/api/auth/login", json=body)).status_code == 401
    response = await client.post("/api/auth/login", json=body)
    assert response.status_code == 429 and response.headers["Retry-After"] == "60"


async def test_log_mixed_timezone_filter(client, auth):
    response = await client.get(
        "/api/webhook-logs",
        headers=auth,
        params={"start": "2026-01-01T00:00:00", "end": "2026-02-01T00:00:00Z"},
    )
    assert response.status_code == 200
    response = await client.get(
        "/api/webhook-logs",
        headers=auth,
        params={"start": "2026-03-01T00:00:00", "end": "2026-02-01T00:00:00Z"},
    )
    assert response.status_code == 422


async def test_health_database_unavailable(client):
    from app.db import get_db
    from app.main import app

    async def unavailable():
        yield AsyncMock(execute=AsyncMock(side_effect=ConnectionError("private-db-password")))

    original = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = unavailable
    try:
        response = await client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["postgresql"] == "unavailable"
        assert "private-db-password" not in response.text
        assert "X-Trace-Id" in response.headers
    finally:
        app.dependency_overrides[get_db] = original
