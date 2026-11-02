"""Module 1 - Hardware.

Talks to the drawer locks, door sensors, barcode scanner, lights, buzzer and
clock.

Hides: how those devices are driven and read. The rest of the program says
"unlock drawer 2" or asks "is the door open", never a signal.

Hardware is the interface, written entirely in terms of the 4-variable model
from shared.py (DoorState/BoltState monitored, LockCmd controlled). There is
no physical cabinet, so SimulatedHardware is what we run. Its demo switches
(jam a lock, unplug a sensor, cut power) are not on Hardware, so no product
module can reach them - only the test bench can.
"""
from shared import Audible, BoltState, DoorState, Indicator, LockCmd


class Hardware:
    """The devices, as the rest of the program sees them."""

    def command_lock(self, drawer_id, cmd):
        """Lock or unlock a drawer. Returns where the bolt actually ended
        up, which is not always what was asked. Never raises."""
        raise NotImplementedError

    def bolt(self, drawer_id):
        """Where the bolt is now (monitored)."""
        raise NotImplementedError

    def lock_all(self):
        """Command every drawer locked."""
        raise NotImplementedError

    def drawer_ids(self):
        raise NotImplementedError

    def door(self, drawer_id):
        """OPEN, CLOSED or UNKNOWN (monitored)."""
        raise NotImplementedError

    def poll(self):
        """Read every sensor once. Called each tick."""
        raise NotImplementedError

    def scan(self):
        """The medication id of the last package scanned, or None. The
        value is used up, so one scan cannot pay for two restocks."""
        raise NotImplementedError

    def set_indicator(self, drawer_id, state):
        raise NotImplementedError

    def set_audible(self, state):
        raise NotImplementedError

    def indicator(self, drawer_id):
        raise NotImplementedError

    def audible(self):
        raise NotImplementedError

    def now(self):
        """Wall-clock time, for timestamps. Can jump when synced."""
        raise NotImplementedError

    def uptime(self):
        """Seconds since start. Never jumps - every timeout uses this."""
        raise NotImplementedError

    def sync(self, reference_now):
        """Set the wall clock from the Monitoring System. Does not affect
        uptime()."""
        raise NotImplementedError

    def since(self, mark):
        """Seconds since a mark taken from uptime()."""
        return self.uptime() - mark


class SimulatedHardware(Hardware):
    """What we run. Everything below here is the secret."""

    SETTLE_BUDGET_S = 0.2
    SCAN_PREFIX = "MED-"

    def __init__(self, drawer_ids=(1, 2, 3, 4), start_time=None):
        import time
        self._ids = tuple(drawer_ids)

        self._bolt = {d: BoltState.LOCKED for d in self._ids}
        self._jammed = set()
        self._powered = True

        self._really_open = {d: False for d in self._ids}
        self._plugged = {d: True for d in self._ids}

        self._pending_scan = None
        self._light = {d: Indicator.OFF for d in self._ids}
        self._sound = Audible.OFF

        self._wall = float(start_time if start_time is not None else time.time())
        self._mono = 0.0
        self._real0 = time.monotonic()

    def command_lock(self, drawer_id, cmd):
        if drawer_id not in self._ids:
            raise KeyError("no drawer %s" % drawer_id)
        if not self._powered:
            self._bolt[drawer_id] = BoltState.LOCKED
            return BoltState.LOCKED
        if drawer_id in self._jammed:
            return self._bolt[drawer_id]
        self._bolt[drawer_id] = (BoltState.UNLOCKED if cmd is LockCmd.UNLOCK
                                 else BoltState.LOCKED)
        return self._bolt[drawer_id]

    def bolt(self, drawer_id):
        if not self._powered:
            return BoltState.LOCKED
        return self._bolt[drawer_id]

    def lock_all(self):
        for d in self._ids:
            if d not in self._jammed:
                self._bolt[d] = BoltState.LOCKED

    def drawer_ids(self):
        return self._ids

    def door(self, drawer_id):
        if not self._plugged[drawer_id]:
            return DoorState.UNKNOWN
        return DoorState.OPEN if self._really_open[drawer_id] else DoorState.CLOSED

    def poll(self):
        pass    # the simulated door reads straight through; nothing to do

    def scan(self):
        value = self._pending_scan
        self._pending_scan = None
        return value

    def set_indicator(self, drawer_id, state):
        self._light[drawer_id] = state

    def set_audible(self, state):
        self._sound = state

    def indicator(self, drawer_id):
        return self._light[drawer_id]

    def audible(self):
        return self._sound

    def all_off(self):
        for d in self._ids:
            self._light[d] = Indicator.OFF
        self._sound = Audible.OFF

    def now(self):
        return self._wall + self._elapsed()

    def uptime(self):
        return self._mono + self._elapsed()

    def sync(self, reference_now):
        offset = reference_now - self.now()
        self._wall += offset
        return offset

    def _elapsed(self):
        import time
        return time.monotonic() - self._real0

    # --- demo switches: not on Hardware, so no module can call them -------

    def set_door(self, drawer_id, is_open):
        self._really_open[drawer_id] = bool(is_open)

    def jam(self, drawer_id):
        self._jammed.add(drawer_id)

    def unjam(self, drawer_id):
        self._jammed.discard(drawer_id)

    def is_jammed(self, drawer_id):
        return drawer_id in self._jammed

    def unplug_sensor(self, drawer_id):
        self._plugged[drawer_id] = False

    def plug_sensor(self, drawer_id):
        self._plugged[drawer_id] = True

    def is_plugged(self, drawer_id):
        return self._plugged[drawer_id]

    def is_really_open(self, drawer_id):
        return self._really_open[drawer_id]

    def set_power(self, on):
        """A spring throws the bolt and current pulls it back, so no power
        means every drawer is locked with no software involved (NFR-SAF-01).
        That holds because of the lock we chose, not anything the program
        does."""
        self._powered = bool(on)
        if not on:
            self._bolt = {d: BoltState.LOCKED for d in self._ids}

    def is_powered(self):
        return self._powered

    def present_package(self, medication_id):
        self._pending_scan = medication_id or None

    def advance(self, seconds):
        """Jump time forward so a demo does not wait for a real timeout."""
        import time
        passed = self._elapsed()
        self._wall += passed + seconds
        self._mono += passed + seconds
        self._real0 = time.monotonic()

    def describe_light(self, drawer_id):
        names = {Indicator.OFF: "off", Indicator.GUIDE: "steady green",
                 Indicator.FAULT: "flashing red"}
        return names[self._light[drawer_id]]

    def describe_sound(self):
        names = {Audible.OFF: "silent", Audible.ALARM: "alarm"}
        return names[self._sound]
