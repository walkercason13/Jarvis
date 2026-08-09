"""Success test for the WHOOP integration: run this one command, approve
WHOOP access in the browser once, and today's real recovery/sleep/strain
print in the terminal.
"""

import db
import whoop


def describe(label, state, value, formatter):
    if state == "ok":
        print(f"{label}: {formatter(value)}")
    elif state == "not_synced":
        print(f"{label}: not synced yet (strap hasn't uploaded to WHOOP)")
    else:
        print(f"{label}: {state.lower().replace('_', ' ')}")


def main():
    db.init_schema()

    if db.load_tokens() is None:
        whoop.authorize()

    cycle = whoop.get_today_cycle()

    strain_state, strain = whoop.get_today_strain(cycle)
    describe("Strain (so far today)", strain_state, strain, lambda v: f"{v:.1f}")

    if cycle is None:
        describe("Recovery", "not_synced", None, None)
    else:
        recovery_state, recovery = whoop.get_today_recovery(cycle["id"])
        describe(
            "Recovery",
            recovery_state,
            recovery,
            lambda v: f"{v['score']['recovery_score']}%",
        )

    sleep_state, sleep = whoop.get_today_sleep()
    describe(
        "Sleep performance",
        sleep_state,
        sleep,
        lambda v: f"{v['score']['sleep_performance_percentage']}%",
    )


if __name__ == "__main__":
    main()
