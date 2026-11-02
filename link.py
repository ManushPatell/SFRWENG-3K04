"""Module 4 - Link.

Talks to the Monitoring System and says whether the connection is up.

Hides: the message format and how we decide the link is down. The cabinet
keeps working when this module cannot reach anyone (FR-EC-11, NFR-AVL-02) -
nothing here blocks or raises, so a network problem is a link failure, not
a crash.
"""
from shared import LinkState, MedicationOrder

HEARTBEAT_SECONDS = 10.0     # FR-FD-10
MISSES_BEFORE_OFFLINE = 3    # FR-EC-08
VERSION = 1


class Link:
    def __init__(self, adc_id, hardware, log, peer=None):
        self._adc_id = adc_id
        self._hw = hardware
        self._log = log
        self._peer = peer

        self._state = LinkState.OFFLINE
        self._misses = 0
        self._last_beat = -HEARTBEAT_SECONDS
        self._pending = []          # events/alarms not yet acknowledged

        self._users = {}
        self._orders = {}

    # --- sending -----------------------------------------------------------

    def send_event(self, seq, event_type, user_id, details):
        """Offer one logged event (FR-EC-01)."""
        self._offer(self._wrap("EVENT", seq=seq, event=event_type,
                               user=user_id, details=details))

    def send_alarm(self, fault):
        """Offer a raised fault (FR-EC-02)."""
        self._offer(self._wrap("ALARM", fault=fault.fault_type.value,
                               drawer=fault.drawer_id,
                               raised_at=fault.raised_at,
                               detail=fault.detail), front=True)

    def send_mode(self, old_mode, new_mode):
        """Offer a mode change (FR-EC-03)."""
        self._offer(self._wrap("MODE", **{"from": old_mode.value,
                                          "to": new_mode.value}))

    def send_stock(self, view):
        """Offer a stock level (FR-EC-04/05)."""
        self._offer(self._wrap("INVENTORY", drawer=view.drawer_id,
                               med=view.medication_id, qty=view.quantity,
                               low=view.low, out=view.out_of_stock))

    # --- the periodic work ---------------------------------------------------

    def tick(self):
        """Send a heartbeat if one is due, then try to clear the backlog.
        Never raises."""
        if self._hw.since(self._last_beat) >= HEARTBEAT_SECONDS:
            self._last_beat = self._hw.uptime()
            reply = self._transmit(self._wrap("HEARTBEAT"))
            self._note(reply)

        for message in list(self._pending):
            reply = self._transmit(message)
            if reply is None:
                self._note(None)
                break
            self._note(reply)
            self._pending.remove(message)

    # --- questions other modules ask ------------------------------------------

    def state(self):
        """ONLINE or OFFLINE. OFFLINE only means we cannot reach anyone; the
        cabinet carries on either way."""
        return self._state

    def waiting(self):
        """How many messages have not reached the Monitoring System yet
        (FR-EC-12)."""
        return len(self._pending)

    def users(self):
        return dict(self._users)

    def orders(self):
        """The active orders we last received (FR-EC-13)."""
        return dict(self._orders)

    def connect(self, peer):
        """Attach the other end. A peer is anything with
        receive(message) -> message | None."""
        self._peer = peer

    # --- the secret ------------------------------------------------------------

    def _wrap(self, kind, **body):
        return {"v": VERSION, "adc": self._adc_id, "kind": kind, **body}

    def _offer(self, message, front=False):
        if front:
            self._pending.insert(0, message)   # FR-EC-18: alarms go first
        else:
            self._pending.append(message)

    def _transmit(self, message):
        if self._peer is None:
            return None
        try:
            return self._peer.receive(dict(message))
        except Exception:
            return None

    def _note(self, reply):
        if reply is None or reply.get("adc") != self._adc_id \
                or reply.get("v") != VERSION:
            self._misses += 1
            if self._misses >= MISSES_BEFORE_OFFLINE:
                self._state = LinkState.OFFLINE
            return

        self._misses = 0
        was_offline = self._state is LinkState.OFFLINE
        self._state = LinkState.ONLINE
        if was_offline:
            # FR-EC-17: re-pull the lists rather than trust a stale cache
            self._apply(self._transmit(self._wrap("REQUEST_LISTS")))
        self._apply(reply)

    def _apply(self, message):
        if not message:
            return
        if "users" in message:
            self._users = dict(message["users"])
        if "orders" in message:
            self._orders = {o["order_id"]: MedicationOrder(**o)
                            for o in message["orders"]}
        if "now" in message:
            self._hw.sync(message["now"])
