# Jarvis — Project Instructions

## What this is

A personal AI assistant ("Jarvis") for one user, Walker. WHOOP biometrics +
Google Calendar → Claude API (persona system prompt) → Telegram morning
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
4. **Small modules, one responsibility each** (whoop.py, gcal.py, bot.py,
   brain.py, briefing.py, debrief.py, db.py).
5. **Fail soft.** If an external API is down, the daily message still sends
   with whatever loaded, and Jarvis says plainly what's missing.
6. **After each feature ships, add one line to the changelog below** so future
   sessions know the current state of the app.

## Changelog

- (nothing built yet — v1 spine is next)
