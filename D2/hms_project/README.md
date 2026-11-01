# Hospital Monitoring System — D2 code prototype

Python 3.10 or newer. The desktop interface uses PyQt5. No cloud service or separate database setup is required. All medications and patients used in the simulator are fictional.

## Start

Extract the ZIP, open a terminal in `hms_project`, then run:

Windows: `py -3 run.py`

macOS/Linux: `python3 run.py`

The application opens as a native PyQt5 desktop window. Select administrator and use password `DemoOnly!2026`. The same demo password applies to pharmacist, nurse and technician. Close the window to stop. Records persist in `data/hms.sqlite3`; use `--database data/another-demo.sqlite3` for a separate clean demo. Do not delete an existing database unless its records are no longer wanted.

Install the interface dependency with `python -m pip install PyQt5`, then run tests with `python -m unittest discover -s tests -v` (Windows may use `py -3`).

## Included

- Two independently simulated Automated Dispensing Cabinets (ADCs), challenge-response heartbeats and recovery.
- Inventory, quantities, thresholds, alternate locations, discrepancy reports, dispense/restock history.
- Alarm acknowledgement distinct from resolution, failures, stale data and security-denial alarms.
- Cabinet health, maintenance, daily/weekly rolling reports, CSV export and inventory reconstruction.
- Role restrictions, SQLite persistence, in-process cabinet simulation, reproducible fault controls.
- Module guide, five precise contracts, complete 88-row requirement coverage worksheet, demo walkthrough and tests.

## Important status

This is a course prototype, not clinical software. It implements a local simulated ADC interface; the ADC sub-team must agree to its schema, timing and security before integration. A mathematical heartbeat checks responsiveness, not identity or security. Per-device credentials, real identity management, hospital integrations, backup replication and production security are not implemented.

The demo uses known user passwords and fictional data only. Historical state grows without a retention policy; performance at hospital scale is unverified. The tests cover core behaviour; a full visual/keyboard desktop acceptance pass is still required. See the coverage worksheet for other partial items. Do not present all requirements as verified complete.

## Live demonstration

1. Start before your lab presentation. Log in as administrator. Overview shows two cabinets and separate communication, operational and freshness indicators.
2. Inventory shows ADC-01 at 80 units and ADC-02 at 40 on a clean run, both threshold 20. In Simulator, dispense 65 from ADC-01. Check quantity 15 and low-stock alarm.
3. In Alarms acknowledge that alarm. It remains active. Restock 20 from Simulator; source evidence now resolves it.
4. Turn ADC-01 `online` OFF. After the next heartbeat and timeout, communication becomes error. ADC-02 remains monitored. Retained quantities stay visible with stale/unavailable labels.
5. Turn `online` ON. The next valid heartbeat restores communication; fresh snapshots restore current data. Set `fault` ON: a good heartbeat must not clear that hardware alarm. Set `fault` OFF to send actual recovery evidence.
6. Set `freeze` ON: heartbeats still succeed but health/inventory age to stale after 15 seconds. Turn it OFF to recover.
7. Use duplicate/invalid update controls. Duplicate events must not double-count stock; invalid snapshots must preserve accepted data and appear in rejected-update history.
8. Request a daily dispense report and download CSV. Stop/restart; records persist, and communication is reverified.
9. Explain which module hides each policy. For an on-the-spot heartbeat timing change, identify config.py, Communication, the timing tests and affected traceability rows.

These are prototype defaults: heartbeat interval 5 s; timeout 3 s; freshness 15 s; future timestamp allowance 2 s; simulator publication 3 s; desktop refresh 1 s. Timeout detection occurs on the next 0.25 s scheduler tick, so PER-01 has a bounded scheduling tolerance to agree with the instructor/ADC team.

D2 handout says show code live; submit the design document through the prescribed submission box. This package supports both preparation tasks and is not itself the finished design report.
