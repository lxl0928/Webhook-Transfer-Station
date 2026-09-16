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
            assert data["content"]["text"] == "你好"
            expected = hmac.new(b"1700000000\nsecret", b"", hashlib.sha256).digest()
            assert data["sign"] == base64.b64encode(expected).decode()
        elif kind == "dingtalk":
            assert request.url.params["access_token"] == "token"
            expected = hmac.new(b"secret", b"1700000000000\nsecret", hashlib.sha256).digest()
            assert request.url.params["sign"] == base64.b64encode(expected).decode()
            assert data["text"]["content"] == "你好"
        else:
            assert data == {"msgtype": "text", "text": {"content": "你好"}}
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
        build_payload("wecom", "中" * 683)
