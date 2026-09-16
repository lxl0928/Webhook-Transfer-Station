import asyncio
import json
import time
from collections import defaultdict, deque
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import commit, get_db
from app.deps import current_user
from app.models import User, Webhook, WebhookLog, now
from app.outbound import complete
from app.schemas import (
    Accepted,
    LogDetail,
    Login,
    LogSummary,
    Page,
    ProfileResponse,
    ProfileUpdate,
    RetryResponse,
    Status,
    TokenResponse,
    WebhookCreate,
    WebhookResponse,
    WebhookUpdate,
    validate_target_url,
)
from app.security import create_token, decrypt, encrypt, hash_password, redact, verify_password
from app.sources import authenticate_source, generic_event, parse_payload

router = APIRouter()
login_attempts: dict[str, deque] = defaultdict(deque)


def profile(user: User) -> dict:
    return {
        key: getattr(user, key)
        for key in (
            "id",
            "username",
            "real_name",
            "phone",
            "created_at",
            "last_login_at",
            "llm_host",
            "llm_model",
        )
    } | {"llm_api_key_set": bool(user.llm_api_key)}


def webhook_view(hook: Webhook) -> dict:
    fields = (
        "wid",
        "name",
        "source_type",
        "source_auth",
        "source_token_header",
        "source_url",
        "source_info",
        "events",
        "source_template",
        "llm_enabled",
        "llm_prompt",
        "target_type",
        "target_template",
        "target_mentions",
        "enabled",
        "created_at",
        "updated_at",
    )
    return {key: getattr(hook, key) for key in fields} | {
        "url": f"{get_settings().public_base_url.rstrip('/')}/webhooks?wid={hook.wid}",
        "source_secret_set": bool(hook.source_secret),
        "target_url_set": bool(hook.target_url),
        "target_secret_set": bool(hook.target_secret),
    }


def log_view(log: WebhookLog, detail: bool = False) -> dict:
    fields = [
        "id",
        "wid",
        "webhook_name",
        "trace_id",
        "event",
        "status",
        "attempts",
        "error",
        "received_at",
        "started_at",
        "output_at",
        "finished_at",
        "cost_ms",
    ]
    if detail:
        fields += [
            "input_payload",
            "output_payload",
            "llm_output",
            "target_response",
            "delivery_id",
        ]
    return {key: getattr(log, key) for key in fields}


async def owned_hook(wid: str, user: User, db: AsyncSession) -> Webhook:
    hook = await db.get(Webhook, wid)
    if hook is None or hook.user_id != user.id:
        raise HTTPException(404, "中转规则不存在")
    return hook


@router.post("/api/auth/login", response_model=TokenResponse, tags=["认证"])
async def login(body: Login, request: Request, db: AsyncSession = Depends(get_db)):
    address = request.client.host if request.client else "unknown"
    attempts = login_attempts[address]
    timestamp = time.monotonic()
    while attempts and attempts[0] < timestamp - 60:
        attempts.popleft()
    if len(attempts) >= get_settings().login_max_attempts:
        raise HTTPException(429, "登录尝试过于频繁，请稍后重试", headers={"Retry-After": "60"})
    attempts.append(timestamp)
    if len(login_attempts) > 10000:
        for key in list(login_attempts):
            if not login_attempts[key] or login_attempts[key][-1] < timestamp - 60:
                del login_attempts[key]
    user = await db.scalar(select(User).where(User.username == body.username))
    # Run expensive password hashing outside the event loop, including nonexistent users.
    valid = await asyncio.to_thread(
        verify_password, body.password, user.password_hash if user else DUMMY_HASH
    )
    if user is None or not valid:
        raise HTTPException(401, "用户名或密码错误")
    user.last_login_at = now()
    await db.commit()
    return {"access_token": create_token(user), "token_type": "bearer", "user": profile(user)}


DUMMY_HASH = hash_password("not-a-real-account-password")


@router.get("/api/users/me", response_model=ProfileResponse, tags=["用户"])
async def get_profile(user: User = Depends(current_user)):
    return profile(user)


@router.patch("/api/users/me", response_model=ProfileResponse, tags=["用户"])
async def update_profile(
    body: ProfileUpdate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    changes = body.model_dump(exclude_none=True)
    if body.new_password is not None:
        if not body.current_password or not await asyncio.to_thread(
            verify_password, body.current_password, user.password_hash
        ):
            raise HTTPException(400, "当前密码不正确")
        user.password_hash = await asyncio.to_thread(hash_password, body.new_password)
        user.token_version += 1
    for key, value in changes.items():
        if key not in {"current_password", "new_password"}:
            setattr(user, key, encrypt(value) if key == "llm_api_key" and value else value)
    await commit(db)
    return profile(user)


@router.post("/api/auth/logout", status_code=204, tags=["认证"])
async def logout(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    user.token_version += 1
    await db.commit()


@router.get("/api/webhooks", response_model=Page[WebhookResponse], tags=["中转规则"])
async def list_hooks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str = Query("", max_length=100),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    conditions = [Webhook.user_id == user.id]
    if q:
        conditions.append(Webhook.name.contains(q, autoescape=True))
    total = await db.scalar(select(func.count()).select_from(Webhook).where(*conditions))
    rows = await db.scalars(
        select(Webhook)
        .where(*conditions)
        .order_by(Webhook.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {"items": [webhook_view(hook) for hook in rows], "total": total}


@router.post("/api/webhooks", response_model=WebhookResponse, status_code=201, tags=["中转规则"])
async def create_hook(
    body: WebhookCreate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    data = body.model_dump()
    for key in ("source_secret", "target_url", "target_secret"):
        data[key] = encrypt(data[key]) if data[key] else ""
    hook = Webhook(user_id=user.id, **data)
    db.add(hook)
    await commit(db)
    return webhook_view(hook)


@router.get("/api/webhooks/{wid}", response_model=WebhookResponse, tags=["中转规则"])
async def get_hook(
    wid: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    return webhook_view(await owned_hook(wid, user, db))


@router.put("/api/webhooks/{wid}", response_model=WebhookResponse, tags=["中转规则"])
async def update_hook(
    wid: str,
    body: WebhookUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    hook = await owned_hook(wid, user, db)
    try:
        validate_target_url(body.target_type, body.target_url or decrypt(hook.target_url))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if body.target_type != hook.target_type and body.target_secret is None:
        hook.target_secret = ""
    for key, value in body.model_dump(exclude_none=True).items():
        if key in {"source_secret", "target_url", "target_secret"}:
            value = encrypt(value) if value else ""
        setattr(hook, key, value)
    await commit(db)
    return webhook_view(hook)


@router.delete("/api/webhooks/{wid}", status_code=204, tags=["中转规则"])
async def delete_hook(
    wid: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    hook = await owned_hook(wid, user, db)
    await db.delete(hook)
    await commit(db)


def detect_event(header: str, payload: dict) -> str:
    value = header.lower().replace(" ", "_").removesuffix("_hook")
    if value in {"tag_push", "tag"} or (
        value == "push" and str(payload.get("ref", "")).startswith("refs/tags/")
    ):
        return "tag"
    return {
        "push": "push",
        "merge_request": "pull_request",
        "pull_request": "pull_request",
        "note": "comment",
        "comment": "comment",
    }.get(value, "unsupported")


def make_snapshot(hook: Webhook, user: User) -> str:
    data = {
        key: getattr(hook, key)
        for key in (
            "name",
            "source_url",
            "source_type",
            "source_info",
            "source_template",
            "llm_enabled",
            "llm_prompt",
            "target_type",
            "target_template",
            "target_mentions",
        )
    }
    data.update(
        target_url=decrypt(hook.target_url),
        target_secret=decrypt(hook.target_secret),
        llm_host=user.llm_host,
        llm_api_key=decrypt(user.llm_api_key),
        llm_model=user.llm_model,
    )
    return encrypt(json.dumps(data, ensure_ascii=False))


@router.post(
    "/webhooks",
    response_model=Accepted,
    status_code=202,
    tags=["源站回调"],
    responses={200: {"model": Accepted, "description": "通用/夜莺回调已入队，或 delivery ID 重复"}},
    description=(
        "Gitee 使用 X-Gitee-Token/JSON password。"
        "其他源站按规则使用自定义密钥头、Bearer 或 URL token。"
        "X-Webhook-Event 指定事件，X-Webhook-Delivery 用于去重。成功响应仅表示入队。"
    ),
    openapi_extra={
        "parameters": [
            {
                "name": "token",
                "in": "query",
                "required": False,
                "description": "仅 source_auth=query 时使用；填写规则回调密钥",
                "schema": {"type": "string"},
            }
        ],
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {},
                    "example": {"event_type": "service.error", "message": "数据库连接超时"},
                },
                "text/plain": {"schema": {"type": "string"}},
                "application/x-www-form-urlencoded": {
                    "schema": {"type": "object", "additionalProperties": {"type": "string"}}
                },
            },
        },
    },
)
async def receive_webhook(
    request: Request,
    response: Response,
    wid: str = Query(pattern=r"^[a-f0-9]{32}$"),
    db: AsyncSession = Depends(get_db),
):
    hook = await db.get(Webhook, wid)
    if hook is None:
        raise HTTPException(404, "中转规则不存在")
    if not hook.enabled:
        raise HTTPException(409, "中转规则已停用")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > get_settings().max_payload_bytes:
            raise HTTPException(413, "回调消息超过大小限制")
    payload = parse_payload(bytes(raw), request.headers.get("Content-Type", ""), hook.source_type)
    authenticate_source(request, hook, payload)
    if hook.source_type == "gitee":
        repository = payload.get("repository")
        actual_url = (
            (repository.get("html_url") or repository.get("url"))
            if isinstance(repository, dict)
            else None
        )
        if (
            not isinstance(actual_url, str)
            or actual_url.rstrip("/").removesuffix(".git") != hook.source_url
        ):
            raise HTTPException(403, "回调仓库与源站配置不匹配")
        event = detect_event(request.headers.get("X-Gitee-Event", ""), payload)
        delivery_id = request.headers.get("X-Gitee-Delivery")
    else:
        event = generic_event(hook.source_type, request.headers.get("X-Webhook-Event"), payload)
        delivery_id = request.headers.get("X-Webhook-Delivery")
    if delivery_id and len(delivery_id) > 128:
        raise HTTPException(400, "Delivery ID 过长")
    user = await db.get(User, hook.user_id)
    ignored = (
        event not in hook.events
        if hook.source_type == "gitee"
        else bool(hook.events) and event not in hook.events
    )
    log = WebhookLog(
        wid=wid,
        user_id=hook.user_id,
        webhook_name=hook.name,
        trace_id=request.state.trace_id,
        delivery_id=delivery_id,
        event=event,
        input_payload=redact(payload),
        config_snapshot=make_snapshot(hook, user),
        status="ignored" if ignored else "pending",
        finished_at=now() if ignored else None,
        error="事件未启用或不支持" if ignored else None,
    )
    db.add(log)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(WebhookLog).where(WebhookLog.wid == wid, WebhookLog.delivery_id == delivery_id)
        )
        if existing is None:
            raise
        response.status_code = 200
        return {"id": existing.id, "status": existing.status, "duplicate": True}
    if hook.source_type != "gitee":
        response.status_code = 200
    return {"id": log.id, "status": log.status, "duplicate": False}


@router.get("/api/webhook-logs", response_model=Page[LogSummary], tags=["消息日志"])
async def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    wid: str | None = None,
    status: Status | None = None,
    trace_id: str | None = Query(None, max_length=64),
    start: datetime | None = None,
    end: datetime | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if start and start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end and end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    if start and end and start > end:
        raise HTTPException(422, "开始时间不能晚于结束时间")
    conditions = [WebhookLog.user_id == user.id]
    for column, value in (
        (WebhookLog.wid, wid),
        (WebhookLog.status, status),
        (WebhookLog.trace_id, trace_id),
    ):
        if value is not None:
            conditions.append(column == value)
    if start:
        conditions.append(WebhookLog.received_at >= start)
    if end:
        conditions.append(WebhookLog.received_at <= end)
    total = await db.scalar(select(func.count()).select_from(WebhookLog).where(*conditions))
    rows = await db.scalars(
        select(WebhookLog)
        .where(*conditions)
        .order_by(WebhookLog.received_at.desc(), WebhookLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {"items": [log_view(log) for log in rows], "total": total}


@router.get("/api/webhook-logs/{log_id}", response_model=LogDetail, tags=["消息日志"])
async def get_log(
    log_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    log = await db.get(WebhookLog, log_id)
    if log is None or log.user_id != user.id:
        raise HTTPException(404, "日志不存在")
    return log_view(log, detail=True)


@router.post(
    "/api/webhook-logs/{log_id}/retries",
    response_model=RetryResponse,
    status_code=202,
    tags=["消息日志"],
)
async def retry_log(
    log_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    # Atomic compare-and-set prevents simultaneous retries of the same failed job.
    result = await db.execute(
        update(WebhookLog)
        .where(
            WebhookLog.id == log_id, WebhookLog.user_id == user.id, WebhookLog.status == "failed"
        )
        .values(
            status="pending",
            error=None,
            started_at=None,
            finished_at=None,
            output_at=None,
            cost_ms=None,
            output_payload=None,
            llm_output=None,
            target_response=None,
        )
    )
    if result.rowcount != 1:
        raise HTTPException(409, "仅当前用户的失败消息可以重试")
    await commit(db)
    return {"id": log_id, "status": "pending"}


@router.get("/health/live", tags=["健康检测"])
async def live():
    return {"status": "ok", "backend": "ok"}


@router.get("/health/ready", tags=["健康检测"])
async def ready(response: Response, db: AsyncSession = Depends(get_db)):
    try:
        async with asyncio.timeout(5):
            await db.execute(text("SELECT 1"))
        return {"status": "ok", "backend": "ok", "postgresql": "ok"}
    except Exception:
        response.status_code = 503
        return {"status": "degraded", "backend": "ok", "postgresql": "unavailable"}


@router.post("/api/health/llm", tags=["健康检测"])
async def llm_health(response: Response, request: Request, user: User = Depends(current_user)):
    start = time.monotonic()
    config = {
        "llm_host": user.llm_host,
        "llm_api_key": decrypt(user.llm_api_key),
        "llm_model": user.llm_model,
        "llm_prompt": "Reply with OK only.",
    }
    try:
        await complete(config, "Health check", request.state.trace_id)
        return {"status": "ok", "llm": "ok", "cost_ms": int((time.monotonic() - start) * 1000)}
    except Exception:
        response.status_code = 503
        return {
            "status": "degraded",
            "llm": "unavailable",
            "detail": "检查 Host、API Key、模型与网络",
        }
