"""Postgres access for Jarvis. One responsibility: connect, reconnect on failure, run queries."""

import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

# Seeded into the goals table on first run. After that the table is the source
# of truth and this constant is never read again — change goals with
# set_goals.py, not by editing this string.
DEFAULT_GOALS = (
    "Build muscle and explosiveness to become a better lacrosse athlete, while "
    "improving physique. Training decisions should serve athletic performance "
    "first, aesthetics second — but both count. Alongside that: guard the "
    "schedule. Between student council, lacrosse, and school, other people's "
    "requests fill the calendar by default — the goal is to defend blocks of "
    "time rather than let them get eaten, and to protect the schedule from "
    "over-commitment."
)

_conn = None


def _connect():
    global _conn
    _conn = psycopg2.connect(DATABASE_URL)
    _conn.autocommit = False
    return _conn


def _is_alive(conn):
    if conn is None or conn.closed:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except psycopg2.OperationalError:
        return False


def run(fn):
    """Run fn(cursor) inside a transaction. Reconnects once and retries if the
    connection has died; a second failure propagates loudly."""
    global _conn
    if not _is_alive(_conn):
        _connect()

    try:
        with _conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            result = fn(cur)
        _conn.commit()
        return result
    except psycopg2.OperationalError:
        _connect()
        with _conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            result = fn(cur)
        _conn.commit()
        return result


def init_schema():
    def _create(cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS whoop_tokens (
                id INTEGER PRIMARY KEY DEFAULT 1,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT single_row CHECK (id = 1)
            )
            """
        )

    run(_create)


def init_goals_schema():
    """Single-row goals table, same pattern as whoop_tokens. The text is
    injected into the persona system prompt at runtime via the
    {{CURRENT_GOALS}} placeholder."""

    def _create(cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY DEFAULT 1,
                goals_text TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT single_goals_row CHECK (id = 1)
            )
            """
        )

    run(_create)


def ensure_goals():
    """Create the table and seed DEFAULT_GOALS if it's empty, so the first
    briefing run works with no separate setup command. Idempotent."""
    init_goals_schema()

    def _seed(cur):
        cur.execute(
            "INSERT INTO goals (id, goals_text) VALUES (1, %s) ON CONFLICT (id) DO NOTHING",
            (DEFAULT_GOALS,),
        )

    run(_seed)


def get_goals():
    def _load(cur):
        cur.execute("SELECT goals_text FROM goals WHERE id = 1")
        return cur.fetchone()

    row = run(_load)
    return row["goals_text"] if row else None


def set_goals(goals_text):
    def _save(cur):
        cur.execute(
            """
            INSERT INTO goals (id, goals_text, updated_at)
            VALUES (1, %s, now())
            ON CONFLICT (id) DO UPDATE SET
                goals_text = EXCLUDED.goals_text,
                updated_at = now()
            """,
            (goals_text,),
        )

    run(_save)


def save_tokens(access_token, refresh_token, expires_at):
    """Upsert access + refresh token atomically. Per the whoop-integration skill,
    the rotated refresh token MUST be persisted in the same transaction as the
    access token, or the connection dies after one hour."""

    def _save(cur):
        cur.execute(
            """
            INSERT INTO whoop_tokens (id, access_token, refresh_token, expires_at, updated_at)
            VALUES (1, %s, %s, %s, now())
            ON CONFLICT (id) DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at,
                updated_at = now()
            """,
            (access_token, refresh_token, expires_at),
        )

    run(_save)


def load_tokens():
    def _load(cur):
        cur.execute("SELECT access_token, refresh_token, expires_at FROM whoop_tokens WHERE id = 1")
        return cur.fetchone()

    return run(_load)
