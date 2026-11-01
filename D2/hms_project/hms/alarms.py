"""Alarm lifecycle policy. Acknowledgment never resolves a condition."""
import uuid

class Alarms:
    def __init__(self, state, audit, now):
        self.state, self.audit, self.now = state, audit, now

    def raise_alarm(self, kind, cabinet, condition, message, severity='critical'):
        for alarm in self.state['alarms']:
            if (alarm['kind'], alarm['cabinet_id'], alarm['condition']) == (kind, cabinet, condition) and alarm['state'] != 'resolved':
                return alarm
        alarm = dict(id=uuid.uuid4().hex, kind=kind, cabinet_id=cabinet, condition=condition,
                     message=message, severity=severity, state='active_unacknowledged', detected_at=self.now(),
                     acknowledged_by=None, resolved_at=None)
        self.state['alarms'].append(alarm)
        self.audit('alarm', cabinet, 'system', alarm.copy())
        return alarm

    def acknowledge(self, alarm_id, user):
        alarm = self.get(alarm_id)
        if alarm['state'] == 'resolved':
            raise ValueError('Resolved alarm cannot be acknowledged')
        if alarm['state'] != 'active_acknowledged':
            alarm.update(state='active_acknowledged', acknowledged_by=user, acknowledged_at=self.now())
            self.audit('acknowledgement', alarm['cabinet_id'], user, alarm.copy())
        return alarm

    def clear(self, kind, cabinet, condition, evidence, user='system'):
        for alarm in self.state['alarms']:
            if (alarm['kind'], alarm['cabinet_id'], alarm['condition']) == (kind, cabinet, condition) and alarm['state'] != 'resolved':
                alarm.update(state='resolved', resolved_at=self.now(), resolution=evidence)
                self.audit('resolution', cabinet, user, alarm.copy())

    def get(self, alarm_id):
        for alarm in self.state['alarms']:
            if alarm['id'] == alarm_id:
                return alarm
        raise ValueError('Unknown alarm')
