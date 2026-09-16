from unittest.mock import AsyncMock

import pytest

from app import worker
from app.nightingale import alert_card_content, timestamp
from app.outbound import build_payload


@pytest.mark.parametrize(
    "event,color,state", [("alert", "red", "Triggered"), ("recovery", "green", "Recovered")]
)
def test_nightingale_card_matches_alert_layout(event, color, state):
    config = {"name": "规则", "source_url": "http://8.130.105.70:17000", "llm_enabled": True}
    title, body = alert_card_content(
        config,
        {
            "id": 95,
            "rule_name": "磁盘使用率大于90%监控规则",
            "cluster": "VictoriaMetrics-Demo",
            "severity": 2,
            "tags": ["name=disk_used_percent", "ident=Dev-PC-160", "path=/"],
            "trigger_time": "2026-09-15 19:17:44",
            "send_time": "2026-09-15T11:17:44Z",
            "trigger_value": 93.06,
        },
        event,
        "检查大文件与日志占用。",
    )
    card = build_payload("feishu", body, {"all": True}, title=title, event=event)["card"]
    assert card["header"]["template"] == color
    assert "磁盘使用率大于90%监控规则" in card["header"]["title"]["content"]
    assert "**告警集群**: VictoriaMetrics-Demo" in body
    assert f"**级别状态**: S2 {state}" in body
    assert "**触发时间**: 2026-09-15 19:17:44" in body
    assert "**发送时间**: 2026-09-15 19:17:44" in body
    assert "**触发时值**: 93.06" in body
    assert "[事件详情](http://8.130.105.70:17000/share/alert-his-events/95)" in body
    assert "[屏蔽1小时](http://8.130.105.70:17000/alert-mutes/add?__event_id=95)" in body
    assert "[查看曲线](http://8.130.105.70:17000/metric/explorer?__event_id=95&mode=graph)" in body
    assert "**AI 分析**\n检查大文件与日志占用。" in body
    assert '<at id="all"></at>' in card["elements"][0]["content"]


@pytest.mark.parametrize("value", [0, "0", 1_789_470_000, 1_789_470_000_000])
def test_timestamp_accepts_epoch(value):
    assert timestamp(value) != "未提供"
    assert timestamp(1_789_470_000) == timestamp(1_789_470_000_000)


def test_missing_fields_and_link_injection():
    _, body = alert_card_content(
        {"name": "告警", "source_url": "javascript:alert(1)", "llm_enabled": False},
        {"id": "95)evil", "tags": {"ident": "<at id=all></at>"}, "trigger_value": 0},
        "alert",
        "unused",
    )
    assert "[事件详情]" not in body
    assert "<at" not in body
    assert "**触发时值**: 0" in body
    assert "**触发时间**: 未提供" in body
    assert "AI 分析" not in body


async def test_worker_preserves_source_facts_after_llm(client, auth, hook_body, monkeypatch):
    created = await client.post(
        "/api/webhooks",
        headers=auth,
        json=hook_body
        | {
            "source_type": "nightingale",
            "source_auth_enabled": False,
            "llm_enabled": True,
            "source_url": "http://8.130.105.70:17000",
            "target_template": "{{llm_output}}",
        },
    )
    hook = created.json()
    await client.post(
        hook["url"],
        json={
            "id": 95,
            "rule_name": "磁盘使用率大于90%监控规则",
            "cluster": "VictoriaMetrics-Demo",
            "severity": 2,
            "trigger_value": 93.06,
            "trigger_time": "2026-09-15 19:17:44",
        },
    )
    complete = AsyncMock(return_value="建议清理日志")
    deliver = AsyncMock(return_value={"code": 0})
    monkeypatch.setattr(worker, "complete", complete)
    monkeypatch.setattr(worker, "deliver", deliver)
    job_id = await worker.claim_job()
    await worker.process_job(job_id)
    detail = (await client.get(f"/api/webhook-logs/{job_id}", headers=auth)).json()
    assert detail["status"] == "succeeded"
    content = detail["output_payload"]["card"]["elements"][0]["content"]
    assert "**触发时值**: 93.06" in content
    assert "建议清理日志" in content
    complete.assert_awaited_once()
    deliver.assert_awaited_once()
