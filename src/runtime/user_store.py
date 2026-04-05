from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.models.user import User, UserRole

_USER_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    hashed_password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'operator',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
"""


class UserStore:
    """SQLite-backed store for User records.

    Shares the same database file as Storage but manages its own schema.

    When database_path is ":memory:", a single persistent connection is reused
    so that all operations share the same in-memory database (SQLite in-memory
    databases are per-connection).
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self._memory_conn: sqlite3.Connection | None = None

        if self.database_path != ":memory:":
            Path(database_path).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )
        else:
            # Create and cache the single shared in-memory connection.
            conn = sqlite3.connect(":memory:", check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._memory_conn = conn

    def connect(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def init_db(self) -> None:
        with self.connect() as connection:
            connection.executescript(_USER_SCHEMA_SQL)
            connection.commit()

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        d = dict(row)
        d["is_active"] = bool(d["is_active"])
        return User.model_validate(d)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create_user(
        self,
        username: str,
        hashed_password: str,
        role: UserRole | str = UserRole.operator,
        is_active: bool = True,
        created_at: datetime | str | None = None,
    ) -> User:
        """Insert a new user; raises sqlite3.IntegrityError on duplicate username."""
        if created_at is None:
            created_at = datetime.now(timezone.utc)
        if isinstance(created_at, datetime):
            created_at_str = created_at.isoformat()
        else:
            created_at_str = created_at

        role_str = role.value if isinstance(role, UserRole) else role

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO users (username, hashed_password, role, is_active, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (username, hashed_password, role_str, int(is_active), created_at_str),
            )
            connection.commit()

        user = self.get_user_by_username(username)
        assert user is not None  # just inserted — should never be None
        return user

    def get_user_by_username(self, username: str) -> User | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        return self._row_to_user(row) if row else None

    def list_users(self) -> list[User]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM users ORDER BY created_at ASC"
            ).fetchall()
        return [self._row_to_user(row) for row in rows]

    def update_user(
        self,
        username: str,
        *,
        is_active: bool | None = None,
        hashed_password: str | None = None,
        role: UserRole | str | None = None,
    ) -> User | None:
        """Update one or more fields on a user. Returns the updated User or None if not found."""
        if is_active is None and hashed_password is None and role is None:
            return self.get_user_by_username(username)

        parts: list[str] = []
        params: list[object] = []

        if is_active is not None:
            parts.append("is_active = ?")
            params.append(int(is_active))
        if hashed_password is not None:
            parts.append("hashed_password = ?")
            params.append(hashed_password)
        if role is not None:
            parts.append("role = ?")
            params.append(role.value if isinstance(role, UserRole) else role)

        params.append(username)
        sql = f"UPDATE users SET {', '.join(parts)} WHERE username = ?"

        with self.connect() as connection:
            connection.execute(sql, params)
            connection.commit()

        return self.get_user_by_username(username)

    def delete_user(self, username: str) -> bool:
        """Delete a user by username. Returns True if the user existed and was deleted."""
        with self.connect() as connection:
            rowcount = connection.execute(
                "DELETE FROM users WHERE username = ?",
                (username,),
            ).rowcount
            connection.commit()
        return rowcount > 0
