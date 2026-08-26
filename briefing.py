"""The morning briefing. Run this one command and a real briefing arrives on
Walker's phone.

Fail soft: each data source is loaded independently, and any failure becomes a
plain line in the "not available" list rather than stopping the run. The
briefing still sends with whatever loaded.

No scheduling here yet — the 7:00 AM poll-then-brief job comes later.
"""

import sys
import traceback

import psycopg2
import requests

import apple_calendar
import bot
import brain
import db
import whoop

# Exceptions each source is known to raise. (Chunking and Telegram formatting
# live in bot.py — delivery is its responsibility, not the briefing's.) Anything outside these is reported
# as an unidentified failure rather than being blamed on the source's most
# likely cause — Jarvis must never assert a cause it hasn't verified.
DB_ERRORS = (psycopg2.Error,)
WHOOP_ERRORS = (requests.RequestException, psycopg2.Error, RuntimeError, KeyError, ValueError)
CALENDAR_ERRORS = (apple_calendar.CalendarError, requests.RequestException)

GOALS_UNAVAILABLE = (
    "(Walker's current goals could not be loaded from the database this "
    "morning — brief without assuming what they are.)"
)


def _record(unavailable, label, error, expected):
    """Append one honest line about a failure.

    Expected failures are named by their real exception type and message.
    Anything else is labelled explicitly as unidentified — we do not guess at a
    cause, because a confident wrong diagnosis is worse than an admitted
    unknown (it sends Walker off fixing the wrong thing)."""
    detail = f"{type(error).__name__}: {error}"
    if isinstance(error, expected):
        unavailable.append(f"{label} ({detail})")
    else:
        unavailable.append(f"{label} — failed for an unidentified reason ({detail})")
        traceback.print_exc()
    print(f"{label} unavailable — {detail}", file=sys.stderr)


def _load_goals(unavailable):
    try:
        db.ensure_goals()
        goals = db.get_goals()
    except Exception as e:
        _record(unavailable, "Walker's goals list", e, DB_ERRORS)
        return GOALS_UNAVAILABLE

    if not goals:
        unavailable.append("Walker's goals list (the goals table is empty)")
        return GOALS_UNAVAILABLE
    return goals


def _describe_state(label, state):
    """WHOOP's non-scored states are normal conditions, not errors — the strap
    simply hasn't synced. Say which it is in plain English."""
    if state == "not_synced":
        return f"{label} (the strap hasn't synced with WHOOP yet)"
    return f"{label} (WHOOP reports {state.lower().replace('_', ' ')})"


def _load_whoop(unavailable):
    """(cycle_score, recovery_score, sleep_score) — any of them None if that
    piece didn't load. Each fetch is isolated so one failure doesn't cost the
    others, and a failed fetch is never reported as 'not synced yet': that is a
    claim about the strap, and we only make it when WHOOP actually said so."""
    cycle = None
    cycle_fetched = False
    cycle_score = recovery_score = sleep_score = None

    try:
        cycle = whoop.get_today_cycle()
        cycle_fetched = True
        state, _ = whoop.get_today_strain(cycle)
        if state == "ok":
            cycle_score = cycle["score"]
        else:
            unavailable.append(_describe_state("Today's strain", state))
    except Exception as e:
        _record(unavailable, "Today's strain", e, WHOOP_ERRORS)

    if not cycle_fetched:
        # The cycle request itself failed, so we know nothing about recovery —
        # including whether the strap has synced.
        unavailable.append("Recovery (could not be checked — the cycle request above failed)")
    elif cycle is None:
        unavailable.append(_describe_state("Recovery", "not_synced"))
    else:
        try:
            state, recovery = whoop.get_today_recovery(cycle["id"])
            if state == "ok":
                recovery_score = recovery["score"]
            else:
                unavailable.append(_describe_state("Recovery", state))
        except Exception as e:
            _record(unavailable, "Recovery", e, WHOOP_ERRORS)

    try:
        state, sleep = whoop.get_today_sleep()
        if state == "ok":
            sleep_score = sleep["score"]
        else:
            unavailable.append(_describe_state("Last night's sleep", state))
    except Exception as e:
        _record(unavailable, "Last night's sleep", e, WHOOP_ERRORS)

    return cycle_score, recovery_score, sleep_score


def _load_calendar(unavailable):
    try:
        return apple_calendar.get_today_and_tomorrow()
    except apple_calendar.CalendarAuthError as e:
        # Only reached when CalDAV returned a verified 401/403. Per the build
        # brief, a genuine auth failure must be named plainly — Apple revokes
        # app-specific passwords automatically when the Apple ID password
        # changes. Any other calendar failure falls through to the branches
        # below and is NOT reported as a password problem.
        print(f"Calendar auth rejected — {e}", file=sys.stderr)
        unavailable.append(
            "The calendar — Apple Calendar rejected the credentials, so the "
            "app-specific password needs regenerating at appleid.apple.com."
        )
    except Exception as e:
        _record(unavailable, "The calendar", e, CALENDAR_ERRORS)
    return None


def main():
    unavailable = []

    goals = _load_goals(unavailable)
    cycle_score, recovery_score, sleep_score = _load_whoop(unavailable)
    events = _load_calendar(unavailable)

    system_prompt = brain.load_system_prompt(goals)
    user_message = brain.build_briefing_message(
        cycle_score, recovery_score, sleep_score, events, unavailable
    )

    print("--- data sent to Claude ---")
    print(user_message)
    print("---------------------------")

    briefing = brain.ask(system_prompt, user_message)

    print("--- briefing ---")
    print(briefing)
    print("----------------")

    bot.send_markdown(briefing)
    print("Briefing sent.")


if __name__ == "__main__":
    try:
        main()
    except brain.BrainError as e:
        # No reply means there is no briefing to send. Fail loudly rather than
        # inventing an in-character apology in source. Note the attribution:
        # this is a Claude-side failure and is never reported as a WHOOP or
        # calendar problem.
        print(f"FAILED — the Claude API call did not succeed: {e}", file=sys.stderr)
        print("No briefing was sent. WHOOP and the calendar are not implicated.", file=sys.stderr)
        sys.exit(1)
