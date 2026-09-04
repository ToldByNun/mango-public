# Playbooks

Procedural notes: **when X happens, do these steps** — so you do not re-explain login/nav/setup every chat.

## Where to put them

| Location | Purpose |
|----------|---------|
| `playbooks/` (this folder) | Shared / non-secret examples in the repo |
| `~/.mango/playbooks/` | **Your** real workflows (wins over repo for same filename) |
| `MANGO_PLAYBOOKS_DIR` | Optional override directory |

## File format

```markdown
---
name: short-id
triggers: login, playwright, example.com, auth
---

# Human title

## When
Describe the situation that should load this playbook.

## Steps
1. First action
2. Second action
3. …

## Secrets
- Prefer env vars (`SITE_USER`, `SITE_PASS`) or ask the user once.
- Never invent passwords. Never commit real credentials here.
```

## Agent tool

`lookup_playbook` — call with keywords from the goal before inventing multi-step external workflows.
