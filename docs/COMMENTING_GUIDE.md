# Commenting Guide

Last updated: 2026-05-22

Comments should help future humans and local AI understand module boundaries and operational risk. They should not narrate obvious code.

## Add Comments For

- Module ownership and what belongs elsewhere.
- Physical device control side effects.
- Polling/cache freshness rules.
- Legacy route or payload compatibility.
- Generated code templates, especially Windows Agent and deploy scripts.
- Concurrency locks and hardware timing delays.

## Avoid Comments For

- Simple assignments.
- Repeating the function name in prose.
- Temporary guesses that will become stale.
- Large commented-out code blocks.

## Module Header Template

```python
# Module role: short sentence.
# Boundaries: what this file owns; what should stay in service/core modules.
# Compatibility: routes or payload fields that external clients rely on.
```

## Function Comment Template

```python
# Keep this route thin: it preserves the public payload and delegates expensive work.
```

## AI Marker Template

Use normal comments, not special syntax, so tools can read them everywhere:

```python
# AI map: server_monitor.agent_generation. Bump AGENT_VERSION when editing this template.
```
