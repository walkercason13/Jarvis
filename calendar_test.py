"""Success test for the Apple Calendar integration.

First run (no CALENDAR_NAMES set): lists every calendar on the account so
Walker can pick which ones matter.

After CALENDAR_NAMES is set in .env: prints today's and tomorrow's events.
"""

from datetime import datetime

import apple_calendar as cal


def format_event(event):
    start = event["start"].strftime("%-I:%M %p") if hasattr(event["start"], "strftime") else "(all day)"
    line = f"  {start} — {event['summary']}"
    if event["location"]:
        line += f" ({event['location']})"
    return line


def main():
    if not cal.CALENDAR_NAMES.strip():
        print("CALENDAR_NAMES is not set yet. Calendars found on this account:\n")
        for name in cal.list_calendars():
            print(f"  - {name}")
        print("\nAdd the ones that matter to .env as CALENDAR_NAMES=name1,name2 and re-run.")
        return

    events = cal.get_today_and_tomorrow()
    today = datetime.now(cal.TZ).date()

    today_events = [e for e in events if e["start"].date() == today]
    tomorrow_events = [e for e in events if e["start"].date() != today]

    print("Today:")
    if today_events:
        for e in today_events:
            print(format_event(e))
    else:
        print("  (nothing scheduled)")

    print("\nTomorrow:")
    if tomorrow_events:
        for e in tomorrow_events:
            print(format_event(e))
    else:
        print("  (nothing scheduled)")


if __name__ == "__main__":
    try:
        main()
    except cal.CalendarAuthError as e:
        print(f"Calendar sync failed: {e}")
