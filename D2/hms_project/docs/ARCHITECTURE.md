# HMS architecture

The active system is a local, single-process PyQt5 application. `run.py` creates the application service, SQLite store, and optional in-process ADC simulator, then starts the Qt event loop. No browser, web server, IP address, or HTTP request is needed for the demo.

## Runtime flow

1. [run.py](../run.py) loads configuration and creates [Store](../hms/storage.py), [HMS](../hms/service.py), and [Simulator](../hms/simulator.py).
2. [HMS](../hms/service.py) owns authentication, permissions, communication state, inventory policy, alarms, schedules, reports, and persistence.
3. [Simulator](../hms/simulator.py) produces repeatable cabinet heartbeats and inventory snapshots for two fictional ADCs. It is an adapter used for demonstration, not a real-device driver.
4. [desktop.py](../hms/desktop.py) creates the native operator window and calls the public HMS service methods.
5. Qt timers periodically call `HMS.tick()`, `Simulator.tick()`, and the UI refresh method. The UI never implements inventory or alarm policy itself.

## Layers and relationships

| Layer | Files | Purpose |
|---|---|---|
| Entry point | [run.py](../run.py) | Wires dependencies and starts Qt. |
| Presentation | [desktop.py](../hms/desktop.py) | Login, tabs, tables, buttons, reports, simulator controls and visual state. |
| Application service | [service.py](../hms/service.py) | Coordinates every workflow and exposes the state shown by the UI. |
| Policy modules | [communication.py](../hms/communication.py), [inventory.py](../hms/inventory.py), [alarms.py](../hms/alarms.py), [security.py](../hms/security.py) | Encapsulate heartbeat, freshness, stock, alarm and authorization rules. |
| Persistence | [storage.py](../hms/storage.py) | Stores users, cabinets, inventory, alarms, audit events, schedules and reports in SQLite. |
| Configuration | [config.py](../hms/config.py) | Centralizes timing values and role permissions. |
| Demonstration adapter | [simulator.py](../hms/simulator.py) | Simulates ADC messages and controlled faults without a network. |

## Main data flows

- A heartbeat enters through the simulator, is verified by `Communication`, and updates cabinet communication state in `HMS`.
- A snapshot enters through `HMS.receive()`, is validated by `Inventory`, and is accepted only when freshness and ordering rules pass.
- A low-stock or communication condition is converted into an `Alarm`; acknowledgement records the operator but does not clear source evidence.
- An operator action passes through login and `HMS.authorize()`, then updates state and an audit record in one workflow.
- The desktop reads a copied snapshot/report view and renders it. It does not access the SQLite connection directly.

## TA grading view

The strongest design evidence is the separation between UI, application coordination, policy modules and storage, plus the focused tests in [test_core.py](../tests/test_core.py). The main prototype limitations are the fictional in-process ADC adapter, known demo credentials, no production identity/deployment security, and the need for a final visual/keyboard check on the actual Windows display.

