"""Persistent shortlist of products worth a second look."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS shortlist (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL,
    source     TEXT NOT NULL,
    title      TEXT NOT NULL,
    url        TEXT,
    score      REAL,
    verdict    TEXT,
    note       TEXT,
    payload    TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(source, product_id)
);
"""


class Shortlist:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def add(self, entry: dict[str, Any], note: str | None = None) -> dict[str, Any]:
        product = entry.get("offer", entry)
        score = entry.get("score", {})
        row = (
            str(product.get("product_id") or product.get("id") or ""),
            str(product.get("source") or "unknown"),
            str(product.get("title") or ""),
            product.get("url"),
            score.get("total") if isinstance(score, dict) else None,
            score.get("verdict") if isinstance(score, dict) else None,
            note,
            json.dumps(entry, default=str),
            time.time(),
        )
        self._conn.execute(
            """INSERT INTO shortlist
               (product_id, source, title, url, score, verdict, note, payload, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(source, product_id) DO UPDATE SET
                 score=excluded.score, verdict=excluded.verdict,
                 note=COALESCE(excluded.note, shortlist.note),
                 payload=excluded.payload""",
            row,
        )
        self._conn.commit()
        return {"saved": True, "product_id": row[0], "source": row[1], "title": row[2]}

    def list(self, limit: int = 50, min_score: float | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM shortlist"
        params: list[Any] = []
        if min_score is not None:
            sql += " WHERE score >= ?"
            params.append(min_score)
        sql += " ORDER BY COALESCE(score, 0) DESC, created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        out = []
        for row in rows:
            record = dict(row)
            try:
                record["payload"] = json.loads(record["payload"])
            except (json.JSONDecodeError, TypeError):
                record["payload"] = {}
            out.append(record)
        return out

    def remove(self, product_id: str, source: str | None = None) -> dict[str, Any]:
        if source:
            cur = self._conn.execute(
                "DELETE FROM shortlist WHERE product_id = ? AND source = ?", (product_id, source)
            )
        else:
            cur = self._conn.execute("DELETE FROM shortlist WHERE product_id = ?", (product_id,))
        self._conn.commit()
        return {"removed": cur.rowcount}
