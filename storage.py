"""Module 2 - Storage.

Saves things so they survive the cabinet being switched off.

Hides: where records live and what format they are in. Nothing above this
file knows it is a JSON file.

Every write can raise StorageFailure. That is deliberate: FR-FD-14 says the
cabinet goes into Fault mode when a write fails, so callers have to handle
it rather than assume it worked.
"""
import json
import os


class StorageFailure(Exception):
    """A write did not stick, so whatever it recorded did not happen."""


class Storage:
    """Named collections of records."""

    def __init__(self, path=None):
        self._path = path          # None means memory only
        self._data = {}
        if self._path and os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    self._data = json.load(f)
            except (OSError, ValueError):
                self._data = {}

    def put(self, collection, key, value):
        """Save a value. On failure nothing changed and StorageFailure is
        raised."""
        had_before = key in self._data.get(collection, {})
        before = self._data.get(collection, {}).get(key)
        self._data.setdefault(collection, {})[key] = value
        try:
            self._save()
        except StorageFailure:
            if had_before:
                self._data[collection][key] = before
            else:
                self._data[collection].pop(key, None)
            raise

    def append(self, collection, record):
        """Add a record and return its position. Positions count up from 0
        and are never reused, so a caller can use one as a sequence
        number."""
        items = self._data.setdefault(collection, [])
        items.append(record)
        try:
            self._save()
        except StorageFailure:
            items.pop()
            raise
        return len(items) - 1

    def get(self, collection, key, default=None):
        return self._data.get(collection, {}).get(key, default)

    def all(self, collection):
        """A copy of a collection, so a caller cannot change stored data
        without going through put() or append()."""
        value = self._data.get(collection)
        if value is None:
            return ()
        if isinstance(value, list):
            return tuple(value)
        return dict(value)

    def length(self, collection):
        return len(self._data.get(collection, ()))

    def _save(self):
        self._before_write()
        if not self._path:
            return
        try:
            folder = os.path.dirname(os.path.abspath(self._path))
            os.makedirs(folder, exist_ok=True)
            with open(self._path, "w") as f:
                json.dump(self._data, f, default=str)
        except OSError as e:
            raise StorageFailure(str(e)) from e

    def _before_write(self):
        """Real storage has no reason to refuse. The simulator overrides
        this so a demo can make writes fail."""


class SimulatedStorage(Storage):
    """Adds the demo switch. It is not on Storage, so no module can use it."""

    def __init__(self, path=None):
        super().__init__(path)
        self._failing = False

    def _before_write(self):
        if self._failing:
            raise StorageFailure("storage device did not accept the write")

    def set_failing(self, failing):
        self._failing = bool(failing)

    def is_failing(self):
        return self._failing
