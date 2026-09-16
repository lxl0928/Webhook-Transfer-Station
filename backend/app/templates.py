import json
import re

VARIABLES = {
    "payload",
    "event",
    "repository",
    "source_url",
    "source_type",
    "source_info",
    "source_name",
    "llm_output",
}
TOKEN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z_0-9]*(?:\.[a-zA-Z0-9_-]{1,64})*)\s*}}")


def validate_template(value: str) -> str:
    for name in TOKEN.findall(value):
        parts = name.split(".")
        if (
            parts[0] not in VARIABLES
            or (len(parts) > 1 and parts[0] not in {"payload", "source_info"})
            or any(part.startswith("__") for part in parts)
        ):
            raise ValueError("模板变量不受支持；嵌套路径仅限 payload 或 source_info 的 JSON 字段")
    remainder = TOKEN.sub("", value)
    if "{{" in remainder or "}}" in remainder:
        raise ValueError("模板变量语法无效")
    return value


def resolve(name: str, context: dict):
    value = context
    for part in name.split("."):
        if isinstance(value, dict):
            value = value.get(part, "")
        elif (
            isinstance(value, list) and part.isdigit() and len(part) < 10 and int(part) < len(value)
        ):
            value = value[int(part)]
        else:
            return ""
    if isinstance(value, (dict, list, bool)) or value is None:
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def render(template: str, context: dict) -> str:
    # JSON traversal only. No eval, object attributes, or second interpolation pass.
    return TOKEN.sub(lambda match: resolve(match[1], context), template)


def context_for(config: dict, payload, event: str) -> dict:
    return {
        "payload": payload,
        "event": event,
        "repository": config["source_url"],
        "source_url": config["source_url"],
        "source_type": config.get("source_type", "gitee"),
        "source_info": config.get("source_info", {}),
        "source_name": config["name"],
        "llm_output": "",
    }
