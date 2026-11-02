"""Monitoring System simulator - the other side of the external interface.

This is NOT part of the ADC. Part A owns the cabinet; this stub stands in
for Part B so the external ADC <-> Monitoring System interface can be
exercised, and so losing the link is something a demonstration can
actually do.

It is written to the interface as documented from the ADC's side, and to
nothing else: if it can drive the cabinet correctly knowing only the
documented messages, the documentation is complete.
"""
from users import user_record
from shared import Role

PROTOCOL_VERSION = 1


class MonitoringSystem:
    """A peer endpoint: anything with receive(frame) -> frame | None."""

    def __init__(self, adc_id="ADC-01", clock=None):
        self._adc = adc_id
        self._clock = clock
        self._users = {}
        self._orders = []
        self.received = []      # everything the ADC has sent us
        self.alarms = []        # FR-EC-02 alarms, for the display scenario
        self._reachable = True

    # --- the documented interface -------------------------------------------

    def receive(self, frame):
        """Handle one frame from the ADC and return the reply, or None.
        Returning None is how an unreachable Monitoring System looks from
        the cabinet's side - no exception, just no answer."""
        if not self._reachable:
            return None
        if frame.get("adc") != self._adc or frame.get("v") != PROTOCOL_VERSION:
            return None                      # not ours; say nothing

        kind = frame.get("kind")
        if kind == "ALARM":
            self.alarms.append(dict(frame))
            self.received.append(dict(frame))
        elif kind in ("EVENT", "MODE", "INVENTORY"):
            self.received.append(dict(frame))

        if kind == "REQUEST_LISTS":
            return self._frame("LISTS", users=self._users,
                               orders=self._orders, now=self._now())
        return self._frame("ACK", now=self._now())

    # --- what a Monitoring System operator does -----------------------------

    def add_user(self, user_id, pin, role: Role, active=True):
        """Provision a user. The PIN is turned into the agreed
        representation here, so it never travels in the clear
        (NFR-SEC-01)."""
        self._users[user_id] = user_record(pin, role, active)

    def set_orders(self, orders):
        self._orders = [dict(o.__dict__) for o in orders]

    def set_reachable(self, reachable: bool):
        """Cut or restore the link. This is the demonstration's
        communication-loss switch."""
        self._reachable = bool(reachable)

    def is_reachable(self):
        return self._reachable

    def summary(self):
        return {"events": len(self.received), "alarms": len(self.alarms),
                "reachable": self._reachable}

    # --- implementation --------------------------------------------------------

    def _frame(self, kind, **body):
        return {"v": PROTOCOL_VERSION, "adc": self._adc, "kind": kind, **body}

    def _now(self):
        if self._clock is not None:
            return self._clock.now()
        import time
        return time.time()
