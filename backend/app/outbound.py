import base64
import hashlib
import hmac
import html
import json
import re
import time
from urllib.parse import urlsplit

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
    try:
        host = validate_llm_host(config["llm_host"])
    except ValueError as exc:
        raise DeliveryError(
            "LLM Host 校验失败：请检查 LLM_ALLOWED_HOSTS、ALLOW_HTTP_LLM 和 Host 格式；"
            "修改 .env 后需重启 API 和 worker"
        ) from exc
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


def build_text_payload(kind: str, content: str, mentions: dict | None = None) -> dict:
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


def build_payload(
    kind: str,
    content: str,
    mentions: dict | None = None,
    *,
    title: str = "中转站通知",
    event: str = "webhook",
    detail_url: str | None = None,
) -> dict:
    """Build platform-native cards; source templates remain plain template strings."""
    title = title.strip()[:36] or "中转站通知"
    content = content.strip()
    if not content:
        raise DeliveryError("目标卡片内容不能为空，请检查目标消息模板")
    if kind == "feishu":
        content = re.sub(r"<\s*/?\s*at\b", lambda m: "&lt;" + m[0][1:], content, flags=re.I)
        mentions = mentions or {}
        ids = ["all"] if mentions.get("all") else mentions.get("user_ids", [])
        if ids:
            content += "\n\n" + " ".join(
                f'<at id="{html.escape(value, quote=True)}"></at>' for value in ids
            )
        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": {"alert": "red", "recovery": "green"}.get(event, "blue"),
                },
                "elements": [{"tag": "markdown", "content": content}],
            },
        }
    else:
        url = detail_url or get_settings().public_base_url.rstrip("/") + "/#/logs"
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            raise DeliveryError("卡片详情地址无效，请检查 PUBLIC_BASE_URL")
        if kind == "wecom":
            if len(content) > 1024:
                raise DeliveryError("企业微信模板卡片正文超过 1024 字符，请缩短提示词或模板")
            payload = {
                "msgtype": "template_card",
                "template_card": {
                    "card_type": "text_notice",
                    "main_title": {"title": title},
                    "sub_title_text": content,
                    "card_action": {"type": 1, "url": url},
                },
            }
        elif kind == "dingtalk":
            payload = {
                "msgtype": "actionCard",
                "actionCard": {
                    "title": title,
                    "text": content,
                    "singleTitle": "查看中转日志",
                    "singleURL": url,
                },
            }
        else:
            raise DeliveryError("不支持的目标平台")
    if len(json.dumps(payload, ensure_ascii=False).encode()) > 20000:
        raise DeliveryError("目标卡片超过 20000 UTF-8 字节，请缩短提示词或模板")
    return payload


async def deliver(config: dict, payload: dict, trace_id: str) -> dict:
    mentions = config.get("target_mentions") or {}
    notification = None
    if config["target_type"] in {"wecom", "dingtalk"} and any(
        mentions.get(key) for key in ("all", "user_ids", "mobiles")
    ):
        # Validate both payloads before sending anything. Card formats do not use text @ fields.
        notification = build_text_payload(
            config["target_type"],
            f"[{config.get('name', '中转站通知')}] 请查看上方通知卡片。",
            mentions,
        )
    result = await send_payload(config, payload, trace_id)
    if notification is not None:
        try:
            mention_result = await send_payload(config, notification, trace_id)
        except Exception as exc:
            reason = str(exc) if isinstance(exc, DeliveryError) else type(exc).__name__
            raise DeliveryError(f"卡片已发送，但 @ 提醒失败：{reason}；重试会再次发送卡片") from exc
        result = {**result, "mention_response": mention_result}
    return result


async def send_payload(config: dict, payload: dict, trace_id: str) -> dict:
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
