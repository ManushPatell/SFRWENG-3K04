"""Module 7 - Modes and Faults.

Holds the operating mode and the list of active faults, and decides when
either changes.

Hides: the mode transition table, what counts as a fault, and the
escalation time. NFR-AVL-01 (Normal mode almost all the time) is helped by
this file: only a critical fault leaves Normal, and the way back is short.

The table below is the state machine from Deliverable 1. Every cell says a
new mode, IGNORE or ILLEGAL, so a transition nobody decided cannot hide in a
blank cell.
"""
from shared import Audible, Decision, DoorState, Fault, FaultType, Indicator, Mode, Reason, Role

OPEN_FAULT_SECONDS = 60.0      # FR-FD-12: a door open this long is a fault

SELFTEST_PASS = "selfTestPassed"
SELFTEST_FAIL = "selfTestFailed"
FAULT_RAISED = "faultDetected"
STORAGE_FAILED = "storageFailed"
ENTER_MAINT = "enterMaintenance"
EXIT_MAINT = "exitMaintenance"

EVENTS = (SELFTEST_PASS, SELFTEST_FAIL, FAULT_RAISED, STORAGE_FAILED,
          ENTER_MAINT, EXIT_MAINT)

IGNORE = "Ignore"      # nothing here; no change, nothing logged
ILLEGAL = "Illegal"    # cannot happen here; stay safe and log it

TABLE = {
    Mode.STARTUP: {
        SELFTEST_PASS: Mode.NORMAL,       # FR-OPM-03
        SELFTEST_FAIL: Mode.FAULT,        # FR-OPM-04
        FAULT_RAISED: Mode.FAULT,
        STORAGE_FAILED: Mode.FAULT,
        ENTER_MAINT: ILLEGAL,
        EXIT_MAINT: ILLEGAL,
    },
    Mode.NORMAL: {
        SELFTEST_PASS: IGNORE,
        SELFTEST_FAIL: Mode.FAULT,
        FAULT_RAISED: Mode.FAULT,         # FR-OPM-05
        STORAGE_FAILED: Mode.FAULT,       # FR-FD-14
        ENTER_MAINT: Mode.MAINTENANCE,    # FR-OPM-08
        EXIT_MAINT: ILLEGAL,
    },
    Mode.MAINTENANCE: {
        SELFTEST_PASS: IGNORE,
        SELFTEST_FAIL: IGNORE,
        FAULT_RAISED: IGNORE,             # repair happens in this mode
        STORAGE_FAILED: Mode.FAULT,
        ENTER_MAINT: IGNORE,
        EXIT_MAINT: Mode.NORMAL,          # FR-OPM-09, guarded below
    },
    Mode.FAULT: {
        SELFTEST_PASS: IGNORE,
        SELFTEST_FAIL: IGNORE,
        FAULT_RAISED: IGNORE,             # already in the safe mode
        STORAGE_FAILED: IGNORE,
        ENTER_MAINT: Mode.MAINTENANCE,    # FR-OPM-10: the only way out
        EXIT_MAINT: ILLEGAL,
    },
}


class Modes:
    """Always true here: in Fault mode every drawer has been commanded
    locked, no dispensing is allowed outside Normal mode, and any
    unacknowledged fault means the alarm is sounding."""

    def __init__(self, hardware, report, on_fault=None, on_fault_cleared=None):
        self._hw = hardware
        self._report = report
        self._on_fault = on_fault or (lambda fault: None)
        self._on_fault_cleared = on_fault_cleared or (lambda fault: None)

        self._mode = Mode.STARTUP
        self._entered_at = hardware.uptime()
        self._locked_on_entry = False

        self._faults = {}
        self._open_since = {}
        self._expected_open = set()

    # --- the mode -----------------------------------------------------------

    def mode(self):
        """The current mode: one of the three FR-OPM-01 asks for, plus
        STARTUP while the self-test runs."""
        return self._mode

    def seconds_in_mode(self):
        return self._hw.since(self._entered_at)

    def dispensing_allowed(self):
        """A drawer may open only in Normal mode (FR-OPM-06, FR-OPM-07)."""
        if self._mode is Mode.NORMAL:
            return Decision.allow()
        return Decision.reject(Reason.WRONG_MODE, self._mode.value)

    def handle(self, event, user_id=None):
        """Give an event to the table. A new mode means we switch, lock
        every drawer, and record the change (FR-OPM-11). IGNORE means
        nothing happens. ILLEGAL means nothing happens, every drawer is
        locked anyway, and FSM_ILLEGAL is recorded."""
        if event not in EVENTS:
            raise ValueError("unknown mode event %r" % event)

        cell = TABLE[self._mode][event]

        if cell is IGNORE:
            return Decision.allow("ignored")

        if cell is ILLEGAL:
            self._safe_report("FSM_ILLEGAL", user_id, event=event)
            return Decision.reject(Reason.BAD_REQUEST,
                                   "%s in %s" % (event, self._mode.value))

        if event == EXIT_MAINT and self._faults:
            return Decision.reject(Reason.FAULTS_STILL_ACTIVE)   # FR-OPM-10

        old = self._mode
        self._mode = cell
        self._entered_at = self._hw.uptime()
        self._enter_mode()
        self._safe_report("MODE_CHANGE", user_id, event=event,
                          **{"from": old.value, "to": cell.value})
        return Decision.allow(cell.value)

    def request_maintenance(self, session, transaction_running):
        """FR-OPM-08: only a Maintenance Technician, and only when nothing
        is part-way through."""
        if session is None:
            return Decision.reject(Reason.NOT_AUTHENTICATED)
        if session.role is not Role.MAINTENANCE:
            return Decision.reject(Reason.ROLE_NOT_PERMITTED,
                                   "enter_maintenance")
        if transaction_running:
            return Decision.reject(Reason.TRANSACTION_IN_PROGRESS)
        return self.handle(ENTER_MAINT, session.user_id)

    def request_normal(self, session):
        """FR-OPM-09/10: only a Maintenance Technician, and only once
        nothing is still faulted."""
        if session is None:
            return Decision.reject(Reason.NOT_AUTHENTICATED)
        if session.role is not Role.MAINTENANCE:
            return Decision.reject(Reason.ROLE_NOT_PERMITTED,
                                   "exit_maintenance")
        return self.handle(EXIT_MAINT, session.user_id)

    # --- faults ---------------------------------------------------------------

    def self_test(self):
        """Check the hardware at start-up (FR-OPM-02). Passes when every
        lock is engaged and every door sensor can be read."""
        from shared import BoltState
        self._hw.poll()
        problems = []
        fault_type = None
        for drawer in self._hw.drawer_ids():
            if self._hw.bolt(drawer) is not BoltState.LOCKED:
                problems.append("drawer %s lock not engaged" % drawer)
                fault_type = fault_type or FaultType.LOCK_FAULT
            if self._hw.door(drawer) is DoorState.UNKNOWN:
                problems.append("drawer %s sensor unreadable" % drawer)
                fault_type = fault_type or FaultType.SENSOR_LOST

        if problems:
            self.raise_fault(fault_type, None, "; ".join(problems))
            self._report("SELFTEST_FAIL", None, problems=problems)
            return Decision.reject(Reason.BAD_REQUEST, "; ".join(problems))

        self._report("SELFTEST_PASS", None)
        return Decision.allow()

    def expect_open(self, drawer_id):
        """This drawer is meant to be opened now, because we unlocked it.
        Without this, an open drawer is treated as a fault (FR-FD-11)."""
        self._expected_open.add(drawer_id)

    def stop_expecting(self, drawer_id):
        self._expected_open.discard(drawer_id)

    def check_hardware(self):
        """Look at the hardware once and escalate anything wrong. Called
        every tick (NFR-PERF-03). A sensor we cannot read is SENSOR_LOST; a
        door open with no reason, or open too long, is DRAWER_FAULT and the
        drawer goes out of service."""
        self._hw.poll()

        for drawer in self._hw.drawer_ids():
            state = self._hw.door(drawer)

            if state is DoorState.UNKNOWN:
                self.raise_fault(FaultType.SENSOR_LOST, drawer,
                                 "sensor unreadable")
                continue

            if state is DoorState.OPEN:
                self._check_open_drawer(drawer)
            else:
                self._open_since.pop(drawer, None)

        self._update_alarm()

    def report_lock_fault(self, drawer_id, detail=""):
        """A lock did not do what it was told (FR-FD-01/02)."""
        return self.raise_fault(FaultType.LOCK_FAULT, drawer_id,
                                detail or "bolt did not move")

    def report_storage_fault(self, detail=""):
        """A write to storage failed (FR-FD-14)."""
        return self.raise_fault(FaultType.STORAGE_FAULT, None,
                                detail or "write rejected")

    def raise_fault(self, fault_type, drawer_id, detail=""):
        """Record a fault as active. If the same fault is already active
        nothing happens, so a condition that sticks around does not fill
        the log."""
        key = (fault_type, drawer_id)
        if key in self._faults:
            return self._faults[key]

        fault = Fault(fault_type, drawer_id, self._hw.now(), detail)
        self._faults[key] = fault
        if drawer_id is not None:
            self._hw.set_indicator(drawer_id, Indicator.FAULT)
        self._update_alarm()
        self._safe_report("FAULT_RAISED", None, fault=fault_type.value,
                          drawer=drawer_id, detail=detail)
        self._on_fault(fault)
        return fault

    def acknowledge(self, fault_type, drawer_id, user_id):
        """An authorised user has seen the alarm (FR-FD-06). The fault
        stays active; only the noise stops."""
        key = (fault_type, drawer_id)
        fault = self._faults.get(key)
        if fault is None:
            return Decision.reject(Reason.BAD_REQUEST, "no such active fault")
        self._faults[key] = Fault(fault.fault_type, fault.drawer_id,
                                  fault.raised_at, fault.detail,
                                  acknowledged=True)
        self._update_alarm()
        self._report("ALARM_ACKNOWLEDGED", user_id, fault=fault_type.value,
                     drawer=drawer_id)
        return Decision.allow()

    def clear_fault(self, fault_type, drawer_id, user_id):
        """Clear a fault that has been fixed (FR-FD-07). Only works if the
        thing that caused it has actually gone."""
        key = (fault_type, drawer_id)
        fault = self._faults.get(key)
        if fault is None:
            return Decision.reject(Reason.BAD_REQUEST, "no such active fault")

        still_there = self._condition_still_there(fault)
        if still_there:
            return Decision.reject(Reason.FAULTS_STILL_ACTIVE, still_there)

        del self._faults[key]
        if drawer_id is not None and not self.faults_on(drawer_id):
            self._hw.set_indicator(drawer_id, Indicator.OFF)
        self._update_alarm()
        self._report("FAULT_CLEARED", user_id, fault=fault_type.value,
                     drawer=drawer_id)
        self._on_fault_cleared(fault)
        return Decision.allow()

    def active_faults(self):
        """Every active fault, oldest first (FR-FD-05)."""
        return tuple(sorted(self._faults.values(), key=lambda f: f.raised_at))

    def faults_on(self, drawer_id):
        return tuple(f for f in self._faults.values()
                     if f.drawer_id == drawer_id)

    def any_fault(self):
        return bool(self._faults)

    def describe_faults(self):
        """One readable line per active fault, for the screen."""
        lines = []
        for fault in self.active_faults():
            where = " on drawer %s" % fault.drawer_id if fault.drawer_id is not None else ""
            seen = " (acknowledged)" if fault.acknowledged else ""
            lines.append("%s%s - %s%s" % (fault.fault_type.value, where,
                                          fault.detail, seen))
        return tuple(lines)

    def check_invariant(self):
        if self._mode is Mode.FAULT and not self._locked_on_entry:
            return False
        for fault in self._faults.values():
            if not fault.acknowledged and self._hw.audible() is not Audible.ALARM:
                return False
        return True

    # --- the secret -------------------------------------------------------------

    def _check_open_drawer(self, drawer):
        if drawer not in self._open_since:
            self._open_since[drawer] = self._hw.uptime()
            if drawer not in self._expected_open:
                self.raise_fault(FaultType.DRAWER_FAULT, drawer,
                                 "opened with no unlock command")
                return

        held_open = self._hw.since(self._open_since[drawer])
        if held_open >= OPEN_FAULT_SECONDS:
            self.raise_fault(FaultType.DRAWER_FAULT, drawer,
                             "open for more than %s s" % int(OPEN_FAULT_SECONDS))

    def _condition_still_there(self, fault):
        from shared import BoltState
        drawer = fault.drawer_id

        if fault.fault_type is FaultType.SENSOR_LOST:
            return "sensor still unreadable" \
                if self._hw.door(drawer) is DoorState.UNKNOWN else ""

        if fault.fault_type is FaultType.DRAWER_FAULT:
            return "drawer still open" \
                if self._hw.door(drawer) is DoorState.OPEN else ""

        if fault.fault_type is FaultType.LOCK_FAULT:
            return "bolt still not engaged" \
                if self._hw.bolt(drawer) is not BoltState.LOCKED else ""

        return ""     # a storage fault is judged by the next write

    def _update_alarm(self):
        """The alarm belongs to whatever is faulted, so it is set in one
        place. A mode change never silences it; only acknowledging does."""
        for fault in self._faults.values():
            if not fault.acknowledged:
                self._hw.set_audible(Audible.ALARM)
                return
        self._hw.set_audible(Audible.OFF)

    def _enter_mode(self):
        """Every mode locks every drawer on the way in (FR-FD-08)."""
        self._hw.lock_all()
        self._locked_on_entry = True

    def _safe_report(self, *args, **kwargs):
        try:
            self._report(*args, **kwargs)
        except Exception:
            pass
