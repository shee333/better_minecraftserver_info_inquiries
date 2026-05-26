from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

PUBLIC_PLAYER_COLUMNS = [
    "id",
    "player_uuid",
    "username",
    "nickname",
    "DisplayName",
    "Rank",
    "Balance",
    "TotalPlayTime",
    "LastLoginTime",
    "LastLogoffTime",
    "Homes",
    "BannedUntil",
    "BannedAt",
    "BannedBy",
    "BanReason",
]


class CMIRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(f"CMI 数据库不存在: {self.db_path}")
        conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def find_player(self, keyword: str) -> dict[str, Any] | None:
        keyword = keyword.strip()
        if not keyword:
            return None
        columns = ", ".join(PUBLIC_PLAYER_COLUMNS)
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT {columns}
                FROM users
                WHERE lower(username) = lower(?)
                   OR lower(coalesce(nickname, '')) = lower(?)
                   OR lower(coalesce(DisplayName, '')) = lower(?)
                LIMIT 1
                """,
                (keyword, keyword, keyword),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    f"""
                    SELECT {columns}
                    FROM users
                    WHERE lower(username) LIKE lower(?)
                    ORDER BY TotalPlayTime DESC
                    LIMIT 1
                    """,
                    (f"%{keyword}%",),
                ).fetchone()
        return self._normalize_player(row) if row else None

    def playtime_rank(self, limit: int) -> list[dict[str, Any]]:
        columns = ", ".join(PUBLIC_PLAYER_COLUMNS)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {columns}
                FROM users
                WHERE TotalPlayTime IS NOT NULL AND TotalPlayTime > 0
                ORDER BY TotalPlayTime DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._normalize_player(row) for row in rows]

    def balance_rank(self, limit: int) -> list[dict[str, Any]]:
        columns = ", ".join(PUBLIC_PLAYER_COLUMNS)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {columns}
                FROM users
                WHERE Balance IS NOT NULL
                ORDER BY Balance DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._normalize_player(row) for row in rows]

    def recent_players(self, limit: int) -> list[dict[str, Any]]:
        columns = ", ".join(PUBLIC_PLAYER_COLUMNS)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {columns}
                FROM users
                WHERE LastLoginTime IS NOT NULL AND LastLoginTime > 0
                ORDER BY LastLoginTime DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._normalize_player(row) for row in rows]

    def banned_players(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT username, BannedUntil, BannedAt, BannedBy, BanReason
                FROM users
                WHERE BannedUntil IS NOT NULL
                   OR (BanReason IS NOT NULL AND trim(BanReason) != '')
                ORDER BY coalesce(BannedAt, 0) DESC
                """,
            ).fetchall()
        return [dict(row) for row in rows]

    def _normalize_player(self, row: sqlite3.Row) -> dict[str, Any]:
        data = {key: row[key] for key in row.keys()}
        data["home_count"] = count_homes(data.get("Homes"))
        data.pop("Homes", None)
        return data


def count_homes(raw_homes: Any) -> int:
    if raw_homes is None:
        return 0
    text = str(raw_homes).strip()
    if not text:
        return 0

    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return len(parsed)

    entries = [entry for entry in text.split(";") if entry.strip()]
    if entries:
        return len(entries)
    return 1
