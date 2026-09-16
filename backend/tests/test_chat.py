import json
from datetime import timedelta

from sqlalchemy import select

from app import chat
from app.models import ChatAction, ChatMessage, Conversation, User, now
from app.security import create_token, hash_password


def call(name, args):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ],
    }


async def stage(client, auth, monkeypatch, name="update_user_info", args=None, skill_id=None):
    async def model(*_):
        return call(name, args if args is not None else {"real_name": "聊天改名"})

    monkeypatch.setattr(chat, "model_completion", model)
    cid = (await client.post("/api/chat/conversations", headers=auth)).json()["id"]
    response = await client.post(
        f"/api/chat/conversations/{cid}/messages",
        headers=auth,
        json={"content": "请执行操作", "skill_id": skill_id},
    )
    assert response.status_code == 200, response.text
    return cid, response.json()


async def decision(client, auth, cid, aid, decision="approve", secrets=None):
    return await client.post(
        f"/api/chat/conversations/{cid}/actions/{aid}/decision",
        headers=auth,
        json={"decision": decision, "secrets": secrets or {}},
    )


async def test_skills_crud_and_catalog(client, auth):
    items = (await client.get("/api/skills", headers=auth)).json()["items"]
    assert len(items) == 11
    assert len((await client.get("/api/skills/tools", headers=auth)).json()["items"]) == 20
    body = {
        "name": "my-logs",
        "description": "日志查询",
        "instructions": "只查询失败的日志",
        "tools": ["query_webhook_logs"],
    }
    created = await client.post("/api/skills", headers=auth, json=body)
    assert created.status_code == 201
    sid = created.json()["id"]
    assert (await client.post("/api/skills", headers=auth, json=body)).status_code == 409
    assert (
        await client.put(f"/api/skills/{sid}", headers=auth, json=body | {"tools": ["shell"]})
    ).status_code == 422
    export = await client.get(f"/api/skills/{sid}/export", headers=auth)
    assert "my-logs" in export.text and "query_webhook_logs" in export.text
    assert (await client.delete(f"/api/skills/{items[0]['id']}", headers=auth)).status_code == 409
    assert (
        await client.post(f"/api/skills/{items[0]['id']}/reset", headers=auth)
    ).status_code == 200
    assert (await client.delete(f"/api/skills/{sid}", headers=auth)).status_code == 204


async def test_write_requires_confirmation_and_is_idempotent(client, auth, monkeypatch, database):
    cid, detail = await stage(client, auth, monkeypatch)
    assert len(detail["actions"]) == 1
    assert (await client.get("/api/users/me", headers=auth)).json()["real_name"] != "聊天改名"
    aid = detail["actions"][0]["id"]
    blocked = await client.post(
        f"/api/chat/conversations/{cid}/messages", headers=auth, json={"content": "继续"}
    )
    assert blocked.status_code == 409
    response = await decision(client, auth, cid, aid)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "succeeded"
    assert (await client.get("/api/users/me", headers=auth)).json()["real_name"] == "聊天改名"
    assert (await decision(client, auth, cid, aid)).json() == response.json()
    async with database() as db:
        rows = list(await db.scalars(select(ChatMessage)))
        assert all("聊天改名" not in row.body for row in rows)
        action = await db.get(ChatAction, aid)
        assert "聊天改名" not in action.arguments


async def test_reject_and_stale_state(client, auth, monkeypatch):
    cid, detail = await stage(client, auth, monkeypatch)
    aid = detail["actions"][0]["id"]
    await client.patch("/api/users/me", headers=auth, json={"phone": "12345"})
    assert (await decision(client, auth, cid, aid)).status_code == 409
    assert (await decision(client, auth, cid, aid, "reject")).json()["status"] == "rejected"
    assert (await client.get("/api/users/me", headers=auth)).json()["real_name"] != "聊天改名"


async def test_read_tool_and_history(client, auth, monkeypatch):
    seen = []

    async def model(user, messages, names, trace):
        seen.append(messages.copy())
        if len(seen) == 1:
            return call("get_user_info", {})
        return {"role": "assistant", "content": "已查询到你的用户信息"}

    monkeypatch.setattr(chat, "model_completion", model)
    cid = (await client.post("/api/chat/conversations", headers=auth)).json()["id"]
    res = await client.post(
        f"/api/chat/conversations/{cid}/messages", headers=auth, json={"content": "查看我的资料"}
    )
    assert res.status_code == 200
    assert not res.json()["actions"]
    assert seen[1][-1]["role"] == "tool"
    assert "password_hash" not in json.dumps(seen)
    assert res.json()["messages"][-1]["content"] == "已查询到你的用户信息"
    assert res.headers["x-trace-id"]


async def test_tool_permission_and_disabled_skill(client, auth, monkeypatch):
    skills = (await client.get("/api/skills", headers=auth)).json()["items"]
    readonly = next(s for s in skills if s["name"] == "query-webhook-log")
    _, detail = await stage(client, auth, monkeypatch, skill_id=readonly["id"])
    assert not detail["actions"]
    assert any(
        "未授权" in m["content"] or "\\u672a" in m["content"]
        for m in detail["messages"]
        if m["role"] == "tool"
    )
    cid, detail = await stage(client, auth, monkeypatch)
    writer = next(s for s in skills if s["name"] == "update-user-info")
    await client.patch(f"/api/skills/{writer['id']}", headers=auth, json={"enabled": False})
    assert (await decision(client, auth, cid, detail["actions"][0]["id"])).status_code == 409


async def test_cross_user_isolation(client, auth, database, monkeypatch):
    cid, detail = await stage(client, auth, monkeypatch)
    async with database.begin() as db:
        other = User(username="other", password_hash=hash_password("OtherPassword123"))
        db.add(other)
        await db.flush()
        token = create_token(other)
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get(f"/api/chat/conversations/{cid}", headers=headers)).status_code == 404
    assert (await decision(client, headers, cid, detail["actions"][0]["id"])).status_code == 404
    sid = (await client.get("/api/skills", headers=auth)).json()["items"][0]["id"]
    assert (await client.get(f"/api/skills/{sid}", headers=headers)).status_code == 404
    assert (await client.get("/api/skills")).status_code == 401


async def test_create_rule_secure_form(client, auth, hook_body, monkeypatch):
    hidden = {k: hook_body[k] for k in ["source_secret", "target_url"]}
    args = {k: v for k, v in hook_body.items() if k not in hidden}
    cid, detail = await stage(client, auth, monkeypatch, "create_webhook_rule", args)
    aid = detail["actions"][0]["id"]
    assert (await decision(client, auth, cid, aid)).status_code == 422
    result = await decision(client, auth, cid, aid, secrets=hidden)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "succeeded"
    history = (await client.get(f"/api/chat/conversations/{cid}", headers=auth)).text
    assert hidden["source_secret"] not in history and hidden["target_url"] not in history
    assert (await client.get("/api/webhooks", headers=auth)).json()["total"] == 1


async def test_expiry_busy_and_delete(client, auth, monkeypatch, database):
    cid, detail = await stage(client, auth, monkeypatch)
    aid = detail["actions"][0]["id"]
    async with database.begin() as db:
        (await db.get(ChatAction, aid)).expires_at = now() - timedelta(seconds=1)
        (await db.get(Conversation, cid)).busy_until = now() + timedelta(seconds=60)
    assert (await decision(client, auth, cid, aid)).status_code == 409
    assert (await client.delete(f"/api/chat/conversations/{cid}", headers=auth)).status_code == 409
    async with database.begin() as db:
        (await db.get(Conversation, cid)).busy_until = None
    assert (await decision(client, auth, cid, aid)).status_code == 409
    assert (await client.delete(f"/api/chat/conversations/{cid}", headers=auth)).status_code == 204


async def test_llm_failure_releases_conversation(client, auth):
    cid = (await client.post("/api/chat/conversations", headers=auth)).json()["id"]
    response = await client.post(
        f"/api/chat/conversations/{cid}/messages", headers=auth, json={"content": "你好"}
    )
    assert response.status_code == 200
    assert "配置 LLM" in response.json()["messages"][-1]["content"]
    assert (await client.delete(f"/api/chat/conversations/{cid}", headers=auth)).status_code == 204


async def test_real_llm_wire_protocol(client, auth, monkeypatch, database):
    import httpx

    from app.security import encrypt

    async with database.begin() as db:
        user = await db.get(User, "a" * 32)
        user.llm_host = "https://api.openai.com/v1"
        user.llm_model = "test-function-model"
        user.llm_api_key = encrypt("test-key-not-real")
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key-not-real"
        assert request.headers["x-trace-id"]
        assert "test-key-not-real" not in json.dumps(body)
        if len(requests) == 1:
            assert any(t["function"]["name"] == "list_webhook_rules" for t in body["tools"])
            answer = call("list_webhook_rules", {})
        else:
            assert body["messages"][-1]["role"] == "tool"
            answer = {"role": "assistant", "content": "当前没有中转规则。"}
        return httpx.Response(200, json={"choices": [{"message": answer}]})

    monkeypatch.setattr(
        chat, "client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    cid = (await client.post("/api/chat/conversations", headers=auth)).json()["id"]
    result = await client.post(
        f"/api/chat/conversations/{cid}/messages", headers=auth, json={"content": "查询规则"}
    )
    assert result.json()["messages"][-1]["content"] == "当前没有中转规则。"
    assert len(requests) == 2


async def test_invalid_secure_form_rolls_back_and_can_retry(client, auth, hook_body, monkeypatch):
    hidden = {k: hook_body[k] for k in ["source_secret", "target_url"]}
    args = {k: v for k, v in hook_body.items() if k not in hidden}
    cid, detail = await stage(client, auth, monkeypatch, "create_webhook_rule", args)
    aid = detail["actions"][0]["id"]
    invalid = await decision(
        client, auth, cid, aid, secrets=hidden | {"target_url": "https://evil.example/hook"}
    )
    assert invalid.status_code == 422
    assert (await client.get("/api/webhooks", headers=auth)).json()["total"] == 0
    assert (await decision(client, auth, cid, aid, secrets=hidden)).json()["status"] == "succeeded"


async def test_concurrent_confirmation_postgres(client, auth, monkeypatch, database):
    import asyncio
    import os

    import pytest

    if not os.getenv("TEST_POSTGRES_URL"):
        pytest.skip("PostgreSQL row locks required")
    cid, detail = await stage(client, auth, monkeypatch)
    aid = detail["actions"][0]["id"]
    results = await asyncio.gather(
        decision(client, auth, cid, aid), decision(client, auth, cid, aid)
    )
    assert all(r.status_code == 200 for r in results)
    async with database() as db:
        messages = list(
            await db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == cid))
        )
        assert (
            sum(
                "操作 update_user_info：succeeded" in chat.unpack(m.body).get("content", "")
                for m in messages
            )
            == 1
        )


async def test_rule_update_delete_and_skill_create_through_tools(client, auth, hook, monkeypatch):
    cid, detail = await stage(
        client,
        auth,
        monkeypatch,
        "update_webhook_rule",
        {"wid": hook["wid"], "changes": {"name": "经助手更新"}},
    )
    assert len(detail["actions"]) == 1, detail
    result = await decision(client, auth, cid, detail["actions"][0]["id"])
    assert result.status_code == 200, result.text
    assert (await client.get(f"/api/webhooks/{hook['wid']}", headers=auth)).json()[
        "name"
    ] == "经助手更新"
    cid, detail = await stage(
        client, auth, monkeypatch, "delete_webhook_rule", {"wid": hook["wid"]}
    )
    assert (await decision(client, auth, cid, detail["actions"][0]["id"])).status_code == 200
    assert (await client.get(f"/api/webhooks/{hook['wid']}", headers=auth)).status_code == 404
    config = {
        "name": "assistant-skill",
        "description": "测试",
        "instructions": "只查用户",
        "tools": ["get_user_info"],
    }
    cid, detail = await stage(client, auth, monkeypatch, "create_skill", config)
    result = await decision(client, auth, cid, detail["actions"][0]["id"])
    assert result.status_code == 200, result.text
    sid = result.json()["result"]["id"]
    cid, detail = await stage(
        client,
        auth,
        monkeypatch,
        "update_skill",
        {"skill_id": sid, "configuration": config | {"enabled": False}},
    )
    assert (await decision(client, auth, cid, detail["actions"][0]["id"])).status_code == 200
    assert not (await client.get(f"/api/skills/{sid}", headers=auth)).json()["enabled"]
