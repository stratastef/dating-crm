"""Reads the source: every SQL statement in `app/` names `user_id`, so no query reaches another user's rows.

A statement that is right without it goes in ALLOWED, with the reason. Row-level security would replace this scan.
"""

import ast
import re
from pathlib import Path

APP = Path(__file__).parent.parent / "app"
SQL = re.compile(r"^\s*(SELECT\s|INSERT INTO\s|UPDATE \w+ SET\s|DELETE FROM\s|WITH \w+ AS)")

# The users table is the tenant itself, keyed by its own id. Invite codes belong to no user: one creates a user.
# The last two read no table.
EXEMPT = re.compile(r"\b(FROM|UPDATE|INTO) (users|invite_codes)\b|^SELECT (1|now\(\))$")

# (file, how the statement starts) -> why it needs no user_id
ALLOWED: dict[tuple[str, str], str] = {
    ("jobs.py", "UPDATE jobs SET"): "the worker runs every user's jobs and marks the one it claimed, by id",
    ("paid_items.py", "SELECT p.id, p.app, p.item"): "a shared column list; each query that uses it adds p.user_id",
    ("push.py", "DELETE FROM devices WHERE token"): "Apple rejected this device token; a token is unique to one phone",
    ("sign_in.py", "SELECT count(*) FILTER"): "rate limits count code requests per phone number and IP, before sign-in",
    ("sign_in.py", "UPDATE sign_in_codes SET code_hash = NULL"): "a sign-in code belongs to a phone number, before sign-in",
}


def statements() -> list[tuple[str, int, str]]:
    found = []
    for path in sorted(APP.glob("*.py")):
        tree = ast.parse(path.read_text())
        inside_f_string = {id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values}
        for node in ast.walk(tree):
            if id(node) in inside_f_string:
                continue
            if isinstance(node, ast.JoinedStr):
                text = "".join(part.value for part in node.values if isinstance(part, ast.Constant))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
            else:
                continue
            if SQL.match(text):
                found.append((path.name, node.lineno, " ".join(text.split())))
    return found


def test_every_sql_statement_names_user_id():
    missing = [
        f"{name}:{line}: {sql[:90]}"
        for name, line, sql in statements()
        if "user_id" not in sql and not EXEMPT.search(sql) and not any(name == file and sql.startswith(start) for file, start in ALLOWED)
    ]
    assert not missing, "SQL without user_id:\n" + "\n".join(missing)
