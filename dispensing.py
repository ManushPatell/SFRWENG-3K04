"""Module 8 - Dispensing.

Runs everything that opens a drawer: dispensing against an order, and
restocking.

Hides: the check order and the drawer timeouts.

Two things hold no matter which path is taken. A drawer is unlocked only
after every check has passed, so nothing opens without a signed-in user
(NFR-SAF-02). Stock only moves after the drawer is shut and locked again,
so a job that gets interrupted is recorded as FAULTED and never as
DISPENSED (NFR-SAF-03).
"""
from enum import Enum

from shared import Action, BoltState, Decision, DoorState, Indicator, LockCmd, Reason

OPEN_TIMEOUT_SECONDS = 30.0      # FR-DISP-09
RELOCK_BUDGET_SECONDS = 2.0      # FR-FD-02


class Step(str, Enum):
    IDLE = "IDLE"
    WAITING_TO_OPEN = "WAITING_TO_OPEN"
    WAITING_TO_CLOSE = "WAITING_TO_CLOSE"


class Dispensing:
    """Always true here: when the step is IDLE this module has no drawer
    unlocked, and stock moves at most once per job."""

    def __init__(self, users, modes, inventory, link, hardware, report):
        self._users = users
        self._modes = modes
        self._inventory = inventory
        self._link = link
        self._hw = hardware
        self._report = report

        self._step = Step.IDLE
        self._job = None
        self._opened_at = 0.0
        self._closed_at = None
        self._unlocked = None

    # --- what the screen asks -----------------------------------------------

    def step(self):
        return self._step

    def busy(self):
        return self._step is not Step.IDLE

    def drawer(self):
        return self._job["drawer"] if self._job else None

    def seconds_left(self):
        if self._step is not Step.WAITING_TO_OPEN:
            return 0.0
        return max(0.0, OPEN_TIMEOUT_SECONDS - self._hw.since(self._opened_at))

    def prompt(self):
        """What to do next. The exact wording on screen is Screen's job."""
        if self._step is Step.IDLE:
            return ""
        drawer = self._job["drawer"]
        if self._step is Step.WAITING_TO_OPEN:
            return "Open drawer %s within %s s." % (drawer, int(self.seconds_left()))
        if self._job["kind"] == "RESTOCK":
            return "Load the stock and close drawer %s." % drawer
        return "Take the dose and close drawer %s." % drawer

    def orders(self):
        """Every active order (FR-DISP-01)."""
        return tuple(o for o in self._link.orders().values() if o.active)

    def order(self, order_id):
        order = self._link.orders().get(order_id)
        return order if order and order.active else None

    # --- starting a job -----------------------------------------------------

    def start_dispense(self, order_id, quantity):
        """Ask to dispense against an order.

        Checks, in order: signed in and may dispense and mode allows it
        (FR-AUTH-09, FR-OPM-06/07); the order is active and the quantity is
        not more than the ordered dose (FR-DISP-05); a drawer holds it and
        is in service; there is enough stock (FR-DISP-06/07). Only then:
        unlock (NFR-SAF-02). Allowed means the drawer is unlocked, its
        light is on and a 30 s timer is running - no stock has moved yet.
        """
        session, refusal = self._begin(Action.DISPENSE, order=order_id)
        if refusal:
            return refusal

        order = self.order(order_id)
        if order is None:
            return self._refuse(Decision.reject(Reason.NO_ACTIVE_ORDER,
                                                str(order_id)),
                                order=order_id, user=session.user_id)
        if quantity is None or quantity <= 0:
            return self._refuse(Decision.reject(Reason.BAD_REQUEST,
                                                "quantity must be > 0"),
                                order=order_id, user=session.user_id)
        if quantity > order.dose:
            return self._refuse(
                Decision.reject(Reason.EXCEEDS_ORDERED_DOSE,
                                "ordered dose is %s" % order.dose),
                order=order_id, user=session.user_id)

        drawer = self._inventory.drawer_holding(order.medication_id)
        if drawer is None:
            return self._refuse(
                Decision.reject(Reason.OUT_OF_STOCK, order.medication_id),
                order=order_id, user=session.user_id)

        allowed = self._inventory.can_take(drawer, quantity)
        if not allowed.ok:
            return self._refuse(allowed, order=order_id, user=session.user_id,
                                drawer=drawer)

        return self._open(drawer, quantity, session.user_id, kind="DISPENSE",
                          order_id=order_id, medication_id=order.medication_id,
                          patient=order.patient)

    def start_restock(self, drawer_id, quantity):
        """Ask to restock a drawer. The medication comes from the scanner,
        not from the screen, so a technician cannot type past the scan
        (FR-INV-17)."""
        session, refusal = self._begin(Action.RESTOCK, drawer=drawer_id)
        if refusal:
            return refusal

        scanned = self._hw.scan()
        if not scanned:
            return self._refuse(
                Decision.reject(Reason.BAD_REQUEST,
                                "scan the medication before restocking"),
                drawer=drawer_id, user=session.user_id)

        allowed = self._inventory.can_restock(drawer_id, scanned, quantity)
        if not allowed.ok:
            return self._refuse(allowed, drawer=drawer_id,
                                user=session.user_id, med=scanned)

        return self._open(drawer_id, quantity, session.user_id, kind="RESTOCK",
                          order_id=None, medication_id=scanned, patient=None)

    # --- the periodic work ---------------------------------------------------

    def tick(self):
        """Move the open job along against the hardware and the clock.

        Waiting to open: the drawer opened, or the timer ran out and we
        relock with nothing changed (FR-DISP-09). Waiting to close: the
        drawer shut, so we lock it; once locked, a restock credits its
        stock and a dispense reduces stock - the only place either does
        (NFR-SAF-03). If the bolt will not engage within two seconds, that
        is a lock fault and the job is recorded as FAULTED with no stock
        moved (FR-FD-02).
        """
        if self._step is Step.IDLE:
            return

        drawer = self._job["drawer"]
        door = self._hw.door(drawer)

        if self._step is Step.WAITING_TO_OPEN:
            if door is DoorState.OPEN:
                self._step = Step.WAITING_TO_CLOSE
            elif self.seconds_left() <= 0:
                kind = self._job["kind"]
                self._relock(drawer)
                self._finish(kind + "_CANCELLED",
                             reason=Reason.NOT_OPENED_IN_TIME.value)
            return

        if self._step is not Step.WAITING_TO_CLOSE:
            return

        if door is not DoorState.CLOSED:
            self._closed_at = None
            return

        if self._closed_at is None:
            self._closed_at = self._hw.uptime()

        if self._hw.command_lock(drawer, LockCmd.LOCK) is BoltState.LOCKED:
            self._hw.set_indicator(drawer, Indicator.OFF)
            self._unlocked = None
            self._settle()
            return

        if self._hw.since(self._closed_at) < RELOCK_BUDGET_SECONDS:
            return   # one failed attempt is not a fault yet

        kind = self._job["kind"]
        self._modes.report_lock_fault(
            drawer, "did not relock within %s s" % int(RELOCK_BUDGET_SECONDS))
        if self._step is not Step.IDLE:
            self._finish(kind + "_FAULTED", reason=Reason.LOCK_FAULT.value)

    # --- cancelling -----------------------------------------------------------

    def cancel(self, why="operator cancelled"):
        """Give up an open job. The drawer is relocked and no stock moves.
        Before the drawer opens that is a cancellation; after, it is
        recorded as FAULTED (NFR-SAF-03)."""
        if self._step is Step.IDLE:
            return Decision.allow("nothing to cancel")
        kind = self._job["kind"]
        self._relock(self._job["drawer"])
        was_opened = self._step is not Step.WAITING_TO_OPEN
        self._finish(kind + ("_FAULTED" if was_opened else "_CANCELLED"), reason=why)
        return Decision.allow()

    def make_safe(self, why="fault mode"):
        """Abandon any open job because the cabinet is going somewhere
        safe."""
        if self.busy():
            self.cancel(why)

    def check_invariant(self):
        if self._step is Step.IDLE:
            return self._job is None and self._unlocked is None
        if self._job is None:
            return False
        return self._unlocked == self._job["drawer"]

    # --- the secret -----------------------------------------------------------

    def _begin(self, action, **refusal_details):
        """Nothing else running, somebody signed in who may do this, and a
        mode that allows a drawer to open."""
        if self.busy():
            return None, self._refuse(
                Decision.reject(Reason.TRANSACTION_IN_PROGRESS),
                **refusal_details)

        allowed = self._users.may(action)
        if not allowed.ok:
            return None, self._refuse(allowed, **refusal_details)

        session = self._users.session()
        allowed = self._modes.dispensing_allowed()
        if not allowed.ok:
            return None, self._refuse(allowed, user=session.user_id,
                                      **refusal_details)
        return session, None

    def _open(self, drawer, quantity, user_id, **job):
        if self._hw.command_lock(drawer, LockCmd.UNLOCK) is not BoltState.UNLOCKED:
            self._modes.report_lock_fault(drawer, "did not unlock")
            self._report(job["kind"] + "_REJECTED", user_id, drawer=drawer,
                         reason=Reason.LOCK_FAULT.value)
            return Decision.reject(Reason.LOCK_FAULT, "drawer %s" % drawer)

        self._unlocked = drawer
        self._job = dict(job, drawer=drawer, quantity=int(quantity), user=user_id)
        self._step = Step.WAITING_TO_OPEN
        self._opened_at = self._hw.uptime()
        self._closed_at = None
        self._hw.set_indicator(drawer, Indicator.GUIDE)
        self._modes.expect_open(drawer)
        self._report(job["kind"] + "_STARTED", user_id, drawer=drawer,
                     quantity=int(quantity), med=job.get("medication_id"),
                     order=job.get("order_id"))
        return Decision.allow("drawer %s" % drawer)

    def _settle(self):
        """The only place stock moves, so it is the only place that has to
        get it right. The operator is assumed to have taken or loaded
        exactly the quantity that was authorised."""
        job = self._job
        try:
            if job["kind"] == "RESTOCK":
                result = self._inventory.restock(job["drawer"],
                                                 job["medication_id"],
                                                 job["quantity"], job["user"])
            else:
                result = self._inventory.take(job["drawer"], job["quantity"],
                                              job["user"])
        except Exception as e:
            self._modes.report_storage_fault(str(e))
            self._finish(job["kind"] + "_FAULTED",
                         reason=Reason.STORAGE_FAILURE.value)
            return

        if not result.ok:
            self._finish(job["kind"] + "_FAULTED", reason=result.reason.value)
            return

        event = "RESTOCK_SETTLED" if job["kind"] == "RESTOCK" else "DISPENSE_COMPLETE"
        # FR-EVL-03/04: user, patient/medication, quantity and time are all here
        self._finish(event, patient=job.get("patient"),
                     med=job["medication_id"], quantity=job["quantity"],
                     order=job.get("order_id"))

    def _relock(self, drawer):
        self._hw.command_lock(drawer, LockCmd.LOCK)
        self._hw.set_indicator(drawer, Indicator.OFF)
        self._unlocked = None

    def _finish(self, event, **details):
        job = self._job or {}
        drawer = job.get("drawer")
        if drawer is not None:
            self._modes.stop_expecting(drawer)
        self._step = Step.IDLE
        self._job = None
        self._unlocked = None
        self._closed_at = None
        clean = {k: v for k, v in details.items() if v is not None}
        self._safe_report(event, job.get("user"), drawer=drawer, **clean)

    def _refuse(self, decision, **details):
        user = details.pop("user", None)
        clean = {k: v for k, v in details.items() if v is not None}
        self._safe_report("DISPENSE_REJECTED", user,
                          reason=decision.reason.value, **clean)
        return decision

    def _safe_report(self, *args, **kwargs):
        try:
            self._report(*args, **kwargs)
        except Exception:
            pass
