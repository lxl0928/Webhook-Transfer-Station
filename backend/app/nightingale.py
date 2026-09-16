"""Preserve Nightingale alert facts independently of model-generated analysis."""

import re
from datetime import UTC, datetime, timedelta, timezone
from urllib.parse import urlsplit

CHINA_TIME = timezone(timedelta(hours=8))


def text(value) -> str:
    if value is None or value == "":
        return "未提供"
    value = str(value).replace("\n", " ").replace("\r", " ")
    # Payload values are text, not Markdown/mention/link instructions.
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_\[\]])", r"\\\1", value)


def timestamp(value) -> str:
    try:
        if isinstance(value, bool) or value is None or value == "":
            return "未提供"
        if isinstance(value, (int, float)) or str(value).isdigit():
            seconds = float(value)
            if seconds > 100_000_000_000:
                seconds /= 1000
            date = datetime.fromtimestamp(seconds, UTC)
        else:
            date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if date.tzinfo is None:
                date = date.replace(tzinfo=CHINA_TIME)
        return date.astimezone(CHINA_TIME).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OverflowError, OSError):
        return "未提供"


def alert_card_content(config: dict, payload: dict, event: str, analysis: str) -> tuple[str, str]:
    name = str(payload.get("rule_name") or config["name"])
    recovered = event == "recovery"
    title = ("✅ " if recovered else "🔔 ") + name
    tags = payload.get("tags", [])
    if isinstance(tags, dict):
        tags = [f"{key}={value}" for key, value in tags.items()]
    if isinstance(tags, list):
        tags = "[" + " ".join(str(tag) for tag in tags) + "]"
    severity = str(payload.get("severity", "未提供"))
    if severity.isdigit():
        severity = "S" + severity
    fields = [
        ("告警集群", payload.get("cluster") or payload.get("datasource_name")),
        ("级别状态", severity + (" Recovered" if recovered else " Triggered")),
        ("告警名称", name),
        ("事件标签", tags),
        ("触发时间", timestamp(payload.get("trigger_time"))),
        ("发送时间", timestamp(payload.get("send_time") or datetime.now(UTC).isoformat())),
        ("触发时值", payload.get("trigger_value")),
    ]
    body = "\n".join(f"**{label}**: {text(value)}" for label, value in fields)
    base = config.get("source_url", "").rstrip("/")
    event_id = str(payload.get("id", ""))
    try:
        url = urlsplit(base)
        valid = (
            url.scheme in {"http", "https"}
            and url.hostname
            and not (url.username or url.password or url.query or url.fragment)
            and not any(char in base for char in '()<>" \n\r')
        )
    except ValueError:
        valid = False
    if valid and event_id.isascii() and event_id.isdigit() and len(event_id) <= 20:
        body += (
            f"\n\n[事件详情]({base}/share/alert-his-events/{event_id})"
            f" | [屏蔽1小时]({base}/alert-mutes/add?__event_id={event_id})"
            f" | [查看曲线]({base}/metric/explorer?__event_id={event_id}&mode=graph)"
        )
    if config.get("llm_enabled") and analysis.strip():
        body += "\n\n---\n**AI 分析**\n" + analysis.strip()
    return title, body
