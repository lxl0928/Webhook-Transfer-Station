#!/usr/bin/env bash
# Run manually: sends a real test notification using the selected relay rule.
set -euo pipefail
alert_now=$(date +%s)
alert_delivery=$(uuidgen)
curl -i -X POST \
  'http://localhost:5173/webhooks?wid=ab8f246cdc884b3580c4343309051d08' \
  -H 'Content-Type: application/json' \
  -H "X-Trace-Id: disk-alert-${alert_delivery}" \
  -H "X-Webhook-Delivery: ${alert_delivery}" \
  -H 'X-Webhook-Event: alert' \
  --data-binary @- <<JSON
{
  "id": 95,
  "cluster": "VictoriaMetrics-Demo",
  "rule_name": "磁盘使用率大于90%监控规则",
  "severity": 2,
  "is_recovered": false,
  "target_ident": "Dev-PC-160",
  "tags": [
    "name=disk_used_percent",
    "device=nvme0n1p5",
    "fstype=ext4",
    "ident=Dev-PC-160",
    "mode=rw",
    "path=/",
    "rulename=磁盘使用率大于90%监控规则"
  ],
  "trigger_time": ${alert_now},
  "send_time": ${alert_now},
  "trigger_value": 93.06
}
JSON
