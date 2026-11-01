"""Heartbeat/freshness policy. Wire encoding lives in server.py/transport adapter."""
import secrets

class Communication:
    def __init__(self, cabinets, alarms, audit, now, config):
        self.cabinets, self.alarms, self.audit, self.now, self.config = cabinets, alarms, audit, now, config
        self.pending = {}
        self.next_due = {}
        # Persisted healthy state is not evidence of a live connection after restart.
        for cabinet in cabinets.values():
            cabinet['communication'] = 'unverified'
            cabinet['verified_at'] = None

    def tick(self):
        now = self.now()
        for cid, cabinet in self.cabinets.items():
            pending = self.pending.get(cid)
            if pending and now >= pending['deadline']:
                self.fail(cid, 'Heartbeat response timeout')
            if cid not in self.pending and now >= self.next_due.get(cid, 0):
                a, b = secrets.randbelow(100), secrets.randbelow(100)
                self.pending[cid] = {'request_id': secrets.token_hex(12), 'a': a, 'b': b, 'operator': '+',
                                     'sent_at': now, 'deadline': now + self.config.heartbeat_timeout}
                self.next_due[cid] = now + self.config.heartbeat_interval
            for category in ('inventory', 'health'):
                stamp = cabinet.get(category + '_at')
                if stamp is None or now - stamp >= self.config.freshness_limit:
                    self.alarms.raise_alarm('stale_data', cid, category, f'{category}: missing or stale update', 'warning')

    def fail(self, cid, reason):
        self.cabinets[cid]['communication'] = 'error'
        self.pending.pop(cid, None)
        self.alarms.raise_alarm('communication', cid, 'heartbeat', reason)

    def answer(self, cid, request_id, answer):
        challenge = self.pending.get(cid)
        if challenge is None or challenge['request_id'] != request_id:
            raise ValueError('No matching outstanding heartbeat')
        if self.now() >= challenge['deadline']:
            self.fail(cid, 'Late heartbeat response')
            raise ValueError('Heartbeat response expired')
        if isinstance(answer, bool) or not isinstance(answer, int) or answer != challenge['a'] + challenge['b']:
            self.fail(cid, 'Incorrect heartbeat answer')
            raise ValueError('Incorrect heartbeat answer')
        self.pending.pop(cid)
        self.cabinets[cid].update(communication='available', verified_at=self.now())
        self.alarms.clear('communication', cid, 'heartbeat', 'Correct matching heartbeat received before deadline')
        # Does not alter cabinet health, operational status or data timestamps.

    def verified(self, cid):
        c = self.cabinets[cid]
        stamp = c.get('verified_at')
        return c['communication'] == 'available' and stamp is not None and self.now() - stamp < self.config.heartbeat_interval + self.config.heartbeat_timeout

    def fresh(self, cid, category):
        stamp = self.cabinets[cid].get(category + '_at')
        return self.verified(cid) and stamp is not None and 0 <= self.now() - stamp < self.config.freshness_limit
