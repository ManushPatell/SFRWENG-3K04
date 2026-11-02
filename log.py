"""Module 3 - Log.

Keeps a permanent record of everything the cabinet does, and lets authorised
users read it.

Hides: the record format. There is no delete and no update - FR-EVL-06 says
no user may remove a log entry, and the easiest way to guarantee that is to
not provide the operation.
"""
from shared import EventView

COLLECTION = "events"

# NFR-SEC-01: a PIN must never end up in a record
BANNED_KEYS = {"pin", "pin_hash", "password", "credential", "secret"}


class Log:
    """Append-only records."""

    def __init__(self, storage, hardware):
        self._storage = storage
        self._hw = hardware

    def add(self, event_type, user_id=None, **details):
        """Record one event and return its sequence number. Raises
        StorageFailure; nothing is recorded in that case."""
        if not event_type:
            raise ValueError("event_type must not be empty")

        safe_details = {k: v for k, v in details.items()
                        if k.lower() not in BANNED_KEYS}
        record = {"seq": self._storage.length(COLLECTION),
                  "ts": self._hw.now(), "type": event_type,
                  "user": user_id, "details": safe_details}
        return self._storage.append(COLLECTION, record)

    def read(self, event_type=None, user_id=None, limit=None):
        """Read the log, oldest first. Returns copies."""
        found = []
        for record in self._storage.all(COLLECTION):
            if event_type and record["type"] != event_type:
                continue
            if user_id and record["user"] != user_id:
                continue
            found.append(EventView(record["seq"], record["ts"],
                                   record["type"], record["user"],
                                   dict(record["details"])))
        if limit:
            found = found[-limit:]
        return tuple(found)

    def count(self):
        """How many records there are. Never goes down."""
        return self._storage.length(COLLECTION)
