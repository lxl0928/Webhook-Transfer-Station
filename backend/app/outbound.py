import base64
import hashlib
import hmac
import html
import re
import time

import httpx

from app.config import get_settings
from app.schemas import validate_llm_host, validate_target_url


class DeliveryError(Exception):
    """Safe-to-log failure without credentials or untrusted upstream error bodies."""


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=get_settings().outbound_timeout_seconds, follow_redirects=False, trust_env=False
    )


async def complete(config: dict, message: str, trace_id: str) -> str:
    if not config.get("llm_api_key") or not config.get("llm_model"):
        raise DeliveryError("LLM 未配置 API Key 或模型")
    host = validate_llm_host(config["llm_host"])
    async with client() as http:
        response = await http.post(
            f"{host}/chat/completions",
            headers={"Authorization": f"Bearer {config['llm_api_key']}", "X-Trace-Id": trace_id},
            json={
                "model": config["llm_model"],
                "messages": [
                    {"role": "system", "content": config["llm_prompt"]},
                    {"role": "user", "content": message},
                ],
                "max_tokens": 1200,
            },
        )
    if response.status_code != 200:
        raise DeliveryError(f"LLM HTTP {response.status_code}")
    try:
        result = response.json()["choices"][0]["message"]["content"]
        if not isinstance(result, str) or not result.strip():
            raise ValueError
        if len(result) > 20000:
            raise DeliveryError("LLM 输出超过 20000 字符")
        return result
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise DeliveryError("LLM 返回格式无效或无文本内容") from exc


def build_payload(kind: str, content: str, mentions: dict | None = None) -> dict:
    mentions = mentions or {}
    everyone = mentions.get("all", False)
    users = mentions.get("user_ids", [])
    mobiles = mentions.get("mobiles", [])
    if kind == "feishu":
        # Source/LLM text cannot inject additional mentions; only rule config can @ users.
        content = re.sub(r"<\s*/?\s*at\b", lambda match: "&lt;" + match[0][1:], content, flags=re.I)
        ids = ["all"] if everyone else users
        tags = [
            f'<at user_id="{html.escape(value, quote=True)}">'
            f"{'所有人' if value == 'all' else '成员'}</at>"
            for value in ids
        ]
        if tags:
            content += "\n" + " ".join(tags)
        payload = {"msg_type": "text", "content": {"text": content}}
    else:
        if kind == "dingtalk" and not everyone and (users or mobiles):
            # DingTalk requires corresponding @ markers in the text as well as the at object.
            content += "\n" + " ".join(f"@{value}" for value in [*users, *mobiles])
        payload = {"msgtype": "text", "text": {"content": content}}
        if kind == "wecom":
            if everyone or users:
                payload["text"]["mentioned_list"] = ["@all"] if everyone else users
            if mobiles and not everyone:
                payload["text"]["mentioned_mobile_list"] = mobiles
        elif everyone or users or mobiles:
            payload["at"] = {
                "atUserIds": [] if everyone else users,
                "atMobiles": [] if everyone else mobiles,
                "isAtAll": everyone,
            }
    limit = {"feishu": 20000, "wecom": 2048, "dingtalk": 20000}[kind]
    if len(content.encode()) > limit:
        raise DeliveryError(f"目标消息（含 @ 人员）超过 {limit} UTF-8 字节，请缩短提示词或模板")
    return payload


async def deliver(config: dict, payload: dict, trace_id: str) -> dict:
    url = validate_target_url(config["target_type"], config["target_url"])
    params = {}
    body = dict(payload)
    secret = config.get("target_secret")
    if secret and config["target_type"] == "feishu":
        timestamp = str(int(time.time()))
        sign = hmac.new(f"{timestamp}\n{secret}".encode(), b"", hashlib.sha256).digest()
        body.update(timestamp=timestamp, sign=base64.b64encode(sign).decode())
    elif secret and config["target_type"] == "dingtalk":
        timestamp = str(int(time.time() * 1000))
        sign = hmac.new(secret.encode(), f"{timestamp}\n{secret}".encode(), hashlib.sha256).digest()
        # Copy existing access_token query and append signature without losing credentials.
        params = dict(httpx.URL(url).params)
        params.update(timestamp=timestamp, sign=base64.b64encode(sign).decode())
    async with client() as http:
        kwargs = {"params": params} if params else {}
        response = await http.post(url, json=body, headers={"X-Trace-Id": trace_id}, **kwargs)
    if response.status_code != 200:
        raise DeliveryError(f"目标平台 HTTP {response.status_code}")
    try:
        result = response.json()
        code = (
            result.get("code", result.get("StatusCode"))
            if config["target_type"] == "feishu"
            else result.get("errcode")
        )
        if type(code) is not int or code != 0:
            safe_code = str(code)[:16] if isinstance(code, int) else "missing"
            raise DeliveryError(f"目标平台拒绝消息，code={safe_code}")
        return {"http_status": response.status_code, "code": code}
    except (ValueError, AttributeError) as exc:
        raise DeliveryError("目标平台返回非预期 JSON") from exc
