import base64
import hashlib
import hmac
import json

import httpx
import pytest

from app import outbound
from app.outbound import DeliveryError, build_payload, complete, deliver
from app.templates import render, validate_template


def mock_client(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        outbound, "client", lambda: original(transport=httpx.MockTransport(handler))
    )


async def test_llm_host_validation_reports_worker_restart(monkeypatch):
    def reject_host(_):
        raise ValueError("invalid host")

    monkeypatch.setattr(outbound, "validate_llm_host", reject_host)
    with pytest.raises(DeliveryError, match="修改 .env 后需重启 API 和 worker"):
        await complete(
            {"llm_host": "https://example.invalid/v1", "llm_api_key": "key", "llm_model": "model"},
            "test",
            "trace-host-validation",
        )


@pytest.mark.parametrize(
    ("kind", "url", "response"),
    [
        ("feishu", "https://open.feishu.cn/open-apis/bot/v2/hook/token", {"code": 0}),
        ("wecom", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=token", {"errcode": 0}),
        ("dingtalk", "https://oapi.dingtalk.com/robot/send?access_token=token", {"errcode": 0}),
    ],
)
async def test_platform_payload_signing_and_success(kind, url, response, monkeypatch):
    monkeypatch.setattr(outbound.time, "time", lambda: 1700000000)

    def handler(request):
        data = json.loads(request.content)
        assert request.headers["X-Trace-Id"] == "trace-123"
        if kind == "feishu":
            assert data["card"]["elements"][0]["content"] == "你好"
            expected = hmac.new(b"1700000000\nsecret", b"", hashlib.sha256).digest()
            assert data["sign"] == base64.b64encode(expected).decode()
        elif kind == "dingtalk":
            assert request.url.params["access_token"] == "token"
            expected = hmac.new(b"secret", b"1700000000000\nsecret", hashlib.sha256).digest()
            assert request.url.params["sign"] == base64.b64encode(expected).decode()
            assert data["actionCard"]["text"] == "你好"
        else:
            assert data["msgtype"] == "template_card"
            assert data["template_card"]["sub_title_text"] == "你好"
        return httpx.Response(200, json=response)

    mock_client(monkeypatch, handler)
    assert await deliver(
        {"target_type": kind, "target_url": url, "target_secret": "secret"},
        build_payload(kind, "你好"),
        "trace-123",
    ) == {"http_status": 200, "code": 0}


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"code": 1}),
        httpx.Response(200, json={"unknown": 0}),
        httpx.Response(200, text="html"),
        httpx.Response(302),
        httpx.Response(500),
    ],
)
async def test_platform_errors_are_not_success(response, monkeypatch):
    mock_client(monkeypatch, lambda _: response)
    with pytest.raises(DeliveryError):
        await deliver(
            {
                "target_type": "feishu",
                "target_url": "https://open.feishu.cn/open-apis/bot/v2/hook/token",
            },
            build_payload("feishu", "hello"),
            "trace",
        )


async def test_llm_request_and_response(monkeypatch):
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer sk-test"
        assert body["messages"] == [
            {"role": "system", "content": "summarize"},
            {"role": "user", "content": "payload"},
        ]
        return httpx.Response(200, json={"choices": [{"message": {"content": "summary"}}]})

    mock_client(monkeypatch, handler)
    assert (
        await complete(
            {
                "llm_host": "https://api.openai.com/v1",
                "llm_api_key": "sk-test",
                "llm_model": "model",
                "llm_prompt": "summarize",
            },
            "payload",
            "trace",
        )
        == "summary"
    )


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
    ],
)
async def test_llm_bad_response(response, monkeypatch):
    mock_client(monkeypatch, lambda _: response)
    with pytest.raises(DeliveryError):
        await complete(
            {
                "llm_host": "https://api.openai.com/v1",
                "llm_api_key": "sk-test",
                "llm_model": "model",
                "llm_prompt": "summarize",
            },
            "payload",
            "trace",
        )


def test_template_does_not_reinterpret_payload():
    assert (
        render("{{payload}}", {"payload": "{{llm_output}}", "llm_output": "secret"})
        == "{{llm_output}}"
    )
    with pytest.raises(ValueError):
        validate_template("{{payload.__class__}}")
    with pytest.raises(DeliveryError):
        build_payload("wecom", "中" * 1025)


@pytest.mark.parametrize("event,color", [("alert", "red"), ("recovery", "green"), ("push", "blue")])
def test_feishu_card_header_markdown_and_mentions(event, color):
    payload = build_payload(
        "feishu", "**磁盘使用率**：93.6%", {"all": True}, title="根分区告警", event=event
    )
    assert payload["msg_type"] == "interactive"
    card = payload["card"]
    assert card["config"]["wide_screen_mode"] is True
    assert card["header"] == {
        "title": {"tag": "plain_text", "content": "根分区告警"},
        "template": color,
    }
    assert card["elements"] == [
        {"tag": "markdown", "content": '**磁盘使用率**：93.6%\n\n<at id="all"></at>'}
    ]


@pytest.mark.parametrize("kind", ["wecom", "dingtalk"])
async def test_card_followed_by_native_mention(kind, monkeypatch):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"errcode": 0})

    mock_client(monkeypatch, handler)
    config = {
        "name": "磁盘告警",
        "target_type": kind,
        "target_mentions": {"all": True},
        "target_url": (
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
            if kind == "wecom"
            else "https://oapi.dingtalk.com/robot/send?access_token=test"
        ),
    }
    payload = build_payload(
        kind, "磁盘占用 93.6%", title="磁盘告警", detail_url="https://station.example/#/logs"
    )
    response = await deliver(config, payload, "trace-card")
    assert len(sent) == 2
    assert sent[0] == payload
    assert sent[1]["msgtype"] == "text"
    if kind == "wecom":
        assert sent[0]["template_card"]["card_action"]["url"] == "https://station.example/#/logs"
        assert sent[1]["text"]["mentioned_list"] == ["@all"]
    else:
        assert sent[0]["actionCard"]["singleURL"] == "https://station.example/#/logs"
        assert sent[1]["at"]["isAtAll"] is True
    assert response["mention_response"]["code"] == 0


async def test_mention_failure_reports_card_already_sent(monkeypatch):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"errcode": 0 if len(sent) == 1 else 400})

    mock_client(monkeypatch, handler)
    with pytest.raises(DeliveryError, match="卡片已发送，但 @ 提醒失败"):
        await deliver(
            {
                "target_type": "wecom",
                "target_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
                "target_mentions": {"user_ids": ["alice"]},
            },
            build_payload("wecom", "告警"),
            "trace-partial",
        )
    assert len(sent) == 2


@pytest.mark.parametrize("kind", ["feishu", "wecom", "dingtalk"])
def test_card_rejects_empty_content(kind):
    with pytest.raises(DeliveryError, match="不能为空"):
        build_payload(kind, "   ")
