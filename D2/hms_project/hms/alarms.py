"""Alarm lifecycle policy. Acknowledgment never resolves a condition."""

import uuid


class Alarms:
    """Store alarm state and enforce acknowledgement/clearance rules."""

    def __init__(self, state, audit, now):
        """Keep references to shared state and the application audit callback."""

        self.state, self.audit, self.now = state, audit, now

    def raise_alarm(self, kind, cabinet, condition, message, severity="critical"):
        """Create an active alarm unless the same condition is already active."""

        for alarm in self.state["alarms"]:
            if (alarm["kind"], alarm["cabinet_id"], alarm["condition"]) == (
                kind,
                cabinet,
                condition,
            ) and alarm["state"] != "resolved":
                return alarm
        alarm = dict(
            id=uuid.uuid4().hex,
            kind=kind,
            cabinet_id=cabinet,
            condition=condition,
            message=message,
            severity=severity,
            state="active_unacknowledged",
            detected_at=self.now(),
            acknowledged_by=None,
            resolved_at=None,
        )
        self.state["alarms"].append(alarm)
        self.audit("alarm", cabinet, "system", alarm.copy())
        return alarm

    def acknowledge(self, alarm_id, user):
        """Record that a user saw an alarm without resolving its condition."""

        alarm = self.get(alarm_id)
        if alarm["state"] == "resolved":
            raise ValueError("Resolved alarm cannot be acknowledged")
        if alarm["state"] != "active_acknowledged":
            alarm.update(
                state="active_acknowledged",
                acknowledged_by=user,
                acknowledged_at=self.now(),
            )
            self.audit("acknowledgement", alarm["cabinet_id"], user, alarm.copy())
        return alarm

    def clear(self, kind, cabinet, condition, evidence, user="system"):
        """Resolve every active alarm matching the supplied source condition."""

        for alarm in self.state["alarms"]:
            if (alarm["kind"], alarm["cabinet_id"], alarm["condition"]) == (
                kind,
                cabinet,
                condition,
            ) and alarm["state"] != "resolved":
                alarm.update(
                    state="resolved", resolved_at=self.now(), resolution=evidence
                )
                self.audit("resolution", cabinet, user, alarm.copy())

    def get(self, alarm_id):
        """Return one alarm by identifier or report that it does not exist."""

        for alarm in self.state["alarms"]:
            if alarm["id"] == alarm_id:
                return alarm
        raise ValueError("Unknown alarm")
