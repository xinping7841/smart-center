# Local Model Learning Workflow

Last updated: 2026-06-01

The local model should learn Smart Center information through a controlled RAG or training export pipeline, not by silently memorizing chat messages.

## Recommended Path

1. Export knowledge from Smart Center:

```powershell
python scripts/export_local_model_training.py
```

or use `POST /api/local-model/export-training` from the local-model page.

2. The export writes runtime knowledge files under `SMART_CENTER_DATA_DIR/training/local_model`:

- `devices_*.jsonl`: configured devices plus runtime `server_machines`.
- `device_inventory_*.jsonl`: compact device inventory with aliases, capabilities, dependencies, and natural-language matching hints.
- `device_aliases_*.jsonl`: natural-language aliases used by Feishu and local-model control routing.
- `control_capabilities_*.jsonl`: explicit query/control capability records, risk level, confirmation policy, and safety chain.
- `protocols_*.jsonl`: protocol/config/driver records.
- `logs_*.jsonl`: recent event, operation, and audit logs, with sensitive fields redacted.
- `instructions_*.jsonl`: curated query instructions.
- `query_intents_*.jsonl`: curated read-only natural-language query intent examples and read API allowlist.
- `control_intents_*.jsonl`: curated controlled-action examples and safety expectations.
- `nl_intent_examples_*.jsonl`: unified query/control natural-language examples for intent classification, routing, and safety policy.
- `insights_*.jsonl`: device profiles, server inventory, protocol cards, inference rules, and log summaries.
- `system_map_*.json`: the runtime system directory for modules, device sections, natural-language contract, and recommended learning order.
- `knowledge_*.json`: manifest and counts.

3. The same command also writes source-code knowledge files unless `--skip-code-knowledge` is passed:

- `code_files_*.jsonl`: source files, `AI_*` markers, purpose, boundary, risk, config keys, and control paths.
- `code_routes_*.jsonl`: Flask routes, permissions, methods, source functions, and route risk.
- `code_modules_*.jsonl`: module-level summaries assembled from files and routes.
- `module_cards_*.jsonl`: compact module cards for local-model navigation.
- `code_design_*.jsonl`: compact design notes for Feishu natural language, local-model knowledge, and physical-control safety.
- `ai_marker_coverage_*.json`: coverage report for `AI_*` markers, including files missing required module/purpose/boundary/risk markers.
- `code_system_map_*.json`: source-code entrypoints, route risk summary, and execution boundary notes.
- `code_knowledge_*.jsonl`: combined file, route, module, and design records for RAG ingestion.
- `full_code_context_*.jsonl`: redacted source chunks for high-context periodic refresh on the 3090 machine.
- `code_manifest_*.json`: code-knowledge manifest and counts.

4. Feed the latest runtime and code knowledge files to the local model knowledge proxy/RAG index. RAG is preferred for frequently changing facts such as online/offline server state, CPU/GPU metrics, logs, current code boundaries, and routes.

Code changes should keep `AI_*` markers current in touched files. Treat the marker header as model-facing maintenance metadata: it should explain module ownership, safety boundaries, data flow, runtime, risk, compatibility, and search keywords for node-123.

5. Optional high-context refresh can run on the 3090 local-model machine. It should read `system_map_*.json`, `device_inventory_*.jsonl`, `control_capabilities_*.jsonl`, `nl_intent_examples_*.jsonl`, `code_system_map_*.json`, `module_cards_*.jsonl`, and then `full_code_context_*.jsonl` to generate a reviewable `system_summary_*.json`. This is a manual or asynchronous understanding refresh, not a direct control path.

6. Optional fine-tuning or LoRA should only use curated examples from `instructions_*.jsonl`, `query_intents_*.jsonl`, `control_intents_*.jsonl`, `nl_intent_examples_*.jsonl`, and reviewed rows. Do not fine-tune on raw secrets, tokens, SNMP community strings, RTSP credentials, unreviewed logs, or full source code.

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

Feishu control defaults to enabled so authorized natural-language control can work after deployment. The AI page switch persists to `config.json`; if an operator turns it off, Feishu keeps allowing queries and parsing, but refuses real execution across service restarts and releases until the switch is turned back on.

## Natural-Language Control Router

Smart Center uses a layered route for Feishu and local-model control:

1. Feishu strips mentions, handles pending confirmations/cancellations, and classifies whether the message is query or control.
2. Feedback memory checks previously confirmed or cancelled phrases in `SMART_CENTER_RUNTIME_DIR/control_feedback.jsonl`.
3. The deterministic safety router selects the safest module and blocks ambiguous phrases such as "把第8路关了".
4. If enabled, the local model may rewrite fuzzy text into a standard Chinese control phrase. The model output is untrusted and must be validated again by the deterministic router.
5. Smart Center executes only after the normal permission, risk, and confirmation policy. Strong-current cabinets, sequencers, server shutdown/restart, and inferred targets must require confirmation.

This makes the assistant improve from real usage while preventing the model from directly producing executable HTTP calls.

## High-Context Refresh On 3090

The 3090 host has enough VRAM to use larger local-model context windows, so Smart Center supports a periodic full-code understanding refresh without changing the control boundary:

1. Daily export writes structured runtime and code knowledge.
2. `full_code_context_*.jsonl` stores redacted source chunks. Runtime configs, common secret files, databases, binary assets, and generated backups are excluded.
3. `scripts/refresh_local_model_system_summary.py` can call the OpenAI-compatible local-model endpoint and write `system_summary_*.json`. Keep it manual/asynchronous unless the local model can finish reliably within the configured timeout.
4. The local-model page shows the latest `system_map`, device inventory, control capability, code map, full-code-context, and summary status.
5. The summary is used as RAG/maintenance context only. It never grants execution permission and never bypasses Smart Center API checks.

Recommended context length for the current 14B/3090 setup is `131072` first. If the model service is stable and latency is acceptable, it can be raised toward `262144`; if answers become vague or slow, lower it and rely more on RAG retrieval.

## Cloud Enhanced Model

Smart Center can configure an optional `local_model.cloud_model` block for Ark / DeepSeek-compatible OpenAI API access. The intended role is an enhanced understanding layer, not an execution authority:

- Local 14B / knowledge proxy remains the normal chat and RAG entry.
- Ark can be used for manual `system_summary_*.json` refresh when local 14B cannot finish a long summary reliably.
- Ark is currently the primary Feishu natural-language understanding source. For each Feishu turn, Ark and the local model both classify/rewrite in parallel; Smart Center records both outputs and currently selects the Ark result first. The selected result still routes through aliases, command policy, audit, and existing APIs.
- The cloud API key is runtime config only. It must not be committed to docs, source code, or exported knowledge files.

Production configuration should use `scripts/remote/configure_ark_cloud_model_20260602.py` with `ARK_API_KEY` supplied in the remote execution environment.

## Recommended Feishu Architecture

The target design should keep four layers separate, with cloud/local model comparison visible in the AI module:

- Feishu adapter: receives messages, renders text/card confirmations, stores short-lived pending controls, and records user decisions.
- Intent and retrieval layer: runs Ark and local model in parallel for Feishu NLU, selects Ark first for speed/understanding, logs the local result for comparison and learning, and retrieves `knowledge_*.json`, `insights_*.jsonl`, `device_aliases_*.jsonl`, `nl_intent_examples_*.jsonl`, and `code_knowledge_*.jsonl`.
- Tool/router layer: maps read intents to read-only allowlisted APIs and control intents to `LocalSmartCenterClient.resolve_control_command_with_translator`.
- Execution layer: calls existing Smart Center APIs only after permission, operation lock, audit, target confidence, risk classification, and confirmation policy.

Known design gaps to watch:

- Feishu uses app credentials, not a logged-in Smart Center session, so control execution should have an explicit service identity or HMAC/internal token instead of relying on whatever auth defaults the HTTP service applies.
- Low-risk direct execution is the operator-preferred mode for speed. Keep the AI page switch as the manual kill switch for Feishu execution while leaving queries available; use process logs to review mistakes and refine mappings.
- Pending controls are keyed by chat, so two people in the same group can overwrite each other. Include sender/open_id in the pending key before enabling wider group control.
- The local-model page stores pending controls in process memory, while Feishu persists them to runtime JSON. A shared pending-control store would make restart behavior and auditing more consistent.
- Query intent classification, control rewrite, and answer generation should be separately observable in logs so mistakes can be debugged without exposing secrets.
