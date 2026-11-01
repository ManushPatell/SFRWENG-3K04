"""Storage secret: SQLite schema/serialization. Clients use load/save only."""

from contextlib import contextmanager
import json
import sqlite3
from pathlib import Path


class Store:
    """Persist the complete application snapshot in one SQLite row."""

    def __init__(self, path):
        """Create the database directory and snapshot table when needed."""

        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS snapshot (id INTEGER PRIMARY KEY, body TEXT NOT NULL)"
            )

    @contextmanager
    def _connect(self):
        """Open a short-lived SQLite connection with transaction handling."""

        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def load(self):
        """Load the saved state, returning ``None`` for a new database."""

        with self._connect() as db:
            row = db.execute("SELECT body FROM snapshot WHERE id=1").fetchone()
            return json.loads(row[0]) if row else None

    def save(self, state):
        """Serialize and atomically replace the saved application state."""

        payload = json.dumps(state, allow_nan=False)
        with self._connect() as db:
            db.execute(
                "INSERT INTO snapshot VALUES(1, ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                (payload,),
            )
