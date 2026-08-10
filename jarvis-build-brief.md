# Jarvis — Build Brief for Claude Code

## What this is
A personal AI assistant ("Jarvis") for one user, Walker. It reads his WHOOP biometrics and Apple Calendar, reasons over them with the Claude API using a persona system prompt, and delivers a morning briefing and evening debrief via a Telegram bot. Runs 24/7 on Railway. One user, no auth beyond API credentials, no public surface.

## Stack (do not substitute)
- **Language:** Python 3.12
- **Delivery:** Telegram bot (python-telegram-bot)
- **Database:** Postgres (Railway-provisioned)
- **Brain:** Anthropic Claude API — system prompt loaded from `jarvis-prompt.md`, never hardcoded in source. Model set via `CLAUDE_MODEL` env var (currently Sonnet), never hardcoded
- **Data sources:** WHOOP API v2, Apple Calendar via CalDAV (`caldav.icloud.com`)
- **Hosting:** Railway — ONE always-on worker service, not cron jobs (see Scheduling)
- **Timezone:** America/New_York for all schedules

## Build status
1. **WHOOP integration — DONE.** `db.py` (reconnect-tolerant Postgres), `whoop.py` (OAuth with all six read scopes, rotating refresh tokens, recovery/sleep/strain fetch), `whoop_test.py`. Verified end-to-end with real data and confirmed token reuse on second run.
2. **Telegram bot — NEXT.**
3. Apple Calendar read.
4. Morning briefing + evening debrief (the brain).
5. Goals management.
6. Deploy to Railway.

## V1 scope (build ONLY this)
1. ~~WHOOP OAuth + daily fetch of recovery, sleep, and strain into Postgres~~ (done)
2. Telegram bot that can send and receive messages, **restricted to Walker's Telegram user ID only** — every incoming message checks the sender ID against an allowlist from `TELEGRAM_ALLOWED_USER_ID` and silently ignores everyone else. The bot username is publicly discoverable; without this check, strangers can burn API credit and read Walker's biometrics.
3. Apple Calendar read (today + tomorrow's events)
4. **Morning briefing (7:00 AM, poll-then-brief):** WHOOP + calendar + current goals → Claude API with system prompt → one Telegram message. Sends when WHOOP data has synced, not blindly at 7:00 — see Daily flow.
5. **Evening debrief (9:00 PM):** finalized strain + today's data → Claude API → strain summary + two journaling prompts; store Walker's replies in a journal table
6. **Goals management:** goals live in a `goals` table and are injected into the system prompt at runtime (the `{{CURRENT_GOALS}}` placeholder). Walker can update goals by messaging the bot in plain English; Jarvis confirms and the table updates.
7. **`/status` command:** replies with system health — last WHOOP sync time, database connection state, next scheduled job. Walker must be able to check Jarvis is alive from his phone without touching a computer.

## NOT in v1 (do not build yet)
Calorie tracking, voice notes (input or output), deadline tracking, sickness early-warning, game-day mode, bloodwork, screen time, PWA, WHOOP webhooks. These come later, one at a time, added to this same codebase.

## Apple Calendar (CalDAV) rules
- Connect to `caldav.icloud.com` using `APPLE_ID` and `APPLE_APP_PASSWORD` (an app-specific password) from environment variables. There is NO OAuth, no browser approval, and no refresh token — this is deliberate, so Jarvis never needs a laptop to re-authenticate.
- On first build, list all calendars found on the account and print their names so Walker can confirm which ones matter. Store the chosen calendar names in an env var or a small config table — do not hardcode.
- Read-only. Jarvis never creates, edits, or deletes events in v1.
- **Known failure mode:** changing or resetting the primary Apple ID password automatically revokes ALL app-specific passwords. When CalDAV auth fails, Jarvis must say so plainly in its next message ("I've lost access to your calendar, sir — the app-specific password needs regenerating") rather than failing silently or omitting the schedule with no explanation.

## Scheduling architecture
- **ONE always-on Railway worker**, not Railway cron jobs. Railway cron is designed for short-lived tasks that exit promptly; Jarvis is a long-running process that must also listen for incoming Telegram messages continuously.
- Schedules live INSIDE the Python process (python-telegram-bot's JobQueue or APScheduler), explicitly pinned to `America/New_York`. Do not rely on the host's clock or UTC-fixed times — a UTC-pinned 7:00 AM drifts by an hour across daylight saving.

## Daily flow
- **7:00 AM job — poll-then-brief:** WHOOP data only uploads once the strap syncs with Walker's phone, and he doesn't sleep with his phone. So the morning job must NOT assume data exists at 7:00. Logic: at 7:00, check whether today's recovery/sleep records exist AND have `score_state == "SCORED"`. A 404 or `PENDING_SCORE` means "not synced yet," which is a normal condition, not an error. If scored data exists → assemble prompt (persona + goals + data) → Claude API → send briefing. If not → retry every 15 minutes until it appears, then brief immediately. Hard fallback at 10:30 AM: send the briefing anyway with calendar + goals, with Jarvis noting plainly that the strap hasn't synced yet ("I'm flying blind on biometrics until you find your phone, sir"). Never send twice.
- **9:00 PM job:** fetch strain (daily totals finalize after midnight, so evening strain is "so far today" — label it that way) → Claude API → send debrief → listen for journal replies
- **Anytime:** incoming Telegram messages route to Claude API with persona + goals + recent data as context, so Walker can ask questions or change goals mid-day

## Critical rules
- Follow the `whoop-integration` project skill for ALL WHOOP work — especially rotating refresh tokens and v2/UUID endpoints only
- All secrets in environment variables: `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_ID`, `APPLE_ID`, `APPLE_APP_PASSWORD`, `DATABASE_URL`
- Incremental builds: build and fully test each piece before wiring the next. Never wire two untested integrations together
- Small modules, one responsibility each (whoop.py, calendar.py, bot.py, brain.py, briefing.py, debrief.py, db.py)
- If an external API fails, the message still sends — Jarvis briefs with whatever data loaded and says plainly what's missing
- **Send a "thinking" acknowledgment** when Walker messages the bot, before the Claude API call returns. A silent 10-second gap reads as a dead bot.
- **Telegram allows only ONE polling connection per bot token.** A locally running bot and a deployed bot will fight, producing `Conflict: terminated by other getUpdates request` (409). Always stop the local instance before deploying.

## Deployment notes (Wednesday)
- Local dev uses `DATABASE_PUBLIC_URL` (Railway TCP proxy: `sakura.proxy.rlwy.net:28811`). The deployed worker uses the INTERNAL address `postgres.railway.internal:5432` — set that in Railway's own environment variables, not copied from `.env`
- Rotate the Postgres password and the Apple app-specific password before going live
