import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(UTC)


def uid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "tb_user"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    real_name: Mapped[str] = mapped_column(String(100), default="管理员")
    phone: Mapped[str] = mapped_column(String(32), default="")
    llm_host: Mapped[str] = mapped_column(String(512), default="https://api.openai.com/v1")
    llm_api_key: Mapped[str] = mapped_column(Text, default="")
    llm_model: Mapped[str] = mapped_column(String(128), default="")
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Webhook(Base):
    __tablename__ = "tb_webhooks"
    wid: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("tb_user.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    source_type: Mapped[str] = mapped_column(String(32), default="gitee")
    source_auth: Mapped[str] = mapped_column(String(16), default="header", server_default="header")
    source_token_header: Mapped[str] = mapped_column(
        String(64), default="X-Webhook-Token", server_default="X-Webhook-Token"
    )
    source_url: Mapped[str] = mapped_column(String(512))
    source_info: Mapped[dict] = mapped_column(JSON, default=dict)
    source_secret: Mapped[str] = mapped_column(Text)
    events: Mapped[list] = mapped_column(JSON)
    source_template: Mapped[str] = mapped_column(Text, default="{{payload}}")
    llm_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    llm_prompt: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str] = mapped_column(String(32))
    target_mentions: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    target_template: Mapped[str] = mapped_column(Text, default="{{llm_output}}")
    target_url: Mapped[str] = mapped_column(Text)
    target_secret: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class WebhookLog(Base):
    __tablename__ = "tb_webhooks_log"
    __table_args__ = (
        UniqueConstraint("wid", "delivery_id", name="uq_log_delivery"),
        Index("ix_log_queue", "status", "received_at"),
        Index("ix_log_owner_time", "user_id", "received_at"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    # Preserve audit history when a webhook is deleted.
    wid: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("tb_user.id"))
    webhook_name: Mapped[str] = mapped_column(String(100))
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    delivery_id: Mapped[str | None] = mapped_column(String(128))
    event: Mapped[str] = mapped_column(String(32))
    input_payload: Mapped[dict | list | str | int | float | bool] = mapped_column(JSON)
    output_payload: Mapped[dict | None] = mapped_column(JSON)
    llm_output: Mapped[str | None] = mapped_column(Text)
    # Encrypt frozen config, including destination credentials, for durable processing.
    config_snapshot: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    target_response: Mapped[dict | None] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cost_ms: Mapped[int | None] = mapped_column(Integer)


class Skill(Base):
    __tablename__ = "tb_skill"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_skill_owner_name"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("tb_user.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(500))
    instructions: Mapped[str] = mapped_column(Text)
    tools: Mapped[list] = mapped_column(JSON)
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Conversation(Base):
    __tablename__ = "tb_chat_conversation"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("tb_user.id"), index=True)
    title: Mapped[str] = mapped_column(String(100), default="新对话")
    lease_token: Mapped[str | None] = mapped_column(String(32))
    busy_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ChatMessage(Base):
    __tablename__ = "tb_chat_message"
    __table_args__ = (Index("ix_chat_message_order", "conversation_id", "created_at", "id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("tb_chat_conversation.id"))
    role: Mapped[str] = mapped_column(String(16))
    # Encrypted wire-format message; tool call arguments/results can contain business data.
    body: Mapped[str] = mapped_column(Text)
    trace_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ChatAction(Base):
    __tablename__ = "tb_chat_action"
    __table_args__ = (Index("ix_chat_action_pending", "conversation_id", "status"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("tb_chat_conversation.id"))
    tool_name: Mapped[str] = mapped_column(String(64))
    arguments: Mapped[str] = mapped_column(Text)
    skill_ids: Mapped[list] = mapped_column(JSON)
    expected_state: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    result: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
