"""Markdown to Telegram HTML.

Claude writes standard Markdown. Telegram renders none of it natively, so a
briefing arrives showing literal `**asterisks**`, `#` hashes and `>` markers.
This module converts what Claude actually emits into the small HTML subset
Telegram supports, and drops what Telegram has no equivalent for.

Deterministic conversion rather than asking Claude for Telegram-safe syntax:
formatting is a delivery concern, and it shouldn't depend on the model
remembering a formatting rule.

Pure text in, pure text out — no network, no Telegram client, no persona.

Telegram's supported tags: b, i, u, s, a, code, pre, blockquote,
tg-spoiler. Anything else is rejected with a BadRequest.
"""

import html
import re

# Placeholders use NUL, which cannot appear in Claude's output, so protected
# spans survive HTML-escaping and inline substitution untouched.
_MARK = "\x00{}{}\x00"

_FENCED_CODE = re.compile(r"```[\w+-]*\n?(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")

_HEADING = re.compile(r"^ {0,3}#{1,6}\s+(.*?)\s*#*$")
_RULE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_BULLET = re.compile(r"^(\s*)[-*+][ \t]+")
_QUOTE = re.compile(r"^ {0,3}>[ \t]?(.*)$")

_BOLD = re.compile(r"\*\*(\S(?:.*?\S)?)\*\*", re.DOTALL)
_BOLD_ALT = re.compile(r"__(\S(?:.*?\S)?)__", re.DOTALL)
_ITALIC = re.compile(r"(?<![*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\*)")
_ITALIC_ALT = re.compile(r"(?<![\w_])_(?!\s)([^_\n]+?)(?<!\s)_(?![\w_])")
_STRIKE = re.compile(r"~~(\S(?:.*?\S)?)~~")
_LINK = re.compile(r"\[([^\]\n]+)\]\(\s*(https?://[^)\s]+)\s*\)")

_EXTRA_BLANKS = re.compile(r"\n{3,}")


def _protect(text, pattern, kind, store, wrap):
    """Replace each match with a placeholder and stash its finished HTML, so
    code spans are never re-parsed as Markdown."""

    def _swap(match):
        token = _MARK.format(kind, len(store))
        store[token] = wrap(_escape(match.group(1)))
        return token

    return pattern.sub(_swap, text)


def _escape(text):
    """Escape only what Telegram's HTML parser treats as markup. Quotes are
    left alone — escaping them inside body text just produces visible
    &quot; noise."""
    return html.escape(text, quote=False)


def _link(match):
    label, url = match.group(1), match.group(2)
    return f'<a href="{url.replace(chr(34), "%22")}">{label}</a>'


def _inline(text):
    """Inline Markdown to HTML. `text` must already be escaped: structural
    markers like '>' are detected on the raw line first, so escaping happens
    per line rather than up front."""
    text = _BOLD.sub(r"<b>\1</b>", text)
    text = _BOLD_ALT.sub(r"<b>\1</b>", text)
    text = _STRIKE.sub(r"<s>\1</s>", text)
    text = _ITALIC.sub(r"<i>\1</i>", text)
    text = _ITALIC_ALT.sub(r"<i>\1</i>", text)
    text = _LINK.sub(_link, text)
    return text


def _render(raw_line):
    return _inline(_escape(raw_line))


def to_html(markdown):
    """Telegram-ready HTML for one message. Safe to send with
    parse_mode=HTML."""
    store = {}
    text = _protect(markdown, _FENCED_CODE, "B", store, lambda s: f"<pre>{s}</pre>")
    text = _protect(text, _INLINE_CODE, "I", store, lambda s: f"<code>{s}</code>")

    out = []
    quote = []

    def _flush_quote():
        if quote:
            out.append("<blockquote>" + "\n".join(quote) + "</blockquote>")
            quote.clear()

    for line in text.split("\n"):
        quoted = _QUOTE.match(line)
        if quoted:
            quote.append(_render(quoted.group(1).strip()))
            continue
        _flush_quote()

        # Telegram has no horizontal rule. Claude uses them as section
        # separators, and the surrounding blank lines already do that job.
        if _RULE.match(line):
            continue

        heading = _HEADING.match(line)
        if heading:
            out.append(f"<b>{_render(heading.group(1).strip())}</b>")
            continue

        # Convert the bullet marker before inline parsing, so a leading "*"
        # is never mistaken for the start of italics.
        bullet = _BULLET.match(line)
        if bullet:
            line = f"{bullet.group(1)}• {line[bullet.end():]}"

        out.append(_render(line))

    _flush_quote()

    result = _EXTRA_BLANKS.sub("\n\n", "\n".join(out)).strip()
    for token, replacement in store.items():
        result = result.replace(token, replacement)
    return result
