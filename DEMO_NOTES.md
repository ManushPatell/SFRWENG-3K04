# Demo notes

How to run the three required scenarios, and how to answer each rubric
point. Written so everyone on the team can run this cold.

## Setup

    python3 run.py

Browser opens at `http://127.0.0.1:8000/`. Demo users: `N001/1111` nurse,
`T001/2222` pharmacy technician, `P001/3333` pharmacist, `M001/5555`
maintenance technician.

## Scenario 1 - ADC: authenticate -> dispense -> log

1. Sign in as `N001/1111`.
2. In "Dispense against an order", pick order `ORD-1` (Acetaminophen for
   A. Brown, dose 2), quantity 2, click **Unlock drawer**.
3. In the test bench, under drawer 1, click **Open door**, then **Close
   door**. The page shows the form again (job finished) and drawer 1's
   quantity dropped from 40 to 38.
4. Sign in as `P001/3333` (pharmacist has `VIEW_LOG`) and show the
   **Recent events** card: `AUTH_OK -> DISPENSE_STARTED -> DISPENSE_COMPLETE`.

Code path: `screen.do("dispense", ...)` -> `Dispensing.start_dispense()`
(checks in `dispensing.py` docstring) -> `Inventory.take()` in `_settle()`
-> `Cabinet.report()` writes to `Log` and offers it to `Link`.

## Scenario 2 - Monitoring: receive alarm -> display

Any fault raised in Scenario 3 is already being shown here: the test
bench's "Monitoring System" panel lists everything `MonitoringSystem.receive()`
has been given, with alarms in their own red feed, exactly as documented
in `link.py`'s message shapes (`send_alarm`, `send_event`, `send_mode`,
`send_stock`). Point at `Link.send_alarm()` -> `MonitoringSystem.receive()`
-> the alarm feed on the page to show the whole path with no code hidden
from the TA.

## Scenario 3 - an off-normal path

Two independent ones are wired up; use whichever fits the question.

**Hardware fault (tamper):** on the test bench, click **Open door** for a
drawer that has *no* transaction running (e.g. drawer 3 or 4 with nobody
mid-dispense). `Modes.check_hardware()` sees an open door with no
`expect_open()` on file, raises `DRAWER_FAULT`, and `Cabinet._fault_raised`
drives the mode to `FAULT` - every drawer relocks, the banner turns red,
and the fault shows up in the Monitoring panel. **Recovery:** sign in as
`M001/5555`, click **Enter Maintenance mode**, close the door, click
**Clear** on the fault row (clearing before the door is shut is correctly
refused - `modes.py`'s `_condition_still_there()`), then **Return to
Normal mode**.

**Communication loss:** click **Cut the link**, then **+35 s** on the
clock three times (real heartbeats are 10 s apart; this manufactures three
misses without waiting). The Monitoring System status flips to `OFFLINE`
and the banner shows events backing up - but dispensing in Scenario 1
still works exactly the same while offline, which is the point
(`link.py`'s docstring: "the cabinet keeps working when this module cannot
reach anyone").

## Rubric -> where to point

- **4-variable model, traceable to D1:** `shared.py`'s module docstring
  spells out monitored (`DoorState`, `BoltState`) vs controlled (`LockCmd`)
  vs other outputs (`Indicator`, `Audible`). Every FR/NFR id in a docstring
  (e.g. `FR-FD-12`, `NFR-SAF-02`) is a live link back to Deliverable 1.
- **Decomposition / module boundaries:** the dependency list in
  `README.md` plus the fact that `modes.py` never imports `inventory.py`
  or `link.py` - `cabinet.py`'s `_fault_raised` is where that knock-on
  effect actually lives, which is the direct answer to "how do you know
  Modes doesn't depend on Inventory".
- **Interfaces match implementation:** every module's public methods have
  one-paragraph docstrings naming the check order and the FR they satisfy;
  open any file and read top to bottom.
- **Own work / everyone understands it:** the whole backend (9 files) is
  under 1,200 lines combined; walk any teammate through `modes.py`'s
  `TABLE` and `dispensing.py`'s `Step` enum first - those two are the
  spine everything else hangs off.

## If they ask for an on-the-spot change

This build deliberately left out several Deliverable-1 requirements to
stay small. Each one is a natural "what if we asked you to add X back"
question, and you already know exactly where it goes:

- **Expiry/lot tracking (FR-INV-09):** one more field (`exp`) on
  `Inventory`'s slot dict, one more check in `can_restock`/`can_take`.
  Nothing else changes - `StockView`, `restock()`'s signature.
- **Operator confirms the quantity actually taken (NFR-SAF-03's full
  version):** add a `WAITING_TO_CONFIRM` step back into `dispensing.py`'s
  `Step` enum between `WAITING_TO_CLOSE` and `_settle()`, same place the
  original design had it.
- **Emergency override (US-08):** a new `start_override()` in
  `dispensing.py` sitting next to `start_dispense()`, reusing `_begin()`
  and `_open()`; the new rule (on an override list, a reason typed, one
  dose only) is one more `_*_allows()` helper.
- **Account lockout (FR-AUTH-04):** a failure counter and a locked-until
  timestamp dict in `users.py`'s `Users.__init__`, checked in `login()`
  right after the unknown-id check.
- **Discrepancy / physical count (FR-INV-11..16):** a `discrepancy` flag
  on the `Inventory` slot, exactly like `min`/`qty` are now, plus
  `can_take` refusing a flagged drawer - the same shape `min_level`
  already has.

The point to make out loud: adding any one of these touches exactly one
module, because the module boundaries haven't moved - only how much is
built behind each boundary has.
