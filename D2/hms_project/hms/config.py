"""Demo timing/policy defaults. These are proposed values, not course mandates."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    heartbeat_interval: float = 5
    heartbeat_timeout: float = 3
    freshness_limit: float = 15
    future_tolerance: float = 2
    session_seconds: float = 3600
    tick_seconds: float = 0.25

PERMISSIONS = {
    'administrator': {'view', 'acknowledge', 'threshold', 'discrepancy', 'fault', 'resolve', 'report', 'maintenance', 'schedule', 'simulate'},
    'pharmacist': {'view', 'acknowledge', 'threshold', 'discrepancy', 'fault', 'resolve', 'report', 'schedule'},
    'nurse': {'view', 'acknowledge', 'discrepancy', 'fault'},
    'technician': {'view', 'acknowledge', 'fault', 'resolve', 'report', 'maintenance', 'simulate'},
}
