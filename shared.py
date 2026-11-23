"""Shared names.

Responsibility: the enumerations and tiny record types that more than one
module's interface needs, so they are defined exactly once. Nothing in this
file says how anything is stored, encoded or timed - that is each module's
own secret.

This file IS the 4-variable model for the cabinet:

    monitored variables   DoorState, BoltState   - what the hardware reports
    controlled variables  LockCmd                - what software commands
    other outputs         Indicator, Audible     - the light and the buzzer
    inputs                a login, a scan, a button press - plain values,
                           no type needed here

The required relation NFR-SAF-01 rests on: whatever LockCmd was last sent,
losing power always drives BoltState to LOCKED (see hardware.py). The
required relation modes.py enforces: BoltState may only read UNLOCKED while
Mode is NORMAL and Dispensing has that one drawer open.
"""
from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    NURSE = "Nurse"
    PHARMACY_TECH = "Pharmacy Technician"
    PHARMACIST = "Pharmacist"
    MAINTENANCE = "Maintenance Technician"
    MANUSH = "Manush"

class Mode(str, Enum):
    """FR-OPM-01. STARTUP is held while the self-test runs. The transition
    table itself lives in modes.py - this is just the set of values."""
    STARTUP = "STARTUP"
    NORMAL = "NORMAL"
    MAINTENANCE = "MAINTENANCE"
    FAULT = "FAULT"


class Action(str, Enum):
    """The actions the role-permission table in users.py is defined over."""
    DISPENSE = "dispense"
    RESTOCK = "restock"
    VIEW_INVENTORY = "view_inventory"
    VIEW_LOG = "view_log"
    ACK_ALARM = "ack_alarm"
    CLEAR_FAULT = "clear_fault"
    ENTER_MAINTENANCE = "enter_maintenance"
    EXIT_MAINTENANCE = "exit_maintenance"


# --------------------------------------------------------------------------
# the 4-variable model
# --------------------------------------------------------------------------
class DoorState(str, Enum):
    """Monitored. UNKNOWN means the sensor cannot be read, and is kept
    separate from CLOSED so a dead sensor is never read as a safe drawer."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class BoltState(str, Enum):
    """Monitored: the position the bolt actually reached."""
    LOCKED = "LOCKED"
    UNLOCKED = "UNLOCKED"


class LockCmd(str, Enum):
    """Controlled: what the software asks of the lock."""
    LOCK = "LOCK"
    UNLOCK = "UNLOCK"


class Indicator(str, Enum):
    OFF = "OFF"
    GUIDE = "GUIDE"      # this is the drawer to open
    FAULT = "FAULT"      # this drawer is out of service


class Audible(str, Enum):
    OFF = "OFF"
    ALARM = "ALARM"


# --------------------------------------------------------------------------
# verdicts
# --------------------------------------------------------------------------
class Verdict(str, Enum):
    """The result of a checked request. A caller may only act on ALLOWED."""
    ALLOWED = "ALLOWED"
    REJECTED = "REJECTED"


class Reason(str, Enum):
    """Why a request was refused. Every refusal carries exactly one."""
    NONE = "NONE"
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    ROLE_NOT_PERMITTED = "ROLE_NOT_PERMITTED"
    WRONG_MODE = "WRONG_MODE"
    DRAWER_OUT_OF_SERVICE = "DRAWER_OUT_OF_SERVICE"
    NO_ACTIVE_ORDER = "NO_ACTIVE_ORDER"
    EXCEEDS_ORDERED_DOSE = "EXCEEDS_ORDERED_DOSE"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
    WRONG_MEDICATION = "WRONG_MEDICATION"
    LOCK_FAULT = "LOCK_FAULT"
    NOT_OPENED_IN_TIME = "NOT_OPENED_IN_TIME"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    INVALID_CREDENTIAL = "INVALID_CREDENTIAL"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    FAULTS_STILL_ACTIVE = "FAULTS_STILL_ACTIVE"
    TRANSACTION_IN_PROGRESS = "TRANSACTION_IN_PROGRESS"
    BAD_REQUEST = "BAD_REQUEST"


HUMAN_REASON = {
    Reason.NOT_AUTHENTICATED: "No one is signed in.",
    Reason.ROLE_NOT_PERMITTED: "Your role may not do this.",
    Reason.WRONG_MODE: "The cabinet is not in Normal mode.",
    Reason.DRAWER_OUT_OF_SERVICE: "That drawer is out of service.",
    Reason.NO_ACTIVE_ORDER: "There is no active order for that.",
    Reason.EXCEEDS_ORDERED_DOSE: "That is more than the ordered dose.",
    Reason.OUT_OF_STOCK: "That medication is out of stock.",
    Reason.INSUFFICIENT_STOCK: "There is not enough stock for that quantity.",
    Reason.WRONG_MEDICATION: "The scan does not match this drawer.",
    Reason.LOCK_FAULT: "The drawer lock did not respond.",
    Reason.NOT_OPENED_IN_TIME: "The drawer was not opened in time.",
    Reason.STORAGE_FAILURE: "The cabinet could not record the change.",
    Reason.INVALID_CREDENTIAL: "That ID and PIN were not accepted.",
    Reason.SESSION_EXPIRED: "The session timed out. Log in again.",
    Reason.FAULTS_STILL_ACTIVE: "Faults are still active.",
    Reason.TRANSACTION_IN_PROGRESS: "A transaction is in progress.",
    Reason.BAD_REQUEST: "The request was not understood.",
    Reason.NONE: "",
}


@dataclass(frozen=True)
class Decision:
    """The uniform result type of every checked operation. ALLOWED carries
    Reason.NONE; anything else carries exactly one reason, so a caller can
    never read a refusal as a success."""
    verdict: Verdict
    reason: Reason = Reason.NONE
    detail: str = ""

    @property
    def ok(self):
        return self.verdict is Verdict.ALLOWED

    @staticmethod
    def allow(detail=""):
        return Decision(Verdict.ALLOWED, Reason.NONE, detail)

    @staticmethod
    def reject(reason, detail=""):
        return Decision(Verdict.REJECTED, reason, detail)

    def message(self):
        text = HUMAN_REASON.get(self.reason, "")
        if self.detail:
            text = f"{text} ({self.detail})" if text else self.detail
        return text


# --------------------------------------------------------------------------
# domain records
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Medication:
    medication_id: str
    name: str


@dataclass(frozen=True)
class MedicationOrder:
    """FR-DISP-01/02. `patient` is a display name, not a separate record -
    the cabinet never needs more about a patient than what to show."""
    order_id: str
    patient: str
    medication_id: str
    dose: int
    active: bool = True


@dataclass(frozen=True)
class Session:
    user_id: str
    role: Role
    started_at: float


@dataclass(frozen=True)
class StockView:
    """A read-only view of one drawer. The Inventory module's internal
    representation is not this type."""
    drawer_id: int
    medication_id: str | None
    quantity: int
    min_level: int
    low: bool
    out_of_stock: bool


class FaultType(str, Enum):
    LOCK_FAULT = "LOCK_FAULT"       # a bolt did not do what it was told
    DRAWER_FAULT = "DRAWER_FAULT"   # a door open with no reason, or too long
    SENSOR_LOST = "SENSOR_LOST"     # a door sensor cannot be read
    STORAGE_FAULT = "STORAGE_FAULT" # a write to storage failed


@dataclass(frozen=True)
class Fault:
    fault_type: FaultType
    drawer_id: int | None
    raised_at: float
    detail: str = ""
    acknowledged: bool = False

    @property
    def key(self):
        return (self.fault_type, self.drawer_id)


class LinkState(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


@dataclass(frozen=True)
class EventView:
    """A read-only view of one log record."""
    sequence: int
    timestamp: float
    event_type: str
    user_id: str | None
    details: dict = field(default_factory=dict)
