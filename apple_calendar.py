"""Apple Calendar access via CalDAV. Read-only: this module never creates,
edits, or deletes events. Named apple_calendar.py rather than calendar.py to
avoid shadowing Python's stdlib `calendar` module (see build brief note).
"""

import os
from datetime import datetime, timedelta

import caldav
import requests
from caldav.lib.error import AuthorizationError, DAVError
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

load_dotenv()

APPLE_ID = os.environ["APPLE_ID"]
APPLE_APP_PASSWORD = os.environ["APPLE_APP_PASSWORD"]
CALENDAR_NAMES = os.environ.get("CALENDAR_NAMES", "")

CALDAV_URL = "https://caldav.icloud.com/"
TZ = ZoneInfo("America/New_York")


class CalendarError(RuntimeError):
    """A calendar failure whose cause has NOT been identified as an auth
    problem — a network drop, an iCloud 5xx, a malformed response. Carries the
    underlying exception type and message so callers report what actually
    happened rather than guessing at a cause."""


class CalendarAuthError(CalendarError):
    """Raised ONLY when CalDAV genuinely rejects our credentials (a verified
    401/403). Apple silently revokes ALL app-specific passwords when the
    primary Apple ID password is changed or reset, so a real auth failure must
    never be swallowed or treated as 'no events today.' Equally, an unrelated
    failure must never be reported as a revoked password — that sends Walker
    to regenerate a credential that was never the problem."""


def _auth_error(underlying):
    return CalendarAuthError(
        "Apple Calendar rejected the credentials — the app-specific password has "
        "been revoked or is wrong. Apple revokes them automatically when the Apple "
        "ID password is changed or reset. Regenerate one at appleid.apple.com and "
        f"update APPLE_APP_PASSWORD in .env. ({type(underlying).__name__}: {underlying})"
    )


def _wrap(action, e):
    """Turn a CalDAV/network failure into the narrowest accurate error. Only a
    verified 401/403 becomes a CalendarAuthError."""
    if isinstance(e, AuthorizationError):
        return _auth_error(e)

    response = getattr(e, "response", None)
    status = getattr(response, "status_code", None)
    if status in (401, 403):
        return _auth_error(e)

    detail = f" (HTTP {status})" if status else ""
    return CalendarError(f"{action} failed{detail} — {type(e).__name__}: {e}")


def _client():
    try:
        client = caldav.DAVClient(
            url=CALDAV_URL,
            username=APPLE_ID,
            password=APPLE_APP_PASSWORD,
        )
        principal = client.get_principal()
    except (DAVError, requests.RequestException) as e:
        raise _wrap("Connecting to Apple Calendar", e) from e
    return principal


def list_calendars():
    """Every calendar name found on the account — the discovery step for
    choosing what goes in CALENDAR_NAMES."""
    principal = _client()
    try:
        return [cal.name for cal in principal.get_calendars()]
    except (DAVError, requests.RequestException) as e:
        raise _wrap("Listing the calendars on the account", e) from e


def _selected_calendars(principal):
    if not CALENDAR_NAMES.strip():
        raise RuntimeError(
            "CALENDAR_NAMES is not set. Run list_calendars() first, pick the "
            "calendars that matter, and set CALENDAR_NAMES=name1,name2 in .env."
        )

    wanted = [name.strip() for name in CALENDAR_NAMES.split(",") if name.strip()]

    try:
        all_calendars = {cal.name: cal for cal in principal.get_calendars()}
    except (DAVError, requests.RequestException) as e:
        raise _wrap("Listing the calendars on the account", e) from e

    selected = []
    for name in wanted:
        if name not in all_calendars:
            raise RuntimeError(
                f"CALENDAR_NAMES includes '{name}', but no calendar with that name "
                f"exists on the account. Found: {list(all_calendars)}"
            )
        selected.append(all_calendars[name])
    return selected


def get_events(start, end):
    """Events across the selected calendars between start and end
    (timezone-aware datetimes), sorted by start time."""
    principal = _client()
    events = []

    for cal in _selected_calendars(principal):
        try:
            found = cal.search(start=start, end=end, event=True, expand=True)
        except (DAVError, requests.RequestException) as e:
            raise _wrap(f"Reading the '{cal.name}' calendar", e) from e

        for obj in found:
            comp = obj.get_icalendar_component()
            events.append(
                {
                    "summary": str(comp.get("SUMMARY", "(no title)")),
                    "start": comp["DTSTART"].dt,
                    "end": comp["DTEND"].dt if "DTEND" in comp else None,
                    "location": str(comp["LOCATION"]) if "LOCATION" in comp else None,
                }
            )

    events.sort(key=lambda e: e["start"])
    return events


def get_today_and_tomorrow():
    """Events from the start of today through the end of tomorrow, in
    America/New_York."""
    today_start = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_end = today_start + timedelta(days=2)
    return get_events(today_start, tomorrow_end)
