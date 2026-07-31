# Jarvis — Build Brief for Claude Code

## What this is
A personal AI assistant ("Jarvis") for one user, Walker. It reads his WHOOP biometrics and Google Calendar, reasons over them with the Claude API using a persona system prompt, and delivers a morning briefing and evening debrief via a Telegram bot. Runs 24/7 on Railway. One user, no auth beyond API credentials, no public surface.

## Stack (do not substitute)
- **Language:** Python 3.12
- **Delivery:** Telegram bot (python-telegram-bot)
- **Database:** Postgres (Railway-provisioned)
- **Brain:** Anthropic Claude API — system prompt loaded from `jarvis-prompt.md`, never hardcoded in source
- **Data sources:** WHOOP API v2, Google Calendar API
- **Hosting:** Railway, with scheduled jobs for the two daily messages
- **Timezone:** America/New_York for all schedules

## V1 scope (build ONLY this)
1. WHOOP OAuth + daily fetch of recovery, sleep, and strain into Postgres
2. Google Calendar read (today + tomorrow's events)
3. Telegram bot that can send and receive messages
4. **Morning briefing (7:00 AM, poll-then-brief):** WHOOP + calendar + current goals → Claude API with system prompt → one Telegram message. Sends when WHOOP data has synced, not blindly at 7:00 — see Daily flow.
5. **Evening debrief (9:00 PM):** finalized strain + today's data → Claude API → strain summary + two journaling prompts; store Walker's replies in a journal table
6. **Goals management:** goals live in a `goals` table and are injected into the system prompt at runtime (the `{{CURRENT_GOALS}}` placeholder). Walker can update goals by messaging the bot in plain English; Jarvis confirms and the table updates.

## NOT in v1 (do not build yet)
Calorie tracking, ElevenLabs voice notes, deadline tracking, sickness early-warning, game-day mode, bloodwork, screen time, PWA. These come later, one at a time, added to this same codebase.

## Daily flow
- **7:00 AM job — poll-then-brief:** WHOOP data only uploads once the strap syncs with Walker's phone, and he doesn't sleep with his phone. So the morning job must NOT assume data exists at 7:00. Logic: at 7:00, check whether today's recovery/sleep records exist yet. If yes → assemble prompt (persona + goals + data) → Claude API → send briefing. If no → retry every 15 minutes until the data appears, then brief immediately. Hard fallback at 10:30 AM: send the briefing anyway with calendar + goals, with Jarvis noting plainly that the strap hasn't synced yet ("I'm flying blind on biometrics until you find your phone, sir"). Never send twice.
- **9:00 PM job:** fetch strain (daily totals finalize after midnight, so evening strain is "so far today" — label it that way) → Claude API → send debrief → listen for journal replies
- **Anytime:** incoming Telegram messages route to Claude API with persona + goals + recent data as context, so Walker can ask questions or change goals mid-day

## Critical rules
- Follow the `whoop-integration` project skill for ALL WHOOP work — especially rotating refresh tokens (save the new refresh token in the same transaction as the access token) and v2/UUID endpoints only
- All secrets in environment variables: `ANTHROPIC_API_KEY`, `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`, `TELEGRAM_BOT_TOKEN`, `GOOGLE_*`, `DATABASE_URL`
- Incremental builds: WHOOP first, test with a real recovery score printing; then Calendar, test; then Telegram, test; then the brain. Never wire the next piece until the current one passes its test
- Small modules, one responsibility each (whoop.py, gcal.py, bot.py, brain.py, briefing.py, debrief.py, db.py)
- If an external API fails, the message still sends — Jarvis briefs with whatever data loaded and says plainly what's missing
