# Automated Dispensing Cabinet — 3K04 Deliverable 2, Part A

Team 36, L03. Python 3, standard library only. Nothing to install.

This is the **simplified demo build**: same 9-module decomposition and the
same state machine as the full design, but trimmed to what the demo
actually needs so the whole team can hold it in their heads. See
`DEMO_NOTES.md` for the live demo script and a map from the rubric to the
code. Features that were cut on purpose (expiry/lot tracking, discrepancy
resolution, controlled-substance count-back, emergency override, account
lockout) are noted inline where they'd go back in - they are good answers
to "what if we asked you to add X back".

## Run it

    python3 run.py

Opens http://127.0.0.1:8000/ by itself. Sign in as **N001 / 1111** (nurse).

The page is the cabinet: a status bar, the current step, the drawers, and
the forms the signed-in role may use. There is no JavaScript - every
button is a plain HTML form; a click is one POST, the server updates one
module, and the page re-renders from the modules' own public state. That
is also why there is nothing "hidden" here: reading `screen.py` and
`demo_server.py` is reading everything the browser can do.

Everything below the dashed rule on the page is the **test bench** and is
*not the product* — the simulated hardware and the Monitoring System
stand-in, which is how you jam a lock, open a drawer without unlocking it,
or cut the link without touching any product code. Those switches live
only on `SimulatedHardware`/`SimulatedStorage`/`MonitoringSystem`, never on
the `Hardware`/`Storage` interfaces the product modules are written
against.

## The 9 modules

| # | File | What it does | What it hides |
|---|------|--------------|---------------|
| 1 | `hardware.py` | locks, sensors, scanner, lights, clock | how the devices are driven and read |
| 2 | `storage.py` | saving things | where records live and in what format |
| 3 | `log.py` | the permanent record | the record format |
| 4 | `link.py` | the Monitoring System | the message format and online/offline detection |
| 5 | `users.py` | who may sign in and do what | how credentials and roles are held |
| 6 | `inventory.py` | what is in each drawer | how stock is stored |
| 7 | `modes.py` | operating mode and faults | the mode table and the escalation time |
| 8 | `dispensing.py` | everything that opens a drawer | the check order and the timeouts |
| 9 | `screen.py` | what the operator sees | layout and wording |

`shared.py` holds the names they all use - it is also where the **4-variable
model** is spelled out (see the module docstring there). `cabinet.py` wires
the nine together and owns the two things that genuinely cross module
lines: `report()` (every event goes to the Log and the Link together) and
the knock-on effects of a fault (out of service, alarm, mode change).

A module may only use ones lower in this list, so there are no loops:

    screen -> dispensing -> users, inventory, modes -> link -> log
           -> storage, hardware

Every module's operations are the public methods of one class; everything
else starts with an underscore.

`demo_server.py`, `demo_monitoring.py`, and `run.py` are the demo harness,
not the product.
