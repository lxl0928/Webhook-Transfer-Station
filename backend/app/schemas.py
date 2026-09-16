from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from app.config import get_settings
from app.templates import validate_template

Source = Literal["gitee", "nightingale", "generic"]
Event = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,32}$")]
Target = Literal["feishu", "wecom", "dingtalk"]
Status = Literal["pending", "processing", "succeeded", "failed", "ignored"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(StrictModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def validate_llm_host(value: str) -> str:
    url = urlsplit(value)
    settings = get_settings()
    allowed = {host.strip().lower() for host in settings.llm_allowed_hosts.split(",")}
    schemes = {"https", "http"} if settings.allow_http_llm else {"https"}
    if (
        url.scheme not in schemes
        or url.hostname not in allowed
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError(
            "LLM Host 必须使用允许的协议和 LLM_ALLOWED_HOSTS 中的域名，无认证或查询参数"
        )
    return value.rstrip("/")


def validate_target_url(kind: str, value: str) -> str:
    url = urlsplit(value)
    domains = {
        "feishu": "open.feishu.cn",
        "wecom": "qyapi.weixin.qq.com",
        "dingtalk": "oapi.dingtalk.com",
    }
    paths = {
        "feishu": "/open-apis/bot/v2/hook/",
        "wecom": "/cgi-bin/webhook/send",
        "dingtalk": "/robot/send",
    }
    path_ok = (
        (url.path.startswith(paths[kind]) and len(url.path) > len(paths[kind]))
        if kind == "feishu"
        else url.path == paths[kind]
    )
    if (
        url.scheme != "https"
        or url.hostname != domains[kind]
        or url.port not in (None, 443)
        or url.username
        or url.password
        or url.fragment
        or not path_ok
    ):
        raise ValueError("目标地址必须为对应平台的官方 HTTPS 群机器人 Webhook 地址")
    return value


class ProfileUpdate(StrictModel):
    real_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=32)
    llm_host: str | None = Field(default=None, max_length=512)
    llm_api_key: str | None = Field(default=None, max_length=2048)
    llm_model: str | None = Field(default=None, max_length=128)
    current_password: str | None = Field(default=None, max_length=256)
    new_password: str | None = Field(default=None, min_length=10, max_length=256)

    @field_validator("llm_host")
    @classmethod
    def host(cls, value):
        return validate_llm_host(value) if value is not None else value


class Mentions(StrictModel):
    all: bool = False
    user_ids: list[
        Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:@-]+$")]
    ] = Field(default_factory=list, max_length=100)
    mobiles: list[Annotated[str, Field(pattern=r"^\+?[0-9]{5,20}$")]] = Field(
        default_factory=list, max_length=100
    )

    @model_validator(mode="after")
    def normalize(self):
        self.user_ids = list(dict.fromkeys(self.user_ids))
        self.mobiles = list(dict.fromkeys(self.mobiles))
        if any(value in {"all", "@all"} for value in self.user_ids):
            raise ValueError("@所有人请使用 all 开关")
        if self.all and (self.user_ids or self.mobiles):
            raise ValueError("@所有人与指定成员不能同时配置")
        return self


class WebhookFields(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    source_type: Source = "gitee"
    source_auth_enabled: bool = True
    source_auth: Literal["header", "bearer", "query"] = "header"
    source_token_header: str = Field(default="X-Webhook-Token", pattern=r"^[A-Za-z0-9-]{1,64}$")
    source_url: str = Field(default="", max_length=512)
    source_info: dict = Field(default_factory=dict)
    events: list[Event] | None = Field(default=None, max_length=100)
    source_template: str = Field(default="{{payload}}", min_length=1, max_length=20000)
    llm_enabled: bool = True
    llm_prompt: str = Field(
        default="请用中文概括以下仓库事件，突出变更内容、作者和相关链接。",
        min_length=1,
        max_length=20000,
    )
    target_type: Target
    target_mentions: Mentions = Field(default_factory=Mentions)
    target_template: str = Field(default="{{llm_output}}", min_length=1, max_length=20000)
    enabled: bool = True

    @field_validator("source_template", "target_template")
    @classmethod
    def template(cls, value):
        return validate_template(value)

    @field_validator("source_token_header")
    @classmethod
    def safe_header(cls, value):
        if value.lower() in {
            "x-trace-id",
            "x-webhook-event",
            "x-webhook-delivery",
            "host",
            "content-type",
            "content-length",
        }:
            raise ValueError("密钥 Header 不能使用追踪、事件或协议保留字段")
        return value

    @model_validator(mode="after")
    def source_and_mentions(self):
        if self.events is None:
            self.events = (
                ["push", "pull_request", "tag", "comment"] if self.source_type == "gitee" else []
            )
        self.events = list(dict.fromkeys(self.events))
        if self.source_type == "gitee":
            if (
                not self.source_url
                or not self.events
                or set(self.events) - {"push", "pull_request", "tag", "comment"}
            ):
                raise ValueError("Gitee 需要仓库地址及有效的仓库事件列表")
            if self.source_auth != "header":
                raise ValueError("Gitee 使用 X-Gitee-Token 或 JSON password 校验")
        if self.source_url:
            url = urlsplit(self.source_url)
            schemes = {"https"} if self.source_type == "gitee" else {"https", "http"}
            if (
                url.scheme not in schemes
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError("源站地址需为 HTTP(S) 页面地址，无认证或查询参数；Gitee 需 HTTPS")
            self.source_url = self.source_url.rstrip("/")
            if self.source_type == "gitee":
                self.source_url = self.source_url.removesuffix(".git")
        if self.target_type == "feishu":
            if self.target_mentions.mobiles or any(
                not value.startswith("ou_") for value in self.target_mentions.user_ids
            ):
                raise ValueError("飞书自定义机器人仅支持 Open ID（ou_ 开头），不支持手机号")
        return self


class WebhookCreate(WebhookFields):
    source_secret: str = Field(default="", max_length=256)
    target_url: str = Field(min_length=1, max_length=2048)
    target_secret: str = Field(default="", max_length=512)

    @model_validator(mode="after")
    def target(self):
        if (self.source_auth_enabled or self.source_secret) and len(self.source_secret) < 8:
            raise ValueError("启用源站回调鉴权时必须配置至少 8 位密钥；非空密钥至少 8 位")
        validate_target_url(self.target_type, self.target_url)
        return self


class WebhookUpdate(WebhookFields):
    # PUT replaces all non-secret configuration; absent secrets retain their stored value.
    source_secret: str | None = Field(default=None, min_length=8, max_length=256)
    target_url: str | None = Field(default=None, min_length=1, max_length=2048)
    target_secret: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def target(self):
        if self.target_url is not None:
            validate_target_url(self.target_type, self.target_url)
        return self


# Explicit response models keep /docs useful and prevent accidental secret exposure.


class ProfileResponse(BaseModel):
    id: str
    username: str
    real_name: str
    phone: str
    created_at: datetime
    last_login_at: datetime | None
    llm_host: str
    llm_model: str
    llm_api_key_set: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: ProfileResponse


class WebhookResponse(WebhookFields):
    wid: str
    url: str
    source_secret_set: bool
    target_url_set: bool
    target_secret_set: bool
    created_at: datetime
    updated_at: datetime


class LogSummary(BaseModel):
    id: str
    wid: str
    webhook_name: str
    trace_id: str
    event: str
    status: Status
    attempts: int
    error: str | None
    received_at: datetime
    started_at: datetime | None
    output_at: datetime | None
    finished_at: datetime | None
    cost_ms: int | None


class LogDetail(LogSummary):
    input_payload: JsonValue
    output_payload: dict | None
    llm_output: str | None
    target_response: dict | None
    delivery_id: str | None


class Page[T](BaseModel):
    items: list[T]
    total: int


class Accepted(BaseModel):
    id: str
    status: Status
    duplicate: bool


class RetryResponse(BaseModel):
    id: str
    status: Status
