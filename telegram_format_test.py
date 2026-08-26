"""Test for the Markdown to Telegram HTML conversion.

The sample below is real Claude briefing output — headings, bold, italics,
bullets, blockquoted scripture, a link, a code span, and horizontal rules.

Two classes of check: nothing Markdown-ish survives as literal text, and the
result is HTML Telegram will actually accept (balanced tags, supported tags
only). An unbalanced or unknown tag makes Telegram reject the whole message.

No network calls — this is a pure-function test.
"""

import re
import sys

import telegram_format

SAMPLE = """# Wednesday, August 26

Good morning, sir. The instruments are dark this morning.

---

**Recovery: 43% — Yellow, with an asterisk**

HRV at 74.3 ms is within your *normal* range. Check with `whoop_test.py`.

- First bullet item
* Second bullet with an asterisk marker
+ Third marker

## Training Recommendation

Reduce volume by ~20%. Costs 5 < 10 & "quotes" > fine.

> "He gives power to the faint, and to him who has no might he increases strength."
> — Isaiah 40:29 (ESV)

**Word from the arena**

> *"Rest at the end, not in the middle."*
> — Kobe Bryant

Read the [docs](https://developer.whoop.com/api) if curious.

~~Skip this~~ Mind the sleep debt, Walker.

```python
print("code block")
```
"""

TELEGRAM_TAGS = {"b", "i", "u", "s", "a", "code", "pre", "blockquote", "tg-spoiler"}


def main():
    out = telegram_format.to_html(SAMPLE)
    print(out)
    print("\n=== CHECKS ===")

    opened = re.findall(r"<([\w-]+)(?:\s[^>]*)?>", out)
    closed = re.findall(r"</([\w-]+)>", out)

    checks = [
        ("no literal ** survives", "**" not in out),
        ("no literal # heading survives", not re.search(r"^\s*#", out, re.M)),
        ("no literal > quote marker survives", not re.search(r"^\s*(>|&gt;)", out, re.M)),
        ("no horizontal rule survives", not re.search(r"^\s*---\s*$", out, re.M)),
        ("headings became bold", "<b>Wednesday, August 26</b>" in out),
        ("blockquote emitted", "<blockquote>" in out),
        ("both quote blocks emitted", out.count("<blockquote>") == 2),
        ("all three bullet markers became •", out.count("•") == 3),
        ("link converted", '<a href="https://developer.whoop.com/api">docs</a>' in out),
        ("code span converted", "<code>whoop_test.py</code>" in out),
        ("code block converted", "<pre>" in out),
        ("italics converted", "<i>normal</i>" in out),
        ("strikethrough converted", "<s>Skip this</s>" in out),
        ("ampersand escaped", "&amp;" in out),
        ("angle brackets escaped", "&lt;" in out),
        ("quotes left readable", "&quot;" not in out),
        ("no placeholder leaked", "\x00" not in out),
        ("tags balanced", sorted(opened) == sorted(closed)),
        ("only Telegram-supported tags", set(opened) <= TELEGRAM_TAGS),
    ]

    failures = 0
    for name, ok in checks:
        failures += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    if failures:
        print(f"\n{failures} check(s) failed.", file=sys.stderr)
        sys.exit(1)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
