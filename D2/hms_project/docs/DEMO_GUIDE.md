# TA demo guide

Start from [run.py](../run.py) in [hms_project/](..). Install `PyQt5`, run `python run.py`, and log in with the administrator demo account shown in [README.md](../README.md).

## Suggested grading walkthrough

1. Overview: identify both cabinets, their communication state, freshness, health, inventory and unresolved alarms.
2. Inventory: show cabinet isolation, locations, quantities and thresholds.
3. Simulator: dispense enough stock from ADC-01 to cross its threshold, then acknowledge the alarm. Explain that acknowledgement is not resolution.
4. Restock: provide source evidence and show the low-stock alarm resolve.
5. Communication: turn ADC-01 offline, wait for the heartbeat timeout, and show ADC-02 still monitored normally.
6. Recovery: turn ADC-01 online and show communication/freshness recover.
7. Fault distinction: demonstrate `fault` and `freeze`; explain that a good heartbeat does not erase a hardware alarm and that frozen data becomes stale.
8. History/reports: generate a report, export CSV, then restart and show SQLite persistence.
9. Code explanation: use [ARCHITECTURE.md](ARCHITECTURE.md), [MODULES.md](MODULES.md), and [TRACEABILITY.csv](TRACEABILITY.csv) to map each visible behaviour to its module.

## Questions a TA may ask

- Why no HTTP? D1 requires centralized monitoring, ADC communication, persistence and an operator interface; it does not prescribe browser/HTTP. A local UI is the simplest demo deployment.
- Where is business logic? In [service.py](../hms/service.py) and the policy modules, not in [desktop.py](../hms/desktop.py).
- What is simulated? The ADC adapter and its faults. The service, policies, alarms, SQLite persistence and UI workflows are real prototype code.
- What is not production-ready? Real ADC integration, hospital identity management, deployment security, backup replication, scale benchmarking and final acceptance of every D1 assumption.

