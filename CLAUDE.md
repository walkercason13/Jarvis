# Jarvis — Project Instructions

## What this is

A personal AI assistant ("Jarvis") for one user, Walker. WHOOP biometrics +
Apple Calendar → Claude API (persona system prompt) → Telegram morning
briefing and evening debrief. Python 3.12, Postgres, hosted on Railway.
One user, no public surface.

## Read these before building anything

1. `jarvis-build-brief.md` — the architecture, stack, v1 scope, and daily flow.
   It is the source of truth. Do not substitute stack choices.
2. `jarvis-prompt.md` — the persona system prompt. It is loaded at runtime and
   sent with every Claude API call. Never hardcode persona text in source, and
   never edit this file unless Walker asks.
3. `.claude/skills/whoop-integration/` — mandatory rules for ALL WHOOP code.

## Build principles

1. **Incremental only.** One feature at a time, added to this same codebase.
   Build and fully test each piece before starting the next. Never wire two
   untested integrations together.
2. **Respect v1 scope.** The build brief lists what is NOT in v1. Do not build
   ahead, do not scaffold future features "while we're here."
3. **Secrets in environment variables, always.** Nothing sensitive in source or
   git history.
4. **Small modules, one responsibility each** (whoop.py, apple_calendar.py,
   bot.py, brain.py, briefing.py, debrief.py, db.py).
5. **Fail soft.** If an external API is down, the daily message still sends
   with whatever loaded, and Jarvis says plainly what's missing.
6. **After each feature ships, add one line to the changelog below** so future
   sessions know the current state of the app.

## Changelog

- WHOOP integration (`db.py`, `whoop.py`): OAuth 2.0 authorization-code flow
  (offline scope, all read scopes), rotating-refresh-token handling,
  reconnect-on-failure Postgres via `DATABASE_URL`. Fetches today's cycle
  (strain), recovery, and sleep from the v2 API, gating on `score_state ==
  SCORED` and treating a 404 on recovery as "not synced yet." Verified
  end-to-end with `whoop_test.py`: real recovery/sleep/strain print in the
  terminal after one-time browser approval, and a second run reuses the
  stored token without reopening the browser.
- Telegram bot (`bot.py`): standalone `send_message()` outbound path (for
  the future scheduled briefing/debrief jobs) plus a polling inbound path
  with `/start` and echo handlers, both gated by a `TELEGRAM_ALLOWED_USER_ID`
  allowlist that silently drops everyone else. Verified end-to-end:
  `send_message()` produced a real push notification, and `/start` +
  a plain-text message both worked over live polling. The allowlist's
  reject path is untested against a real second account — logic-verified
  only. `/status`, the "thinking" ack, and Railway/webhook deployment are
  deferred until brain.py and the scheduler exist.
- Apple Calendar (`apple_calendar.py`, read-only): CalDAV against
  `caldav.icloud.com` via `APPLE_ID`/`APPLE_APP_PASSWORD`, no OAuth. Named
  `apple_calendar.py` rather than the build brief's `calendar.py` to avoid
  shadowing Python's stdlib `calendar` module. `list_calendars()` for
  discovery, `get_today_and_tomorrow()` reads events from the calendars
  named in `CALENDAR_NAMES` (currently `Home,Work`), gated in
  `America/New_York`. Auth failures raise `CalendarAuthError` with a plain
  diagnostic rather than failing silently, per the build brief's
  app-specific-password-revocation warning. Verified end-to-end with
  `calendar_test.py` against real account data (confirmed correct via a raw
  unfiltered object dump, not just the date-range search). Known gap: the
  calendar with Walker's actual class schedule is a subscribed `.ics`/webcal
  feed, which CalDAV cannot reach — deferred, not built.
