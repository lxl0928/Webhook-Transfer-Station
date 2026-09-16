import pytest


@pytest.mark.parametrize("source", ["gitee", "nightingale", "generic"])
async def test_auth_disabled_accepts_without_secret(client, auth, hook_body, source):
    body = hook_body | {"source_type": source, "source_auth_enabled": False}
    body.pop("source_secret")
    response = await client.post("/api/webhooks", headers=auth, json=body)
    assert response.status_code == 201, response.text
    hook = response.json()
    assert hook["source_auth_enabled"] is False
    assert hook["source_secret_set"] is False
    payload = {"repository": {"html_url": body["source_url"]}, "event": "alert"}
    received = await client.post(
        "/webhooks",
        params={"wid": hook["wid"]},
        json=payload,
        headers={"X-Gitee-Event": "Push Hook"},
    )
    assert received.status_code == (202 if source == "gitee" else 200), received.text
    assert (await client.get("/api/webhook-logs", headers=auth)).json()["total"] == 1


@pytest.mark.parametrize("mode", ["header", "bearer", "query"])
async def test_auth_modes_toggle_and_preserve_secret(client, auth, hook_body, mode):
    body = hook_body | {"source_type": "generic", "source_auth": mode}
    hook = (await client.post("/api/webhooks", headers=auth, json=body)).json()
    wid = hook["wid"]
    assert hook["source_auth_enabled"] is True
    assert (
        await client.post("/webhooks", params={"wid": wid}, json={"event": "hello"})
    ).status_code == 401
    patch = {k: v for k, v in body.items() if k != "source_secret"} | {"source_auth_enabled": False}
    changed = await client.put(f"/api/webhooks/{wid}", headers=auth, json=patch)
    assert changed.status_code == 200
    assert changed.json()["source_secret_set"] is True
    assert (
        await client.post("/webhooks", params={"wid": wid}, json={"event": "hello"})
    ).status_code == 200
    patch["source_auth_enabled"] = True
    assert (await client.put(f"/api/webhooks/{wid}", headers=auth, json=patch)).status_code == 200
    assert (
        await client.post("/webhooks", params={"wid": wid}, json={"event": "hello"})
    ).status_code == 401
    headers, params = {}, {"wid": wid}
    if mode == "header":
        headers["X-Webhook-Token"] = body["source_secret"]
    if mode == "bearer":
        headers["Authorization"] = "Bearer " + body["source_secret"]
    if mode == "query":
        params["token"] = body["source_secret"]
    assert (
        await client.post("/webhooks", params=params, headers=headers, json={"event": "hello"})
    ).status_code == 200


async def test_enable_requires_secret_and_disabled_rule_still_rejected(client, auth, hook_body):
    body = {k: v for k, v in hook_body.items() if k != "source_secret"} | {"source_type": "generic"}
    assert (await client.post("/api/webhooks", headers=auth, json=body)).status_code == 422
    body["source_auth_enabled"] = False
    hook = (await client.post("/api/webhooks", headers=auth, json=body)).json()
    url = f"/api/webhooks/{hook['wid']}"
    assert (
        await client.put(url, headers=auth, json=body | {"source_auth_enabled": True})
    ).status_code == 422
    assert (await client.get(url, headers=auth)).json()["source_auth_enabled"] is False
    assert (
        await client.put(
            url, headers=auth, json=body | {"source_auth_enabled": True, "source_secret": "short"}
        )
    ).status_code == 422
    assert (
        await client.put(
            url,
            headers=auth,
            json=body | {"source_auth_enabled": True, "source_secret": "valid-secret"},
        )
    ).status_code == 200
    assert (await client.put(url, headers=auth, json=body | {"enabled": False})).status_code == 200
    assert (await client.post("/webhooks", params={"wid": hook["wid"]}, json={})).status_code == 409
    assert (await client.post("/webhooks", params={"wid": "f" * 32}, json={})).status_code == 404
    assert (await client.get(url)).status_code == 401


async def test_auth_off_preserves_gitee_repository_and_payload_validation(client, auth, hook_body):
    hook = (
        await client.post(
            "/api/webhooks", headers=auth, json=hook_body | {"source_auth_enabled": False}
        )
    ).json()
    url = f"/webhooks?wid={hook['wid']}"
    assert (
        await client.post(url, json={"repository": {"html_url": "https://gitee.com/other/repo"}})
    ).status_code == 403
    assert (await client.post(url, json=[])).status_code == 400
