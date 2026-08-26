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
- Morning briefing (`db.py`, `brain.py`, `briefing.py`, `set_goals.py`): a
  single-row `goals` table seeded on first run and editable via
  `set_goals.py`; `brain.py` loads `jarvis-prompt.md`, substitutes
  `{{CURRENT_GOALS}}` from that table, assembles today's WHOOP + calendar data
  into a user message, and calls the Claude API with `CLAUDE_MODEL` (no
  model-specific params, so the call stays valid if the model changes);
  `briefing.py` wires it together and sends via `bot.send_markdown`. Fail
  soft: each source loads
  independently and any failure becomes a plain "not available" line naming
  its own real exception type and message. Diagnoses are never guessed — the
  "regenerate the app-specific password" claim fires only on a verified
  CalDAV 401/403 (`CalendarAuthError`, now split from the new generic
  `CalendarError`), a failed cycle request is never reported as "the strap
  hasn't synced," and unrecognized errors are labelled as unidentified rather
  than blamed on the nearest plausible cause. A Claude API failure (bad key,
  billing, rate limit) is reported as Claude-side, sends nothing, and exits 1
  rather than hardcoding an in-character apology. Verified end-to-end:
  `python briefing.py` put a real briefing on Walker's phone from live WHOOP
  data, and `briefing_test.py` passes six diagnosis-accuracy checks plus a
  fail-soft delivery run. Appended a calendar rule to `jarvis-prompt.md`: the
  full class schedule is never recited, only the first commitment, work due,
  unusual events, and collisions. Not built: scheduling/the 7:00 AM
  poll-then-brief loop, the evening debrief, plain-English goal updates by
  message, `/status`, deployment. Known gap: `Home` and `Work` are the only
  CalDAV-reachable calendars and both are currently empty, so the calendar
  half of the briefing has no content until the subscribed `.ics` schedule is
  reachable.
- Telegram formatting (`telegram_format.py`, `bot.py`): Claude writes standard
  Markdown, which Telegram renders as literal `**asterisks**` and `#` hashes.
  `telegram_format.to_html()` converts it deterministically — rather than
  relying on the model to remember a formatting rule — into the tag subset
  Telegram accepts: headings and bold to `<b>`, italics to `<i>`, `>` quotes
  to `<blockquote>`, backticks to `<code>`/`<pre>`, links to `<a>`, bullet
  markers to `•`, and horizontal rules dropped (Telegram has no equivalent;
  the blank lines already separate sections). Delivery now lives entirely in
  `bot.py`: `send_markdown()` chunks the Markdown *before* converting, so a
  chunk boundary can never land inside a tag or a blockquote, and falls back
  to unformatted text on a Telegram `BadRequest` so a formatting bug never
  costs the briefing itself. `send_message()` takes an optional `parse_mode`.
  Verified: `telegram_format_test.py` passes 19 checks on real briefing output
  (nothing Markdown-ish survives, tags balanced, only supported tags), a real
  formatted briefing rendered correctly on the phone, and deliberately
  malformed HTML triggered the plain-text fallback instead of losing the
  message.
