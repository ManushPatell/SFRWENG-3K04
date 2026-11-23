"""The application.

Builds the modules, wires them together, and runs the periodic tick. It
has no secret of its own; this is just the one place that knows which
module uses which.

Two jobs genuinely belong to the whole cabinet rather than to any one
module:

  report()  - every event is written to the Log AND offered to the Link
              (FR-EC-01), so "every logged event is reported" is true by
              construction instead of each module remembering to do both.

  the knock-on effects of a fault - put the drawer out of service
              (FR-FD-13), tell the Monitoring System (FR-EC-02) and move
              the mode (FR-OPM-05). Doing it here is what keeps Modes from
              depending on Inventory and Link.
"""
from dispensing import Dispensing
from hardware import SimulatedHardware
from inventory import Inventory
from link import Link
from log import Log
from modes import FAULT_RAISED, SELFTEST_FAIL, SELFTEST_PASS, STORAGE_FAILED, Modes
from storage import SimulatedStorage
from shared import FaultType, Mode
from users import Users

TICK_SECONDS = 0.25

STOCK_EVENTS = {"DISPENSE_COMPLETE", "RESTOCK_SETTLED"}


class Cabinet:
    def __init__(self, adc_id="ADC-01", drawer_ids=(1, 2, 3, 4),
                 store_path=None, peer=None, hardware=None, storage=None):
        self.adc_id = adc_id
        self.drawer_ids = tuple(drawer_ids)

        self.hardware = hardware or SimulatedHardware(self.drawer_ids)
        self.storage = storage or SimulatedStorage(store_path)

        self.log = Log(self.storage, self.hardware)
        self.link = Link(adc_id, self.hardware, self.log, peer)

        self.modes = Modes(self.hardware, self.report,
                           on_fault=self._fault_raised,
                           on_fault_cleared=self._fault_cleared)
        self.users = Users(self.link, self.report, self.hardware)
        self.inventory = Inventory(self.drawer_ids, self.report, self.storage)
        self.dispensing = Dispensing(self.users, self.modes, self.inventory,
                                     self.link, self.hardware, self.report)

        self._handling_fault_mode = False

    # --- running --------------------------------------------------------------

    def start(self):
        """Power on: run the self-test and let the mode table decide where
        that leaves us (FR-OPM-02/03/04)."""
        self.report("STARTUP", None, adc=self.adc_id)
        result = self.modes.self_test()
        self.modes.handle(SELFTEST_PASS if result.ok else SELFTEST_FAIL)
        self.link.tick()
        self.users.sync()
        return self.modes.mode()

    def tick(self):
        """One round of the cabinet's regular work. The order matters:
        read the hardware, move any open job against what we read, then
        send, so anything just recorded goes out the same round."""
        self.modes.check_hardware()
        self.dispensing.tick()
        self.link.tick()
        self.users.session()      # ends an idle session (FR-AUTH-08)

    def shutdown(self):
        self.hardware.lock_all()
        self.hardware.all_off()

    # --- the one place events are recorded and reported -----------------------

    def report(self, event_type, user_id=None, **details):
        """Write an event to the log and offer it to the Monitoring
        System. Raises StorageFailure; a caller that needs the record as
        part of its safety argument must catch that and treat its action
        as FAULTED."""
        seq = self.log.add(event_type, user_id, **details)
        self.link.send_event(seq, event_type, user_id, details)
        self._knock_on_effects(event_type, details)
        return seq

    # --- what the screen reads -------------------------------------------------

    def status(self):
        """Everything the screen shows, built only from what the modules
        publish."""
        return {
            "adc": self.adc_id,
            "mode": self.modes.mode().value,
            "link": self.link.state().value,
            "waiting": self.link.waiting(),
            "session": self.users.session(),
            "faults": self.modes.describe_faults(),
            "log_count": self.log.count(),
            "step": self.dispensing.step().value,
            "prompt": self.dispensing.prompt(),
            "stock": self.inventory.views(),
            "out_of_service": self.inventory.out_of_service(),
        }

    def check_invariants(self):
        """Every module's invariant. Shown live on the demo panel."""
        return {
            "modes": self.modes.check_invariant(),
            "users": self.users.check_invariant(),
            "inventory": self.inventory.check_invariant(),
            "dispensing": self.dispensing.check_invariant(),
        }

    # --- effects that cross module lines ----------------------------------------

    def _fault_raised(self, fault):
        if fault.drawer_id is not None:
            self.inventory.set_out_of_service(fault.drawer_id, True)
        self.link.send_alarm(fault)
        if fault.fault_type is FaultType.STORAGE_FAULT:
            self.modes.handle(STORAGE_FAILED)
        else:
            self.modes.handle(FAULT_RAISED)

    def _fault_cleared(self, fault):
        if fault.drawer_id is None:
            return
        if not self.modes.faults_on(fault.drawer_id):
            self.inventory.set_out_of_service(fault.drawer_id, False)

    def _knock_on_effects(self, event_type, details):
        if event_type == "MODE_CHANGE":
            if details.get("to") == Mode.FAULT.value:
                self._enter_fault_mode()
            self.link.send_mode(Mode(details["from"]), Mode(details["to"]))
        elif event_type in STOCK_EVENTS and details.get("drawer") is not None:
            self.link.send_stock(self.inventory.view(details["drawer"]))

    def _enter_fault_mode(self):
        if self._handling_fault_mode:
            return      # entering fault mode reports, which lands back here
        self._handling_fault_mode = True
        try:
            self.dispensing.make_safe("fault mode")
            self.users.logout("fault mode")
        finally:
            self._handling_fault_mode = False


def load_demo_data(cabinet, monitoring=None):
    """Put the cabinet into the state a demonstration starts from: four
    users, four medications and four loaded drawers. Kept out of Cabinet so
    nothing in the product depends on demo data."""
    from shared import Medication, Role

    people = [("N001", "1111", Role.NURSE),
              ("T001", "2222", Role.PHARMACY_TECH),
              ("P001", "3333", Role.PHARMACIST),
              ("M001", "5555", Role.MAINTENANCE),
              ("MA01", "9090", Role.MANUSH)]
    for user_id, pin, role in people:
        cabinet.users.add_user(user_id, pin, role)
        if monitoring is not None:
            monitoring.add_user(user_id, pin, role)

    medications = [
        Medication("MED-001", "Acetaminophen 500 mg"),
        Medication("MED-002", "Morphine 10 mg/mL"),
        Medication("MED-003", "Amoxicillin 250 mg"),
        Medication("MED-004", "Insulin glargine 100 U/mL")]
    for medication in medications:
        cabinet.inventory.add_medication(medication)

    stock = [(1, "MED-001", 40, 10), (2, "MED-002", 12, 4),
             (3, "MED-003", 25, 8), (4, "MED-004", 15, 5)]
    for drawer, medication_id, quantity, minimum in stock:
        cabinet.inventory.assign(drawer, medication_id)
        cabinet.inventory.set_min_level(drawer, minimum)
        cabinet.inventory.restock(drawer, medication_id, quantity,
                                  user_id="COMMISSIONING")
    return cabinet
