import json
from unittest.mock import AsyncMock

import pytest

from app import worker
from app.models import WebhookLog
from app.outbound import DeliveryError, build_payload
from app.security import decrypt
from app.templates import context_for, render, validate_template


@pytest.mark.parametrize(
    ("kind", "mentions", "expected"),
    [
        (
            "feishu",
            {"user_ids": ["ou_alice", "ou_bob"]},
            {
                "msg_type": "text",
                "content": {
                    "text": 'hello\n<at user_id="ou_alice">成员</at> <at user_id="ou_bob">成员</at>'
                },
            },
        ),
        (
            "feishu",
            {"all": True},
            {"msg_type": "text", "content": {"text": 'hello\n<at user_id="all">所有人</at>'}},
        ),
        (
            "wecom",
            {"user_ids": ["alice"], "mobiles": ["13800138000"]},
            {
                "msgtype": "text",
                "text": {
                    "content": "hello",
                    "mentioned_list": ["alice"],
                    "mentioned_mobile_list": ["13800138000"],
                },
            },
        ),
        (
            "wecom",
            {"all": True},
            {"msgtype": "text", "text": {"content": "hello", "mentioned_list": ["@all"]}},
        ),
        (
            "dingtalk",
            {"user_ids": ["alice"], "mobiles": ["13800138000"]},
            {
                "msgtype": "text",
                "text": {"content": "hello\n@alice @13800138000"},
                "at": {"atUserIds": ["alice"], "atMobiles": ["13800138000"], "isAtAll": False},
            },
        ),
        (
            "dingtalk",
            {"all": True},
            {
                "msgtype": "text",
                "text": {"content": "hello"},
                "at": {"atUserIds": [], "atMobiles": [], "isAtAll": True},
            },
        ),
    ],
)
def test_mentions_platform_format(kind, mentions, expected):
    assert build_payload(kind, "hello", mentions) == expected


def test_feishu_untrusted_at_and_size():
    payload = build_payload(
        "feishu", '<at user_id="all">everyone</at>', {"user_ids": ["ou_trusted"]}
    )
    assert '<at user_id="all">' not in payload["content"]["text"]
    assert '<at user_id="ou_trusted">' in payload["content"]["text"]
    with pytest.raises(DeliveryError):
        build_payload("feishu", "x" * 20000, {"user_ids": ["ou_a"]})


@pytest.mark.parametrize(
    "mentions",
    [
        {"all": True, "user_ids": ["ou_user"]},
        {"user_ids": ["all"]},
        {"user_ids": ['ou_foo"><at user_id="all']},
        {"user_ids": ["ordinary_user_id"]},
        {"mobiles": ["13800138000"]},
        {"extra": True},
    ],
)
async def test_invalid_feishu_mentions(client, auth, hook_body, mentions):
    response = await client.post(
        "/api/webhooks", headers=auth, json=hook_body | {"target_mentions": mentions}
    )
    assert response.status_code == 422


async def create_generic(client, auth, hook_body, **overrides):
    body = (
        hook_body
        | {"source_type": "generic", "source_url": "", "source_template": "{{payload}}"}
        | overrides
    )
    response = await client.post("/api/webhooks", headers=auth, json=body)
    assert response.status_code == 201, response.text
    assert response.json()["events"] == body.get("events", [])
    return response.json(), body


@pytest.mark.parametrize(
    ("mode", "header", "query"),
    [
        ("header", {"X-Custom-Token": "gitee-secret-123"}, {}),
        ("bearer", {"Authorization": "Bearer gitee-secret-123"}, {}),
        ("query", {}, {"token": "gitee-secret-123"}),
    ],
)
async def test_generic_authentication(client, auth, hook_body, mode, header, query):
    hook, _ = await create_generic(
        client, auth, hook_body, source_auth=mode, source_token_header="X-Custom-Token"
    )
    response = await client.post(
        "/webhooks",
        params={"wid": hook["wid"], **query},
        headers=header,
        json={"event_type": "service.error", "message": "disk full"},
    )
    assert response.status_code == 200 and response.json()["status"] == "pending"
    detail = (await client.get(f"/api/webhook-logs/{response.json()['id']}", headers=auth)).json()
    assert detail["event"] == "service.error" and detail["input_payload"]["message"] == "disk full"
    assert (await client.post(hook["url"], json={})).status_code == 401
    # Password fallback is only allowed for Gitee, never generic sources.
    assert (
        await client.post(hook["url"], json={"password": "gitee-secret-123"})
    ).status_code == 401


@pytest.mark.parametrize(
    ("content_type", "content", "expected"),
    [
        (
            "application/json",
            '[{"message":"one"},{"message":"two"}]',
            [{"message": "one"}, {"message": "two"}],
        ),
        ("text/plain; charset=utf-8", "服务不可用", "服务不可用"),
        (
            "application/x-www-form-urlencoded",
            "status=down&tag=a&tag=b&password=secret",
            {"status": "down", "tag": ["a", "b"], "password": "[REDACTED]"},
        ),
        ("application/json", '"string event"', "string event"),
        ("application/json", "false", False),
    ],
)
async def test_generic_payload_formats(client, auth, hook_body, content_type, content, expected):
    hook, _ = await create_generic(client, auth, hook_body)
    response = await client.post(
        hook["url"],
        headers={"X-Webhook-Token": "gitee-secret-123", "Content-Type": content_type},
        content=content.encode(),
    )
    assert response.status_code == 200, response.text
    detail = (await client.get(f"/api/webhook-logs/{response.json()['id']}", headers=auth)).json()
    assert detail["input_payload"] == expected


@pytest.mark.parametrize(
    ("payload", "event"),
    [
        ({"rule_name": "CPU high", "is_recovered": 0}, "alert"),
        ({"rule_name": "CPU high", "is_recovered": True}, "recovery"),
        ([{"rule_name": "CPU high"}], "alert_batch"),
        ({"events": [{"is_recovered": False}]}, "alert_batch"),
    ],
)
async def test_nightingale_events(client, auth, hook_body, payload, event):
    hook, _ = await create_generic(client, auth, hook_body, source_type="nightingale")
    response = await client.post(
        hook["url"], headers={"X-Webhook-Token": "gitee-secret-123"}, json=payload
    )
    assert response.status_code == 200 and response.json()["status"] == "pending"
    detail = (await client.get(f"/api/webhook-logs/{response.json()['id']}", headers=auth)).json()
    assert detail["event"] == event


@pytest.mark.parametrize("llm_enabled", [False, True])
async def test_generic_filter_dedup_and_worker_mentions_snapshot(
    client, auth, hook_body, database, monkeypatch, llm_enabled
):
    hook, body = await create_generic(
        client,
        auth,
        hook_body,
        events=["service.error"],
        llm_enabled=llm_enabled,
        target_mentions={"user_ids": ["ou_owner", "ou_owner"]},
        source_template="{{payload.error.message}} / {{source_type}}",
    )
    assert hook["target_mentions"]["user_ids"] == ["ou_owner"]
    headers = {
        "X-Webhook-Token": "gitee-secret-123",
        "X-Webhook-Event": "service.error",
        "X-Webhook-Delivery": "delivery-one",
    }
    response = await client.post(
        hook["url"], headers=headers, json={"error": {"message": "database down"}}
    )
    again = await client.post(
        hook["url"], headers=headers, json={"error": {"message": "database down"}}
    )
    assert again.json()["duplicate"] and again.json()["id"] == response.json()["id"]
    ignored = await client.post(
        hook["url"], headers={"X-Webhook-Token": "gitee-secret-123"}, json={"event_type": "other"}
    )
    assert ignored.json()["status"] == "ignored"
    # Changing recipients later must not modify an accepted notification.
    await client.put(
        f"/api/webhooks/{hook['wid']}", headers=auth, json=body | {"target_mentions": {}}
    )
    monkeypatch.setattr(worker, "complete", AsyncMock(return_value="处理后的摘要"))
    deliver = AsyncMock(return_value={"code": 0})
    monkeypatch.setattr(worker, "deliver", deliver)
    job_id = await worker.claim_job()
    await worker.process_job(job_id)
    detail = (await client.get(f"/api/webhook-logs/{job_id}", headers=auth)).json()
    assert detail["status"] == "succeeded"
    assert (
        detail["output_payload"]["content"]["text"]
        == ("处理后的摘要" if llm_enabled else "database down / generic")
        + '\n<at user_id="ou_owner">成员</at>'
    )
    async with database() as db:
        job = await db.get(WebhookLog, job_id)
        snapshot = json.loads(decrypt(job.config_snapshot))
        assert snapshot["target_mentions"]["user_ids"] == ["ou_owner"]


async def test_invalid_generic_body_and_unsupported_media(client, auth, hook_body):
    hook, _ = await create_generic(client, auth, hook_body)
    headers = {"X-Webhook-Token": "gitee-secret-123"}
    for body in ["null", "NaN", '{"value":Infinity}', "{"]:
        assert (
            await client.post(
                hook["url"], headers=headers | {"Content-Type": "application/json"}, content=body
            )
        ).status_code == 400
    assert (
        await client.post(
            hook["url"],
            headers=headers | {"Content-Type": "application/octet-stream"},
            content=b"binary",
        )
    ).status_code == 415


def test_nested_json_templates():
    config = {
        "name": "monitor",
        "source_url": "",
        "source_type": "nightingale",
        "source_info": {"team": "infra"},
    }
    context = context_for(config, {"events": [{"rule_name": "CPU high"}]}, "alert_batch")
    template = "{{source_info.team}}: {{payload.events.0.rule_name}} {{payload.missing}}"
    validate_template(template)
    assert render(template, context) == "infra: CPU high "
    for template in ["{{payload.__class__}}", "{{event.upper}}", "{{payload[0]}}"]:
        with pytest.raises(ValueError):
            validate_template(template)


async def test_secret_header_cannot_be_logged_as_trace(client, auth, hook_body):
    response = await client.post(
        "/api/webhooks",
        headers=auth,
        json=hook_body | {"source_type": "generic", "source_token_header": "X-Trace-Id"},
    )
    assert response.status_code == 422
