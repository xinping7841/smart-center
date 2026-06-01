# Feishu Natural Language Design Review

Last updated: 2026-06-01

## Current State

Smart Center already has the core pieces for Feishu natural-language operations:

- `services/feishu_bot.py` is the Feishu long-connection adapter. It strips mentions, handles text commands, runs scheduled pushes, stores pending controls, sends confirmation cards, and calls Smart Center HTTP APIs.
- `services/control_intent_router.py` is the deterministic safety router. It chooses the module before command construction and blocks ambiguous bare-channel commands.
- `services/control_model_translator.py` lets a local model rewrite fuzzy user text into a safer standard Chinese control phrase. The rewritten text is treated as untrusted and must be routed again.
- `services/device_aliases.py` builds aliases from `CONFIG`, including cabinets, lights, HVAC, projectors, screens, sequencers, custom protocol devices, sensors, current collector, door, and proxy.
- `api/local_model.py` exposes the local-model page, OpenAI-compatible chat, control dry-run/confirm, and runtime knowledge export.
- `scripts/export_local_model_training.py` exports runtime knowledge. It now also exports source-code/module knowledge through `scripts/export_code_knowledge.py`.

The deployed behavior is more capable than older docs imply: Feishu can execute low-risk controls directly and requires confirmation for strong-current cabinets, sequencers, and inferred targets.

## Existing Flow

1. Feishu message enters `FeishuBot.handle_message_event`.
2. `dispatch_command` first checks control/cancel/confirm text.
3. `_dispatch_control_command` detects control intent with deterministic keywords.
4. `LocalSmartCenterClient.resolve_control_command_with_translator` uses:
   - feedback memory from `SMART_CENTER_RUNTIME_DIR/control_feedback.jsonl`;
   - `ControlIntentRouter`;
   - optional local-model rewrite;
   - conservative fallback inference.
5. The resolved command contains `type`, `risk`, `label`, `path`, `payload`, `action`, and confidence metadata.
6. High-risk or inferred commands are stored as pending controls. Confirmation cards or text replies execute `_execute_pending_control`.
7. Execution uses existing Smart Center HTTP APIs such as `/api/light/control`, `/api/hvac/control`, `/api/set`, `/api/sequencer/control`, `/api/wake/<mac>`, and `/api/control_center/execute`.

## Main Problems

1. Feishu identity and Smart Center identity are not clearly separated.

   The bot calls local HTTP APIs with app credentials at the Feishu side, but device APIs are designed around Smart Center session permissions. This can become ambiguous if production auth defaults change or if auto-login grants broad access.

2. Low-risk direct execution may still be too permissive for group chat.

   A phrase like "关空调" or "开投影" can affect the venue even though it is not classified as strong-current. For the first production phase, Feishu should probably require confirmation for every control, then later allow direct execution only for a reviewed low-risk allowlist.

3. Pending controls are keyed by chat, not sender.

   In a group, a second user can overwrite or confirm another user's pending request. Pending keys should include `chat_id` plus sender/open_id, and cards should reject mismatched users.

4. Query, rewrite, and execution telemetry is not complete enough.

   Logs should record the original text, detected intent, model rewrite, route reason, command summary, risk, confirmation outcome, and API result. The current feedback memory helps learning, but it is not a full audit trail.

5. Two confirmation stores exist.

   Feishu persists pending controls to runtime JSON. The local-model page stores pending controls in process memory. A shared pending-control service would make restart behavior, TTL cleanup, audit, and UI/Feishu parity cleaner.

6. Model knowledge is split across runtime facts, docs, code comments, and config.

   Existing runtime export is good, but the model also needs source-code navigation knowledge: routes, permissions, module boundaries, risk comments, and design notes. That is now addressed by `scripts/export_code_knowledge.py`, but the knowledge proxy/RAG ingestion still needs to consume it.

## Recommended Target Design

Keep the system in four layers:

- Feishu adapter: message receive/send, cards, sender identity, pending-control UX.
- Intent and retrieval: deterministic intent rules first, optional local-model classify/rewrite, RAG over runtime and code knowledge.
- Tool/router: read-only API allowlist for queries; controlled-action resolver for controls.
- Execution: existing Smart Center APIs with explicit service identity, permission policy, operation locks, audit logs, risk classification, and confirmation.

The local model should never output an executable HTTP path or payload as the final authority. It may output a structured proposal such as:

```json
{"intent":"control_request","module":"light","target":"一号厅前言墙灯","action":"off","confidence":0.82}
```

The backend must then resolve that proposal through aliases, status APIs, permission rules, and confirmation policy.

## Phased Optimization Plan

1. Safety-first Feishu control hardening:
   - Add explicit Feishu service identity or internal token for Smart Center API calls.
   - Key pending controls by chat and sender.
   - Require confirmation for all Feishu controls initially.
   - Log original text, resolved command summary, risk, confirmation, and result.

2. Knowledge/RAG ingestion:
   - Run `python scripts/export_local_model_training.py`.
   - Ingest `system_map_*.json`, `device_inventory_*.jsonl`, `control_capabilities_*.jsonl`, `knowledge_*.json`, `insights_*.jsonl`, `device_aliases_*.jsonl`, `query_intents_*.jsonl`, `control_intents_*.jsonl`, `nl_intent_examples_*.jsonl`, `code_system_map_*.json`, `module_cards_*.jsonl`, and `code_knowledge_*.jsonl`.
   - Use `full_code_context_*.jsonl` only for high-context periodic refresh on the 3090 local model host or for RAG indexing.
   - Prefer RAG for current state and code navigation; reserve fine-tuning for reviewed examples.

3. Better intent contract:
   - Use a strict JSON schema for model intent output.
   - Separate query classification, control rewrite, and answer generation prompts.
   - Add dry-run tests for common phrases and known dangerous ambiguous cases.

4. Shared control orchestration:
   - Move pending controls and feedback into a shared service used by Feishu and `/api/local-model/control/*`.
   - Add a "proposal -> confirmation -> execute -> verify state" state machine.
   - Add post-execution readback where supported.

5. Operator experience:
   - Reply with concise evidence for queries.
   - For controls, always show target, action, risk, current state when available, and how to cancel.
   - When ambiguous, return candidates instead of guessing.

## Knowledge Export

Production code was backed up before this design/export change. Runtime and code knowledge can now be generated together:

```bash
python scripts/export_local_model_training.py
```

Use `--skip-code-knowledge` only if you want the previous runtime-only export behavior.

For the 3090 high-context host, the daily systemd export can also run:

```bash
python scripts/refresh_local_model_system_summary.py --max-input-chars 160000
```

The generated `system_summary_*.json` is an operator/model-maintenance artifact. It does not authorize control. Feishu control still depends on the explicit Feishu control switch, sender identity, confirmation policy, permissions, and Smart Center execution APIs.
