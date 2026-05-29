# Local Model Learning Workflow

Last updated: 2026-05-24

The local model should learn Smart Center information through a controlled RAG or training export pipeline, not by silently memorizing chat messages.

## Recommended Path

1. Export knowledge from Smart Center:

```powershell
python scripts/export_local_model_training.py
```

or use `POST /api/local-model/export-training` from the local-model page.

2. The export writes files under `SMART_CENTER_DATA_DIR/training/local_model`:

- `devices_*.jsonl`: configured devices plus runtime `server_machines`.
- `protocols_*.jsonl`: protocol/config/driver records.
- `logs_*.jsonl`: recent event, operation, and audit logs, with sensitive fields redacted.
- `instructions_*.jsonl`: curated query instructions.
- `insights_*.jsonl`: device profiles, server inventory, protocol cards, inference rules, and log summaries.
- `knowledge_*.json`: manifest and counts.

3. Feed the latest files to the local model knowledge proxy/RAG index. RAG is preferred for frequently changing facts such as online/offline server state, CPU/GPU metrics, and logs.

4. Optional fine-tuning or LoRA should only use curated examples from `instructions_*.jsonl` and reviewed rows. Do not fine-tune on raw secrets, tokens, SNMP community strings, RTSP credentials, or unreviewed logs.

## Server Knowledge

Server assets are exported from `monitor.db` as `source_section=server_machines`. Each record includes:

- `asset_group`: for example `机房`, `2号厅`, `机房-马勇`, `1号厅`, or `未分组`.
- `custom_name`, `hostname`, `ip`, `mac`.
- `last_online`, `agent_version`, `os`.
- `metrics.cpu_percent`, `metrics.mem_percent`, `metrics.disk_percent`, `metrics.gpu_names`.
- sanitized raw status for deeper retrieval.

Natural language should query all server groups by default. Specific group queries must filter by `asset_group`; specific host queries must match `custom_name`, `hostname`, `ip`, or `mac`.

## Control Boundary

The model may classify intent, retrieve evidence, summarize, and act as a natural-language control entry from Feishu or the Smart Center local-model page.

Real device actions must still go through the existing Smart Center control chain: API permission, audit log, target matching, risk classification, and confirmation policy. Strong-current cabinets, sequencers, server shutdown/restart, and unclear inferred targets must require confirmation before execution. The model must never invent a separate direct-control route that bypasses this chain.
