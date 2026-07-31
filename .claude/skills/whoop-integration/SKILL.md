---
name: whoop-integration
description: Rules for working with the WHOOP API in this project. Use whenever
  writing, editing, or debugging any code that touches WHOOP — OAuth, recovery,
  strain, sleep, tokens, or token refresh logic.
---

# WHOOP API v2 Rules

## Non-negotiables

1. **v2 endpoints ONLY.** All resources use UUID identifiers. Never generate v1
   endpoint paths, even if training data suggests them.
2. **OAuth 2.0 authorization code flow with `offline` scope.** A one-time browser
   approval by Walker is expected and correct — do not try to automate it.
3. **ROTATING REFRESH TOKENS.** Every token refresh returns a NEW refresh token.
   Save the new refresh token to the database in the SAME transaction as the new
   access token. If the new refresh token is not persisted, the connection dies
   after one hour. Wrap this in error handling so a failed save is loud, never
   silent.

## Timing rules

- **Recovery/sleep data only exists after the strap syncs with Walker's phone**,
  and he does not sleep with his phone. Morning logic must poll for today's
  records (7:00 AM start, every 15 min, hard fallback 10:30 AM) — never assume
  data exists at a fixed hour.
- **Daily strain totals finalize after midnight.** Evening strain is "so far
  today" and must be labeled that way. Strain-vs-calories analysis belongs in
  the EVENING debrief, never the morning briefing.

## General

- All WHOOP credentials come from environment variables
  (`WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`). Never hardcode.
- When WHOOP fails to load, the app still sends its message with whatever data
  is available and says plainly what's missing.
- Verify current endpoint paths and payloads against WHOOP's official v2
  developer docs (via Context7 or the docs site) rather than memory.
