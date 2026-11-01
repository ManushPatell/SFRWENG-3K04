# Module guide and implementation notes

| Module / code | Responsibility and hidden design choice | Main interface |
|---|---|---|
| Configuration, hms/config.py | Timing, role matrix; anticipated policy changes | Config; role permission sets |
| Communication, hms/communication.py | Outstanding challenge representation, timeout/freshness policy | tick(), answer(), verified(), fresh() |
| Inventory, hms/inventory.py | Classification, threshold and validation rules | validate_snapshot(), classify(), below_threshold() |
| Alarms, hms/alarms.py | Alarm lifecycle and duplicate-active-alarm policy | raise_alarm(), acknowledge(), clear() |
| Security, hms/security.py | Password derivation and role permission decisions | credential(), verify(), allowed() |
| Storage, hms/storage.py | SQLite schema, snapshot serialization | load(), save() |
| Application, hms/service.py | Serialized workflows, audit and accepted-event consistency | login(), receive(), action(), snapshot(), history(), reconstruct() |
| Transport, hms/server.py | HTTP, cookies, JSON, CSV and TLS details | make_server(); documented device endpoints |
| Presentation, hms/static/* | Browser layout, filtering and polling | HTTP application API |
| Simulator, hms/simulator.py | Fictional cabinet behaviour and fault generation | tick(), control(), status() |

Modules are design units, not a reimplementation of the D1 domain entities. Alarm states implement the D1 alarm state machine with acknowledgement separate from clearance. Communication implements unverified/available/error plus correct-response recovery. Inventory actions implement validation, location threshold checking, alarm generation and history recording.

## Current encapsulation limit

The application owns the mutable state and passes internal references to its policy collaborators. This is deliberate internal composition, but server.py and simulator.py also currently access application state for device commands and the demo adapter. For a stronger information-hiding demonstration, extract public device polling/command-ack operations before expanding these adapters. The browser receives copied public views and never gets user password hashes or device credentials. Treat modularity as a working baseline, not a perfect rubric score.

## Role matrix

All roles can view, acknowledge, report a discrepancy and report a fault. Administrator has every operation. Pharmacist additionally changes thresholds, resolves manually clearable alarms, generates reports and manages schedules. Technician additionally resolves alarms, generates reports, records maintenance and operates the simulator. Nurse has no additional operations. These assignments are provisional assumptions, not hospital policy.

## D2 four-variable framing (once)

- Monitored: actual cabinet stock, hardware/sensor/power condition, cabinet availability and operator intentions in the environment.
- Inputs: timestamped ADC messages, heartbeat responses and authenticated operator requests received by HMS.
- Outputs: dashboard/API/report values, alarms and queued supervisory configuration requests.
- Controlled: information and alarm indications presented to operators; supervisory configuration delivered to cabinets. Physical dispensing/locks are outside this HMS boundary.
- NAT: messages can be delayed, lost or repeated; the cabinet owns physical measurement and actuation; communication failure does not prove hardware failure. Simulator assumptions approximate these environmental constraints.
- REQ: accurately expose accepted reports and their freshness, preserve unresolved alarms, prevent unverified supervisory dispatch and retain traceable history. Input/output accuracy depends on the stated environmental and adapter assumptions.

## Five precise specification candidates

These are behavioural contracts for the safety-critical subset, for review in the report.

### PS-01: Heartbeat verification and gated dispatch

Pre: registered cabinet c; outstanding request r with deadline d. Post: a response verifies c iff its request identifier matches r, its integer answer is correct and receipt time t < d. A wrong answer or timeout sets communication error and raises an alarm. Recovery requires a valid new response. Invariant: no supervisory command is returned for dispatch unless verified(c); heartbeat success does not change cabinet health. Timing detection is on the next scheduler tick, a disclosed PER-01 gap.

### PS-02: Freshness and rejected updates

Pre: registered source and syntactically valid envelope. Post: accept only finite source timestamp s satisfying now-s < freshness_limit and s <= now+future_tolerance, and no regression for a category; otherwise preserve accepted quantities/status and record the rejection. Invariant: display current only with verified communication and source age in [0, freshness_limit). Missing or stale information is visibly identified and alerted. Future-tolerated data is not current until its timestamp is reached.

### PS-03: Inventory conservation and idempotence

Pre: authenticated device, known location/product and positive integer transaction quantity q. Post: for a new valid dispense event Q'=Q-q >=0; restock Q'=Q+q; persist event and resulting state together. Repeated (cabinet,event_id) leaves quantity and transaction count unchanged. Invalid events leave accepted inventory unchanged and create rejection evidence. Invariant: quantities are nonnegative integers; location key is cabinet/drawer/pocket.

### PS-04: Alarm acknowledgement

Pre: authorized user and existing unresolved alarm a. Post: a.state=active_acknowledged and acknowledgement actor/time recorded; all inventory, health and communication values unchanged. Invariant: acknowledgement never resolves an alarm. Source-driven alarms require confirming source evidence; manually clearable incidents require authorized recorded resolution evidence.

### PS-05: Location threshold alarm

Pre: validated quantity Q, location threshold T with unit quantity or percent; percent requires valid full-stock baseline F>0. Post: raise/retain active low-stock alarm iff Q<=T (quantity) or 100Q/F<=T (percent); clear on a valid above-threshold observation. Missing T raises configuration alert. Invariant: alarm comparison uses the affected location's own threshold. Missing percentage baseline yields unavailable comparison and a configuration alert.
