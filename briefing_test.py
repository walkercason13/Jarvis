"""Fail-soft test for the morning briefing.

Two things are checked:

1. Diagnosis accuracy (offline, no API calls). Each simulated failure must be
   reported as its own actual cause. In particular, the "regenerate the
   app-specific password" claim must appear ONLY for a verified CalDAV 401/403 —
   never for a 503, a network drop, or a bug in our own code.

2. End-to-end fail-soft delivery (one real Claude call, one real Telegram
   message). WHOOP is unreachable and iCloud returns a 503; a briefing must
   still arrive, saying plainly what's missing without blaming the password.
"""

import sys

import requests
from caldav.lib.error import AuthorizationError, PropfindError

import apple_calendar
import briefing
import whoop

PASSWORD_CLAIM = "app-specific password"


def _raise(error):
    def _fn(*args, **kwargs):
        raise error

    return _fn


def _http_error(status):
    response = requests.Response()
    response.status_code = status
    error = requests.HTTPError(f"{status} Server Error")
    error.response = response
    return error


def _calendar_lines(error):
    original = apple_calendar.get_today_and_tomorrow
    apple_calendar.get_today_and_tomorrow = _raise(error)
    try:
        lines = []
        briefing._load_calendar(lines)
        return lines
    finally:
        apple_calendar.get_today_and_tomorrow = original


def check_diagnosis():
    """The password claim is a specific accusation. It must be earned."""
    cases = [
        ("verified 401", apple_calendar._wrap("Connecting", AuthorizationError("reason Unauthorized")), True),
        ("iCloud 503", apple_calendar._wrap("Reading 'Home'", _http_error(503)), False),
        ("network drop", apple_calendar._wrap("Connecting", requests.ConnectionError("DNS failure")), False),
        ("CalDAV PropfindError", apple_calendar._wrap("Listing", PropfindError("bad multistatus")), False),
        ("bug in our own code", TypeError("unrelated bug"), False),
    ]

    failures = 0
    for name, error, should_claim in cases:
        lines = _calendar_lines(error)
        claimed = any(PASSWORD_CLAIM in line for line in lines)
        ok = claimed == should_claim
        failures += not ok
        verdict = "PASS" if ok else "FAIL"
        expected = "claims password" if should_claim else "must not claim password"
        print(f"  [{verdict}] {name}: {expected}")
        for line in lines:
            print(f"           {line}")

    # A failed cycle request must not be reported as "the strap hasn't synced" —
    # that is a claim about the strap we have no evidence for.
    original = whoop.get_today_cycle
    whoop.get_today_cycle = _raise(requests.ConnectionError("WHOOP unreachable"))
    try:
        lines = []
        briefing._load_whoop(lines)
    finally:
        whoop.get_today_cycle = original

    synced_claim = any("hasn't synced" in line for line in lines)
    failures += synced_claim
    print(f"  [{'FAIL' if synced_claim else 'PASS'}] WHOOP request failure: must not claim 'not synced'")
    for line in lines:
        print(f"           {line}")

    return failures


def main():
    print("Checking diagnosis accuracy (no API calls)...")
    failures = check_diagnosis()
    if failures:
        print(f"\n{failures} diagnosis check(s) failed — not sending a briefing.", file=sys.stderr)
        sys.exit(1)
    print("\nAll diagnosis checks passed.\n")

    print("Running the briefing with WHOOP unreachable and iCloud returning 503...\n")
    outage = _raise(requests.ConnectionError("simulated WHOOP outage"))
    whoop.get_today_cycle = outage
    whoop.get_today_strain = outage
    whoop.get_today_recovery = outage
    whoop.get_today_sleep = outage
    apple_calendar.get_today_and_tomorrow = _raise(
        apple_calendar._wrap("Reading the 'Home' calendar", _http_error(503))
    )
    briefing.main()


if __name__ == "__main__":
    main()
