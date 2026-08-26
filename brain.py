"""The Claude API layer. One responsibility: load the persona system prompt,
inject the current goals, assemble today's data into a user message, and return
Claude's reply.

Persona text lives in jarvis-prompt.md and is never hardcoded here. The model
comes from CLAUDE_MODEL and is never hardcoded either — so this module passes
no model-specific parameters (no thinking config, no sampling params), which
keeps the call valid whatever CLAUDE_MODEL is set to.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = os.environ["CLAUDE_MODEL"]
PROMPT_PATH = Path(__file__).parent / "jarvis-prompt.md"
GOALS_PLACEHOLDER = "{{CURRENT_GOALS}}"
TZ = ZoneInfo("America/New_York")
MAX_TOKENS = 1500


class BrainError(RuntimeError):
    """Raised when the Claude API call fails or returns nothing usable. There
    is no fail-soft path here: without a reply there is no briefing to send,
    and inventing one in source would mean hardcoding persona text."""


def _api_detail(error):
    """HTTP status, the API's own error type, and its message — so a Claude-side
    failure is always reported as what it actually was (a billing problem, a bad
    model ID, an overload) and never guessed at."""
    parts = [f"HTTP {error.status_code}"]
    api_type = getattr(error, "type", None)
    if api_type:
        parts.append(str(api_type))
    parts.append(error.message)
    return " | ".join(parts)


def load_system_prompt(goals_text):
    """The persona prompt with {{CURRENT_GOALS}} replaced by the goals table's
    text. Raises if the placeholder has gone missing — silently briefing with
    no goals would defeat the point of the whole file."""
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    if GOALS_PLACEHOLDER not in prompt:
        raise BrainError(
            f"{PROMPT_PATH.name} no longer contains the {GOALS_PLACEHOLDER} "
            "placeholder — goals cannot be injected."
        )
    return prompt.replace(GOALS_PLACEHOLDER, goals_text)


def _hours_minutes(millis):
    total_minutes = round(millis / 60000)
    return f"{total_minutes // 60}h {total_minutes % 60:02d}m"


def _whoop_lines(cycle_score, recovery_score, sleep_score):
    """Every field read with .get() so a shape change in WHOOP's response
    drops one line instead of killing the briefing."""
    lines = []

    if recovery_score:
        if recovery_score.get("recovery_score") is not None:
            lines.append(f"- Recovery: {recovery_score['recovery_score']:.0f}%")
        if recovery_score.get("hrv_rmssd_milli") is not None:
            lines.append(f"- HRV (RMSSD): {recovery_score['hrv_rmssd_milli']:.1f} ms")
        if recovery_score.get("resting_heart_rate") is not None:
            lines.append(f"- Resting heart rate: {recovery_score['resting_heart_rate']:.0f} bpm")
        if recovery_score.get("spo2_percentage") is not None:
            lines.append(f"- Blood oxygen: {recovery_score['spo2_percentage']:.1f}%")
        if recovery_score.get("skin_temp_celsius") is not None:
            lines.append(f"- Skin temperature: {recovery_score['skin_temp_celsius']:.1f} °C")
        if recovery_score.get("user_calibrating"):
            lines.append("- Note: WHOOP still reports this account as calibrating.")

    if sleep_score:
        if sleep_score.get("sleep_performance_percentage") is not None:
            lines.append(f"- Sleep performance: {sleep_score['sleep_performance_percentage']:.0f}%")

        stages = sleep_score.get("stage_summary") or {}
        in_bed = stages.get("total_in_bed_time_milli")
        awake = stages.get("total_awake_time_milli")
        if in_bed is not None:
            lines.append(f"- Time in bed: {_hours_minutes(in_bed)}")
            if awake is not None:
                lines.append(f"- Actual sleep: {_hours_minutes(in_bed - awake)}")
        if stages.get("total_slow_wave_sleep_time_milli") is not None:
            lines.append(f"- Deep (SWS) sleep: {_hours_minutes(stages['total_slow_wave_sleep_time_milli'])}")
        if stages.get("total_rem_sleep_time_milli") is not None:
            lines.append(f"- REM sleep: {_hours_minutes(stages['total_rem_sleep_time_milli'])}")
        if stages.get("disturbance_count") is not None:
            lines.append(f"- Disturbances: {stages['disturbance_count']}")

        needed = sleep_score.get("sleep_needed") or {}
        if needed.get("baseline_milli") is not None:
            lines.append(f"- Baseline sleep need: {_hours_minutes(needed['baseline_milli'])}")
        if needed.get("need_from_sleep_debt_milli") is not None:
            lines.append(f"- Additional need from sleep debt: {_hours_minutes(needed['need_from_sleep_debt_milli'])}")

        if sleep_score.get("respiratory_rate") is not None:
            lines.append(f"- Respiratory rate: {sleep_score['respiratory_rate']:.1f} breaths/min")
        if sleep_score.get("sleep_consistency_percentage") is not None:
            lines.append(f"- Sleep consistency: {sleep_score['sleep_consistency_percentage']:.0f}%")
        if sleep_score.get("sleep_efficiency_percentage") is not None:
            lines.append(f"- Sleep efficiency: {sleep_score['sleep_efficiency_percentage']:.0f}%")

    if cycle_score:
        if cycle_score.get("strain") is not None:
            lines.append(f"- Strain so far today: {cycle_score['strain']:.1f}")
        if cycle_score.get("average_heart_rate") is not None:
            lines.append(f"- Average heart rate so far: {cycle_score['average_heart_rate']} bpm")
        if cycle_score.get("max_heart_rate") is not None:
            lines.append(f"- Max heart rate so far: {cycle_score['max_heart_rate']} bpm")

    return lines


def _event_line(event):
    start, end = event["start"], event["end"]

    # All-day events come back as date objects rather than datetimes.
    if isinstance(start, datetime):
        when = start.astimezone(TZ).strftime("%-I:%M %p")
        if isinstance(end, datetime):
            when += f"–{end.astimezone(TZ).strftime('%-I:%M %p')}"
    else:
        when = "all day"

    line = f"- {when}: {event['summary']}"
    if event.get("location"):
        line += f" ({event['location']})"
    return line


def _calendar_section(heading, events, day):
    lines = [heading]
    for event in events:
        start = event["start"]
        event_day = start.astimezone(TZ).date() if isinstance(start, datetime) else start
        if event_day == day:
            lines.append(_event_line(event))
    if len(lines) == 1:
        lines.append("- (nothing on the calendar)")
    return lines


def build_briefing_message(cycle_score, recovery_score, sleep_score, events, unavailable):
    """The user message for the morning briefing: today's date, whatever WHOOP
    and calendar data loaded, and a plain statement of anything that didn't."""
    today = datetime.now(TZ).date()
    tomorrow = today + timedelta(days=1)

    parts = [f"MORNING BRIEFING REQUEST — {today.strftime('%A, %B %-d, %Y')}", ""]

    whoop_lines = _whoop_lines(cycle_score, recovery_score, sleep_score)
    parts.append("WHOOP DATA")
    parts.extend(whoop_lines if whoop_lines else ["- (no WHOOP data loaded)"])
    parts.append("")

    if events is None:
        parts.extend(["CALENDAR", "- (no calendar data loaded)", ""])
    else:
        parts.extend(_calendar_section(f"TODAY'S CALENDAR ({today.strftime('%A, %B %-d')})", events, today))
        parts.append("")
        parts.extend(_calendar_section(f"TOMORROW'S CALENDAR ({tomorrow.strftime('%A, %B %-d')})", events, tomorrow))
        parts.append("")

    if unavailable:
        parts.append("NOT AVAILABLE THIS MORNING")
        parts.extend(f"- {item}" for item in unavailable)
        parts.append("")

    parts.append(
        "Deliver the morning briefing in the format defined in your instructions. "
        "Do not invent data. If anything is listed as not available above, say so "
        "plainly and brief with what you have."
    )
    return "\n".join(parts)


def ask(system_prompt, user_message):
    """Send one message to Claude and return its text. Raises BrainError on any
    failure — the caller decides what that means."""
    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.AuthenticationError as e:
        raise BrainError(f"Claude API rejected ANTHROPIC_API_KEY: {_api_detail(e)}") from e
    except anthropic.PermissionDeniedError as e:
        raise BrainError(
            "Claude API denied this request — check the account's billing and "
            f"API key permissions: {_api_detail(e)}"
        ) from e
    except anthropic.NotFoundError as e:
        raise BrainError(f"CLAUDE_MODEL '{MODEL}' was not found: {_api_detail(e)}") from e
    except anthropic.RateLimitError as e:
        raise BrainError(f"Claude API rate limit hit: {_api_detail(e)}") from e
    except anthropic.BadRequestError as e:
        raise BrainError(f"Claude API rejected the request: {_api_detail(e)}") from e
    except anthropic.APIConnectionError as e:
        raise BrainError(f"Could not reach the Claude API ({type(e).__name__}): {e}") from e
    except anthropic.APIStatusError as e:
        raise BrainError(f"Claude API call failed: {_api_detail(e)}") from e

    if response.stop_reason == "refusal":
        raise BrainError("Claude declined to answer this request.")

    text = "\n".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise BrainError(f"Claude returned no text (stop_reason: {response.stop_reason}).")
    if response.stop_reason == "max_tokens":
        print(f"Warning: reply hit the {MAX_TOKENS}-token cap and may be cut off.")

    return text
