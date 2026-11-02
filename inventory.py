"""Module 6 - Inventory.

Holds what is in each drawer and keeps it in step with what has been
dispensed and restocked.

Hides: how stock and minimum levels are stored. Callers get read-only views
and yes/no answers, never the stored structure, so nothing can change a
quantity without going through an operation that records it.

Always true here: no quantity is ever negative, and an empty drawer has no
medication assigned.
"""
from shared import Decision, Reason, StockView

COLLECTION = "inventory"


class Inventory:
    def __init__(self, drawer_ids, report, storage=None, catalogue=None):
        self._ids = tuple(drawer_ids)
        self._report = report
        self._storage = storage
        self._catalogue = dict(catalogue or {})
        self._out_of_service = set()

        self._slots = {d: {"med": None, "qty": 0, "min": 0}
                       for d in self._ids}
        if self._storage:
            saved = self._storage.get(COLLECTION, "slots") or {}
            for key, value in saved.items():
                if int(key) in self._slots:
                    self._slots[int(key)].update(value)

    # --- the medication catalogue ------------------------------------------

    def add_medication(self, medication):
        self._catalogue[medication.medication_id] = medication

    def medication(self, medication_id):
        return self._catalogue.get(medication_id)

    # --- setting drawers up --------------------------------------------------

    def assign(self, drawer_id, medication_id):
        """Put a medication in a drawer (FR-INV-04). Refused while the
        drawer still holds stock."""
        if medication_id not in self._catalogue:
            return Decision.reject(Reason.BAD_REQUEST, "unknown medication")
        slot = self._slot(drawer_id)
        if slot["qty"] > 0:
            return Decision.reject(Reason.BAD_REQUEST,
                                   "empty the drawer first")
        self._change(drawer_id, med=medication_id, qty=0)
        self._report("DRAWER_ASSIGNED", None, drawer=drawer_id,
                     med=medication_id)
        return Decision.allow()

    def set_min_level(self, drawer_id, level):
        """Set the low-stock level (FR-INV-06). Zero turns the flag off."""
        if level < 0:
            return Decision.reject(Reason.BAD_REQUEST, "level must be >= 0")
        self._change(drawer_id, min=int(level))
        return Decision.allow()

    # --- stock moving in and out ---------------------------------------------

    def can_restock(self, drawer_id, scanned_medication_id, quantity):
        """In order: drawer out of service, nothing assigned, scan does not
        match the drawer (FR-INV-17), quantity not positive, otherwise
        allowed."""
        if drawer_id in self._out_of_service:
            return Decision.reject(Reason.DRAWER_OUT_OF_SERVICE, str(drawer_id))
        slot = self._slot(drawer_id)
        if slot["med"] is None:
            return Decision.reject(Reason.BAD_REQUEST,
                                   "drawer has no medication assigned")
        if scanned_medication_id != slot["med"]:
            return Decision.reject(Reason.WRONG_MEDICATION,
                                   "drawer %s holds %s" % (drawer_id,
                                                           slot["med"]))
        if quantity is None or quantity <= 0:
            return Decision.reject(Reason.BAD_REQUEST, "quantity must be > 0")
        return Decision.allow()

    def restock(self, drawer_id, scanned_medication_id, quantity, user_id=None):
        """Record a restock (FR-INV-02/03). The caller must already have
        checked the role and relocked the drawer."""
        decision = self.can_restock(drawer_id, scanned_medication_id, quantity)
        if not decision.ok:
            self._report("RESTOCK_REJECTED", user_id, drawer=drawer_id,
                         reason=decision.reason.value)
            return decision
        slot = self._slot(drawer_id)
        self._change(drawer_id, qty=slot["qty"] + int(quantity))
        self._report("RESTOCK_COMPLETE", user_id, drawer=drawer_id,
                     med=scanned_medication_id, quantity=int(quantity))
        return Decision.allow()

    def can_take(self, drawer_id, quantity):
        """In order: drawer out of service, quantity not positive, nothing
        in the drawer (FR-DISP-06), not enough in the drawer, otherwise
        allowed."""
        if drawer_id in self._out_of_service:
            return Decision.reject(Reason.DRAWER_OUT_OF_SERVICE, str(drawer_id))
        slot = self._slot(drawer_id)
        if quantity is None or quantity <= 0:
            return Decision.reject(Reason.BAD_REQUEST, "quantity must be > 0")
        if slot["qty"] == 0:
            return Decision.reject(Reason.OUT_OF_STOCK, str(slot["med"]))
        if slot["qty"] < quantity:
            return Decision.reject(Reason.INSUFFICIENT_STOCK,
                                   "%s in drawer %s" % (slot["qty"], drawer_id))
        return Decision.allow()

    def take(self, drawer_id, quantity, user_id=None):
        """Reduce the stored quantity after a confirmed removal (FR-DISP-08).
        The caller must already have checked can_take and had the drawer
        opened and closed."""
        slot = self._slot(drawer_id)
        if quantity <= 0 or quantity > slot["qty"]:
            return Decision.reject(Reason.BAD_REQUEST, "quantity out of range")
        self._change(drawer_id, qty=slot["qty"] - int(quantity))
        return Decision.allow()

    # --- looking at drawers ---------------------------------------------------

    def set_out_of_service(self, drawer_id, out):
        if out:
            self._out_of_service.add(drawer_id)
        else:
            self._out_of_service.discard(drawer_id)

    def out_of_service(self):
        return tuple(sorted(self._out_of_service))

    def view(self, drawer_id):
        """A read-only view of one drawer (FR-INV-10)."""
        slot = self._slot(drawer_id)
        low = bool(slot["min"]) and 0 < slot["qty"] <= slot["min"]
        return StockView(drawer_id=drawer_id, medication_id=slot["med"],
                         quantity=slot["qty"], min_level=slot["min"],
                         low=low, out_of_stock=slot["qty"] == 0)

    def views(self):
        return tuple(self.view(d) for d in self._ids)

    def drawer_holding(self, medication_id):
        for drawer in self._ids:
            if self._slots[drawer]["med"] == medication_id:
                return drawer
        return None

    def drawer_ids(self):
        return self._ids

    def check_invariant(self):
        for slot in self._slots.values():
            if slot["qty"] < 0:
                return False
            if slot["med"] is None and slot["qty"] != 0:
                return False
        return True

    # --- the secret -----------------------------------------------------------

    def _slot(self, drawer_id):
        if drawer_id not in self._slots:
            raise KeyError("no drawer %s" % drawer_id)
        return self._slots[drawer_id]

    def _change(self, drawer_id, **fields):
        slot = self._slots[drawer_id]
        before = dict(slot)
        slot.update(fields)

        if not self.check_invariant():
            self._slots[drawer_id] = before
            raise AssertionError("that change would break the invariant")

        if self._storage:
            try:
                saved = {str(k): dict(v) for k, v in self._slots.items()}
                self._storage.put(COLLECTION, "slots", saved)
            except Exception:
                self._slots[drawer_id] = before
                raise
