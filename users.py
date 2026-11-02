"""Module 5 - Users.

Decides who may sign in and what their role is allowed to do.

Hides: how credentials are stored and checked, and how the role table is
held. A sign-in is decided against the list we already hold and never waits
on the network, which is how NFR-PERF-01 (an answer within 2 s) holds even
when the link is down.
"""
import hashlib
import os

from shared import Action, Decision, Reason, Role, Session

IDLE_SECONDS = 60.0        # FR-AUTH-08

# Deliverable 1, Table 8.1 (trimmed to the actions this build supports)
PERMISSIONS = {
    Role.NURSE: {Action.DISPENSE, Action.ACK_ALARM, Action.VIEW_INVENTORY},
    Role.PHARMACY_TECH: {Action.RESTOCK, Action.VIEW_INVENTORY},
    Role.PHARMACIST: {Action.DISPENSE, Action.RESTOCK,
                      Action.VIEW_INVENTORY, Action.VIEW_LOG,
                      Action.ACK_ALARM},
    Role.MAINTENANCE: {Action.CLEAR_FAULT, Action.ENTER_MAINTENANCE,
                       Action.EXIT_MAINTENANCE, Action.VIEW_LOG,
                       Action.ACK_ALARM, Action.VIEW_INVENTORY},
}


class Users:
    """Always true here: at most one session exists, and if there is one
    its user is still active."""

    def __init__(self, link, report, hardware):
        self._link = link
        self._report = report
        self._hw = hardware
        self._session = None
        self._last_action = 0.0
        self._known = {}

    def add_user(self, user_id, pin, role, active=True):
        """Add a user locally. In service the list comes from the
        Monitoring System; this is for commissioning and the demo. The PIN
        is kept only as a salted hash (NFR-SEC-01)."""
        salt = os.urandom(8).hex()
        self._known[user_id] = {"salt": salt, "hash": _hash(pin, salt),
                                "role": Role(role).value,
                                "active": bool(active)}

    def login(self, user_id, pin):
        """Try to sign in (FR-AUTH-01). On success a session exists with
        the user's role and AUTH_OK is recorded. On failure there is no
        session and AUTH_FAIL is recorded with the reason, never the PIN
        (FR-EVL-01). An unknown or deactivated id is refused (FR-AUTH-06)."""
        user = self._known.get(user_id)

        if user is None or not user["active"]:
            self._report("AUTH_FAIL", user_id,
                         reason=Reason.INVALID_CREDENTIAL.value)
            return Decision.reject(Reason.INVALID_CREDENTIAL)

        if user["hash"] != _hash(pin, user["salt"]):
            self._report("AUTH_FAIL", user_id,
                         reason=Reason.INVALID_CREDENTIAL.value)
            return Decision.reject(Reason.INVALID_CREDENTIAL)

        self._session = Session(user_id, Role(user["role"]), self._hw.now())
        self._last_action = self._hw.uptime()
        self._report("AUTH_OK", user_id, role=user["role"])
        return Decision.allow(user["role"])

    def logout(self, reason="user"):
        """End the session if there is one, and record it (FR-EVL-02). Safe
        to call twice."""
        if self._session is None:
            return
        user_id = self._session.user_id
        self._session = None
        self._report("LOGOUT", user_id, reason=reason)

    def session(self):
        """The current session, or None. Ends it first if it has been idle
        too long (FR-AUTH-08)."""
        if self._session is None:
            return None
        if self._hw.since(self._last_action) >= IDLE_SECONDS:
            self.logout("idle timeout")
            return None
        return self._session

    def touch(self):
        self._last_action = self._hw.uptime()

    def can(self, action):
        """Whether the signed-in user may do this, with no audit record.
        For a screen deciding what to show - asking what a role is allowed
        to see is not an attempt, so it is not worth logging. may() is the
        one to call when the user actually tried to do something."""
        session = self.session()
        return session is not None and Action(action) in PERMISSIONS[session.role]

    def may(self, action):
        """Whether the signed-in user may do this, and records a refusal
        (FR-AUTH-03). "Nobody is signed in" and "your role may not do this"
        are different answers. Call this only for an action someone
        actually attempted - check can() instead to decide what to show."""
        session = self.session()
        if session is None:
            return Decision.reject(Reason.NOT_AUTHENTICATED)
        if Action(action) not in PERMISSIONS[session.role]:
            self._report("ACTION_REFUSED", session.user_id,
                         action=Action(action).value, role=session.role.value)
            return Decision.reject(Reason.ROLE_NOT_PERMITTED,
                                   Action(action).value)
        self.touch()
        return Decision.allow()

    def sync(self):
        """Take the user list the Monitoring System sent (FR-AUTH-02,
        FR-AUTH-10). Ends the session if its user is no longer active."""
        users = self._link.users()
        if not users:
            return 0
        for user_id, record in users.items():
            self._known[user_id] = {"salt": record.get("salt", ""),
                                    "hash": record.get("hash", ""),
                                    "role": record.get("role"),
                                    "active": bool(record.get("active", True))}
        if self._session is not None:
            current = self._known.get(self._session.user_id)
            if current is None or not current["active"]:
                self.logout("user no longer active")
        return len(users)

    def check_invariant(self):
        if self._session is None:
            return True
        user = self._known.get(self._session.user_id)
        return bool(user and user["active"])


def _hash(pin, salt):
    return hashlib.sha256((salt + str(pin)).encode()).hexdigest()


def user_record(pin, role, active=True):
    """Build the record the Monitoring System should send in a user list,
    so a PIN never travels in the clear. Used by the Monitoring System
    simulator."""
    salt = os.urandom(8).hex()
    return {"salt": salt, "hash": _hash(pin, salt),
            "role": Role(role).value, "active": bool(active)}
