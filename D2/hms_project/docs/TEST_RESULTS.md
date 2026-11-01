# Verification record — 31 October 2026

Environment: Python 3.12, Node 24 for JavaScript syntax checking.

- `python -m unittest discover -s tests -v`: 16 tests passed.
- `node --check hms/static/app.js`: passed.
- Separate server and device-client process smoke test: authenticated registration, challenge response and fresh health publication passed over loopback HTTP; both stopped cleanly.
- Python compilation passed before final behavioural test run; tests import the modified modules.

Unit scenarios cover idempotent transactions, rejected negative/NaN updates, stale timestamps, acknowledgement versus source clearance, heartbeat timeout/wrong answer/recovery/replay, cabinet isolation, command gating, three denied operations, role enforcement, restart, schedule/product conflicts, reconstruction gaps and classification boundaries. HTTP test checks login, protected state, public-view credential exclusion, CSV, static JavaScript serving and cross-origin rejection.

Browser visual and keyboard tests were attempted but could not run because the installed browser automation package has no browser binary. No visual acceptance, full accessibility conformance, hospital-scale load performance, real ADC integration, TLS setup or production security claim is made.

## Remaining team decisions

1. Agree ADC message schema, timestamps, ordering/reconciliation, timing and endpoint authentication.
2. Confirm role permissions, inventory classification rules and missing-baseline behaviour.
3. Agree response/display limits and scheduler tolerance, then benchmark against the chosen workload.
4. Review all 88 rows in TRACEABILITY.csv against D1. The worksheet distinguishes implementation from verified acceptance.
5. Perform a browser and keyboard walkthrough before the live lab demonstration.
6. Improve adapter encapsulation, remote command lifecycle and complete historical activity reconstruction if required for the final scope.
