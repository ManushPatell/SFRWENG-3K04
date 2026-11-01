# Verification record — 31 October 2026

Environment: Python 3.13.6 with PyQt5 installed. The active application is a local desktop program; there is no Node, browser, or HTTP runtime in the demo path.

- `python -m unittest discover -s tests -v`: 15 tests passed.
- `python -m py_compile hms/desktop.py run.py`: passed.
- `git diff --check`: passed.
- VS Code Problems check for `hms/desktop.py` and `run.py`: no errors.

Unit scenarios cover idempotent transactions, rejected negative/NaN updates, stale timestamps, acknowledgement versus source clearance, heartbeat timeout/wrong answer/recovery/replay, cabinet isolation, command gating, three denied operations, role enforcement, restart, schedule/product conflicts, reconstruction gaps and classification boundaries. The PyQt5 desktop path is syntax-checked; its final visual acceptance must be performed on the Windows display used for the demo.

Headless visual rendering was not treated as acceptance evidence because font/widget rendering differs from the real Windows display. No full accessibility conformance, hospital-scale load performance, real ADC integration, network deployment, or production security claim is made.

## Remaining team decisions

1. Agree ADC message schema, timestamps, ordering/reconciliation, timing and endpoint authentication.
2. Confirm role permissions, inventory classification rules and missing-baseline behaviour.
3. Agree response/display limits and scheduler tolerance, then benchmark against the chosen workload.
4. Review all 88 rows in TRACEABILITY.csv against D1. The worksheet distinguishes implementation from verified acceptance.
5. Perform a Windows visual and keyboard walkthrough before the live lab demonstration.
6. Agree the ADC schema, timing and security boundary before any real-device integration.
