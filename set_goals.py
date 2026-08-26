"""Set or show the goals injected into the persona system prompt.

    python set_goals.py                 # show current goals
    python set_goals.py "new goals..."  # replace them

Changing goals by messaging the bot in plain English is a separate v1 feature
and is not built yet — this is the terminal path in the meantime.
"""

import sys

import db


def main():
    db.ensure_goals()

    if len(sys.argv) == 1:
        print(db.get_goals())
        return

    if len(sys.argv) > 2:
        print('Usage: python set_goals.py "the new goals text"', file=sys.stderr)
        sys.exit(1)

    db.set_goals(sys.argv[1])
    print("Goals updated:")
    print(db.get_goals())


if __name__ == "__main__":
    main()
