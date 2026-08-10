"""Apple Calendar access via CalDAV. Read-only: this module never creates,
edits, or deletes events. Named apple_calendar.py rather than calendar.py to
avoid shadowing Python's stdlib `calendar` module (see build brief note).
"""

import os
from datetime import datetime, timedelta

import caldav
from caldav.lib.error import DAVError
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

load_dotenv()

APPLE_ID = os.environ["APPLE_ID"]
APPLE_APP_PASSWORD = os.environ["APPLE_APP_PASSWORD"]
CALENDAR_NAMES = os.environ.get("CALENDAR_NAMES", "")

CALDAV_URL = "https://caldav.icloud.com/"
TZ = ZoneInfo("America/New_York")


class CalendarAuthError(RuntimeError):
    """Raised whenever CalDAV rejects our credentials. Apple silently
    revokes ALL app-specific passwords when the primary Apple ID password
    is changed or reset, so this must never be swallowed or treated as
    'no events today.'"""


def _client():
    try:
        client = caldav.DAVClient(
            url=CALDAV_URL,
            username=APPLE_ID,
            password=APPLE_APP_PASSWORD,
        )
        principal = client.get_principal()
    except DAVError as e:
        raise CalendarAuthError(
            "Apple Calendar authentication failed — the app-specific password may "
            "have been revoked. This happens automatically if the Apple ID password "
            "was changed or reset. Regenerate one at appleid.apple.com and update "
            f"APPLE_APP_PASSWORD in .env. (underlying error: {e})"
        ) from e
    return principal


def list_calendars():
    """Every calendar name found on the account — the discovery step for
    choosing what goes in CALENDAR_NAMES."""
    principal = _client()
    return [cal.name for cal in principal.get_calendars()]


def _selected_calendars(principal):
    if not CALENDAR_NAMES.strip():
        raise RuntimeError(
            "CALENDAR_NAMES is not set. Run list_calendars() first, pick the "
            "calendars that matter, and set CALENDAR_NAMES=name1,name2 in .env."
        )

    wanted = [name.strip() for name in CALENDAR_NAMES.split(",") if name.strip()]
    all_calendars = {cal.name: cal for cal in principal.get_calendars()}

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
        for obj in cal.search(start=start, end=end, event=True, expand=True):
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
