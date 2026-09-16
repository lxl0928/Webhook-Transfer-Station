"""Source-specific authentication, parsing, and event classification."""

import hmac
import json
import re
from urllib.parse import parse_qs

from fastapi import HTTPException, Request

from app.models import Webhook
from app.security import decrypt

EVENT_NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,32}$")


def parse_payload(raw: bytes, content_type: str, source_type: str):
    media_type = content_type.split(";", 1)[0].lower().strip()
    try:
        if source_type == "generic" and media_type == "text/plain":
            return raw.decode("utf-8")
        if source_type == "generic" and media_type == "application/x-www-form-urlencoded":
            values = parse_qs(raw.decode("utf-8"), keep_blank_values=True, max_num_fields=1000)
            return {key: value[0] if len(value) == 1 else value for key, value in values.items()}
        if media_type and media_type != "application/json" and not media_type.endswith("+json"):
            raise HTTPException(415, "请使用 JSON；通用源站另支持 UTF-8 text/plain 和 URL 编码表单")
        payload = json.loads(raw, parse_constant=lambda value: reject_non_json(value))
        if source_type == "gitee" and not isinstance(payload, dict):
            raise ValueError
        if payload is None:
            raise ValueError
        return payload
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise HTTPException(
            400, "回调内容格式无效；Gitee 需要 JSON 对象，其他源站不接受 null"
        ) from None


def reject_non_json(value: str):
    raise ValueError("Non-finite JSON numbers are not supported")


def authenticate_source(request: Request, hook: Webhook, payload) -> None:
    if hook.source_type == "gitee":
        supplied = request.headers.get("X-Gitee-Token") or payload.get("password", "")
    elif hook.source_auth == "query":
        supplied = request.query_params.get("token", "")
    elif hook.source_auth == "bearer":
        scheme, _, supplied = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer":
            supplied = ""
    else:
        supplied = request.headers.get(hook.source_token_header, "")
    if not isinstance(supplied, str) or not hmac.compare_digest(
        supplied.encode(), decrypt(hook.source_secret).encode()
    ):
        raise HTTPException(401, "源站回调密钥不正确")


def generic_event(source_type: str, header: str | None, payload) -> str:
    if header:
        event = header
    elif source_type == "nightingale":
        if isinstance(payload, list) or (
            isinstance(payload, dict) and isinstance(payload.get("events"), list)
        ):
            event = "alert_batch"
        elif isinstance(payload, dict) and payload.get("is_recovered") in (True, 1, "1", "true"):
            event = "recovery"
        else:
            event = "alert"
    else:
        value = (
            payload.get("event_type", payload.get("event")) if isinstance(payload, dict) else None
        )
        event = value if isinstance(value, str) and EVENT_NAME.fullmatch(value) else "webhook"
    if not EVENT_NAME.fullmatch(event):
        raise HTTPException(
            400, "事件名需为 1–32 位字母、数字或 _ . : -；可通过 X-Webhook-Event 指定"
        )
    return event
