"""Application orchestration. Public operations serialize changes under one lock."""
import copy
import json
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from .config import Config
from .security import credential, verify, allowed
from .inventory import number, integer, text, location_key, percentage, classify, below_threshold, validate_snapshot
from .alarms import Alarms
from .communication import Communication

class HMS:
    def __init__(self, store, config=None, clock=time.time):
        self.store, self.config, self.now = store, config or Config(), clock
        self.lock = threading.RLock()
        self.sessions = {}
        self.state = store.load() or self.initial_state()
        self.alarms = Alarms(self.state, self.audit, clock)
        self.comm = Communication(self.state['cabinets'], self.alarms, self.audit, clock, self.config)
        self.save()

    def initial_state(self):
        return {'cabinets': {}, 'locations': {}, 'alarms': [], 'events': [], 'seen': [], 'sequence': {},
                'gaps': [], 'schedules': {}, 'commands': [], 'denials': {}, 'users': {role: {'role': role, **credential('DemoOnly!2026')} for role in
                ('administrator', 'pharmacist', 'nurse', 'technician')}, 'device_key': secrets.token_urlsafe(32)}

    def save(self):
        self.store.save(self.state)

    def audit(self, kind, cabinet, actor, details):
        event = dict(id=uuid.uuid4().hex, kind=kind, cabinet_id=cabinet, actor=actor,
                     received_at=self.now(), details=copy.deepcopy(details))
        self.state['events'].append(event)
        return event

    def register(self, cid):
        text(cid, 'cabinet_id')
        if '|' in cid:
            raise ValueError('cabinet_id must not contain |')
        if cid not in self.state['cabinets']:
            self.state['cabinets'][cid] = dict(cabinet_id=cid, communication='unverified', verified_at=None,
                inventory_at=None, health_at=None, operational_status='unknown', health={}, maintenance_at=None)
            self.audit('registration', cid, 'system', {})
            self.save()

    def denied(self, user, operation, source, authentication=False):
        key = f'{source}:{user}'
        count = self.state['denials'].get(key, 0) + 1
        self.state['denials'][key] = count
        self.audit('authentication_failure' if authentication else 'authorization_failure', None, user,
                   {'operation': operation, 'source': source, 'consecutive_denials': count})
        if count >= 3:
            self.alarms.raise_alarm('security', None, key, f'Three or more consecutive denials for {user} from {source}')
        self.save()

    def login(self, username, password, source='local'):
        with self.lock:
            record = self.state['users'].get(username)
            if not record or not verify(password, record):
                self.denied(username, 'login', source, True)
                raise PermissionError('Invalid username or password')
            self.state['denials'][f'{source}:{username}'] = 0
            token = secrets.token_urlsafe(32)
            self.sessions[token] = (username, self.now() + self.config.session_seconds)
            self.audit('login', None, username, {'source': source})
            self.save()
            return token

    def authorize(self, token, operation, source='local'):
        with self.lock:
            session = self.sessions.get(token)
            if not session or self.now() >= session[1]:
                self.sessions.pop(token, None)
                self.denied('anonymous', operation, source, True)
                raise PermissionError('Login required or session expired')
            user = session[0]
            if not allowed(self.state['users'][user]['role'], operation):
                self.denied(user, operation, source)
                raise PermissionError('Your role does not permit this operation')
            # Count consecutive protected-operation denials; success resets that scope.
            self.state['denials'][f'{source}:{user}'] = 0
            return user

    def tick(self):
        with self.lock:
            self.comm.tick()
            self.save()

    def receive(self, envelope):
        """Validate before mutation; persist accepted event and effects together."""
        with self.lock:
            before = copy.deepcopy(self.state)
            try:
                json.dumps(envelope, allow_nan=False)
                return self._receive(envelope)
            except (ValueError, TypeError, KeyError) as exc:
                # Restore mutable state in-place so policies retain their references.
                self.state.clear(); self.state.update(before)
                self.comm.cabinets = self.state['cabinets']
                cid = envelope.get('cabinet_id') if isinstance(envelope, dict) else None
                self.audit('rejected_update', cid, 'device', {'reason': str(exc), 'message': repr(envelope)})
                if 'Conflicting medication' in str(exc):
                    self.alarms.raise_alarm('medication_conflict', cid, 'product_metadata', str(exc))
                if 'timestamp' in str(exc) and cid in self.state['cabinets']:
                    self.alarms.raise_alarm('stale_data', cid, str(envelope.get('type')), str(exc), 'warning')
                self.save()
                raise ValueError(str(exc)) from exc

    def _receive(self, e):
        if not isinstance(e, dict):
            raise ValueError('Message must be an object')
        cid = text(e.get('cabinet_id'), 'cabinet_id')
        if cid not in self.state['cabinets']:
            raise ValueError('Unknown cabinet')
        event_id = text(e.get('event_id'), 'event_id')
        identity = [cid, event_id]
        if identity in self.state['seen']:
            return {'accepted': True, 'duplicate': True}
        seq = integer(e.get('sequence'), 'sequence', 1)
        last = self.state['sequence'].get(cid, 0)
        if seq <= last:
            raise ValueError('Out-of-order sequence: replay requires reconciliation')
        stamp = number(e.get('timestamp'), 'timestamp')
        if stamp > self.now() + self.config.future_tolerance or self.now() - stamp >= self.config.freshness_limit:
            raise ValueError('Source timestamp is stale or outside permitted future tolerance')
        kind = e.get('type'); data = e.get('data')
        if not isinstance(data, dict):
            raise ValueError('data must be an object')
        cabinet = self.state['cabinets'][cid]
        if kind in ('inventory', 'health') and cabinet.get(kind + '_at') is not None and stamp < cabinet[kind + '_at']:
            raise ValueError('Source timestamp predates accepted update')
        if kind == 'inventory':
            validate_snapshot(data)
            for incoming in data['locations']:
                key = location_key(cid, incoming['drawer_id'], incoming['pocket_id'])
                previous = self.state['locations'].get(key)
                for loc in self.state['locations'].values():
                    if loc['medication_id'] == incoming['medication_id'] and any(loc.get(f) != incoming.get(f) for f in ('name', 'din', 'strength', 'dosage_form')):
                        raise ValueError('Conflicting medication product data')
                loc = dict(incoming, cabinet_id=cid, key=key, updated_at=stamp, lot=incoming.get('lot'))
                if previous:
                    loc['threshold'] = previous.get('threshold')
                    loc['threshold_type'] = previous.get('threshold_type', 'quantity')
                else:
                    loc.setdefault('threshold_type', 'quantity')
                self.state['locations'][key] = loc
                self.stock_alarm(loc)
            cabinet['inventory_at'] = stamp
        elif kind in ('dispense', 'restock'):
            key = location_key(cid, text(data.get('drawer_id'), 'drawer_id'), text(data.get('pocket_id'), 'pocket_id'))
            loc = self.state['locations'].get(key)
            if not loc or data.get('medication_id') != loc['medication_id']:
                raise ValueError('Unknown or mismatched inventory location/product')
            amount = integer(data.get('quantity'), 'quantity', 1)
            text(data.get('operator_id'), 'operator_id')
            if stamp < loc['updated_at']:
                raise ValueError('Transaction timestamp predates inventory')
            new = loc['quantity'] + (amount if kind == 'restock' else -amount)
            if new < 0:
                raise ValueError('Dispense would produce negative stock')
            loc.update(quantity=new, updated_at=stamp)
            if data.get('lot') is not None: loc['lot'] = data['lot']
            data = dict(data, lot=data.get('lot', loc.get('lot')), patient_id=data.get('patient_id'), resulting_quantity=new)
            self.stock_alarm(loc)
            # A transaction updates one location, not the freshness of the whole cabinet snapshot.
        elif kind == 'health':
            if data.get('operational_status') not in ('operational', 'maintenance', 'fault'):
                raise ValueError('Invalid operational_status')
            for field in ('power', 'hardware', 'sensors', 'backup', 'cooling'):
                if data.get(field) not in ('ok', 'failed', 'unsupported', 'unknown'):
                    raise ValueError(f'Invalid {field} status')
            number(data.get('uptime'), 'uptime')
            if type(data.get('unsafe')) is not bool:
                raise ValueError('unsafe must be Boolean')
            cabinet.update(health=copy.deepcopy(data), health_at=stamp, operational_status=data['operational_status'])
            for field in ('power', 'hardware', 'sensors', 'backup', 'cooling'):
                if data[field] == 'failed':
                    self.alarms.raise_alarm('device_failure', cid, field, f'{field} reports failure')
                elif data[field] == 'ok':
                    self.alarms.clear('device_failure', cid, field, f'Fresh {field}=ok report')
            if data['unsafe']:
                self.alarms.raise_alarm('unsafe_state', cid, 'unsafe', 'ADC reports an unsafe condition')
            else:
                self.alarms.clear('unsafe_state', cid, 'unsafe', 'Fresh ADC report confirms unsafe condition cleared')
        elif kind == 'maintenance':
            text(data.get('activity'), 'activity'); text(data.get('operator_id'), 'operator_id')
            cabinet['maintenance_at'] = stamp
        elif kind == 'alarm':
            alarm_kind = text(data.get('kind'), 'kind')
            if alarm_kind not in ('device_failure', 'unsafe_state', 'discrepancy'):
                raise ValueError('Unsupported device alarm kind')
            self.alarms.raise_alarm(alarm_kind, cid, text(data.get('condition'), 'condition'), text(data.get('message'), 'message'))
        else:
            raise ValueError('Unsupported message type')
        if seq != last + 1:
            self.state['gaps'].append(dict(cabinet_id=cid, after=last, before=seq, timestamp=stamp))
        self.state['sequence'][cid] = seq
        self.state['seen'].append(identity)
        self.audit(kind, cid, data.get('operator_id', 'device'), dict(data, event_id=event_id, sequence=seq, timestamp=stamp))
        if kind in ('inventory', 'health'):
            self.alarms.clear('stale_data', cid, kind, 'Fresh valid update received')
        self.save()
        return {'accepted': True, 'duplicate': False}

    def stock_alarm(self, loc):
        cid, key = loc['cabinet_id'], loc['key']
        if loc.get('threshold') is None or (loc.get('threshold_type') == 'percent' and percentage(loc['quantity'], loc.get('full_stock')) is None):
            self.alarms.raise_alarm('configuration', cid, key, f'Missing restock threshold or percentage baseline at {key}', 'warning')
        else:
            self.alarms.clear('configuration', cid, key, 'Threshold configured')
        low = below_threshold(loc)
        if low is True:
            self.alarms.raise_alarm('low_stock', cid, key, f'Restock threshold reached at {key}', 'warning')
        elif low is False:
            self.alarms.clear('low_stock', cid, key, 'Recorded stock is above the configured threshold')

    def action(self, token, operation, data, source='local'):
        with self.lock:
            user = self.authorize(token, operation, source)
            result = {'ok': True}
            if operation == 'acknowledge':
                result = self.alarms.acknowledge(data['alarm_id'], user)
            elif operation == 'threshold':
                loc = self.state['locations'][data['location']]
                value = number(data['threshold'], 'threshold')
                mode = data.get('threshold_type', 'quantity')
                if mode not in ('quantity', 'percent') or (mode == 'percent' and value > 100):
                    raise ValueError('Threshold must be quantity or percent (0–100)')
                # This changes supervisory configuration and is sent to the target cabinet.
                if not self.comm.verified(loc['cabinet_id']):
                    raise ValueError('Blocked: cabinet communication is unverified or unavailable')
                loc.update(threshold=value, threshold_type=mode)
                self.stock_alarm(loc)
                cmd = dict(id=uuid.uuid4().hex, cabinet_id=loc['cabinet_id'], operation='set_threshold',
                           data=dict(data), state='queued', created_at=self.now())
                self.state['commands'].append(cmd)
                self.audit('threshold_change', loc['cabinet_id'], user, dict(data, command_id=cmd['id']))
                result = dict(ok=True, command_id=cmd['id'], command_state='queued')
            elif operation == 'discrepancy':
                loc = self.state['locations'][data['location']]
                observed = integer(data['observed'], 'observed')
                if observed == loc['quantity']:
                    raise ValueError('Observed and recorded stock match')
                self.alarms.raise_alarm('discrepancy', loc['cabinet_id'], loc['key'], f"Observed {observed}; recorded {loc['quantity']} at {loc['key']}")
                self.audit('discrepancy_report', loc['cabinet_id'], user, data)
            elif operation == 'fault':
                cid = data['cabinet_id']; self.state['cabinets'][cid]
                self.alarms.raise_alarm('manual_fault', cid, uuid.uuid4().hex, text(data['message'], 'message'))
                self.audit('manual_fault', cid, user, data)
            elif operation == 'resolve':
                alarm = self.alarms.get(data['alarm_id'])
                if alarm['kind'] not in ('manual_fault', 'discrepancy', 'security', 'schedule_conflict', 'medication_conflict'):
                    raise ValueError('This alarm requires fresh source evidence, not manual clearance')
                evidence = text(data.get('evidence'), 'resolution evidence')
                self.alarms.clear(alarm['kind'], alarm['cabinet_id'], alarm['condition'], evidence, user)
            elif operation == 'maintenance':
                cid = data['cabinet_id']; self.state['cabinets'][cid]
                activity = text(data['activity'], 'activity')
                self.state['cabinets'][cid]['maintenance_at'] = self.now()
                self.audit('maintenance', cid, user, dict(activity=activity, operator_id=user, timestamp=self.now()))
            elif operation == 'schedule':
                result = self.schedule(data, user)
            else:
                raise ValueError('Unsupported operation')
            self.save()
            return copy.deepcopy(result)

    def schedule(self, data, user):
        for field in ('record_id', 'patient_id', 'medication_id'):
            text(data.get(field), field)
        start, end = number(data.get('start'), 'start'), number(data.get('end'), 'end')
        if end <= start:
            raise ValueError('Schedule end must be after start')
        for old in self.state['schedules'].values():
            if old['record_id'] != data['record_id'] and (old['patient_id'], old['medication_id']) == (data['patient_id'], data['medication_id']) and max(start, old['start']) < min(end, old['end']):
                self.alarms.raise_alarm('schedule_conflict', None, data['record_id'], f"Overlapping records {old['record_id']} and {data['record_id']}")
                self.audit('rejected_update', None, user, dict(reason='overlapping patient/product intervals', message=data))
                return {'ok': False, 'reason': 'Conflicting schedule rejected'}
        self.state['schedules'][data['record_id']] = copy.deepcopy(data)
        self.alarms.clear('schedule_conflict', None, data['record_id'], 'Corrected schedule accepted', user)
        self.audit('schedule', None, user, data)
        return {'ok': True}

    def snapshot(self, token, source='local'):
        with self.lock:
            user = self.authorize(token, 'view', source)
            cabinets = copy.deepcopy(list(self.state['cabinets'].values()))
            for c in cabinets:
                cid = c['cabinet_id']
                c['inventory_fresh'] = self.comm.fresh(cid, 'inventory')
                c['health_fresh'] = self.comm.fresh(cid, 'health')
                if not self.comm.verified(cid) and c['communication'] == 'available': c['communication'] = 'unverified'
                c['maintenance_age_seconds'] = None if c['maintenance_at'] is None else max(0, self.now()-c['maintenance_at'])
            locations = copy.deepcopy(list(self.state['locations'].values()))
            for loc in locations:
                loc['classification'] = classify(loc['quantity'], loc.get('full_stock'))
                loc['percentage'] = percentage(loc['quantity'], loc.get('full_stock'))
                loc['fresh'] = self.comm.fresh(loc['cabinet_id'], 'inventory') and self.now()-loc['updated_at'] < self.config.freshness_limit
            return dict(user=user, role=self.state['users'][user]['role'], now=self.now(), cabinets=cabinets,
                locations=locations, alarms=copy.deepcopy(self.state['alarms']), commands=copy.deepcopy(self.state['commands']),
                schedules=copy.deepcopy(list(self.state['schedules'].values())))

    def history(self, token, kind='all', days=1, source='local'):
        with self.lock:
            self.authorize(token, 'report', source)
            if days not in (1, 7): raise ValueError('Report period must be 1 or 7 days')
            end = self.now(); start = end - days * 86400
            events = [copy.deepcopy(e) for e in self.state['events'] if start <= e['received_at'] <= end and (kind == 'all' or e['kind'] == kind)]
            return dict(start=start, end=end, timezone='UTC', time_basis='receipt timestamp', events=events)

    def reconstruct(self, token, cid, at, source='local'):
        with self.lock:
            self.authorize(token, 'report', source);number(at,'at')
            rows = {}; baseline = False
            for event in self.state['events']:
                d = event['details']; stamp = d.get('timestamp', event['received_at'])
                if event['cabinet_id'] != cid or stamp > at: continue
                if event['kind'] == 'inventory':
                    for loc in d['locations']:
                        rows[location_key(cid,loc['drawer_id'],loc['pocket_id'])] = loc['quantity']
                    baseline = True
                elif event['kind'] in ('dispense','restock'):
                    rows[location_key(cid,d['drawer_id'],d['pocket_id'])] = d['resulting_quantity']
            gaps = [g for g in self.state['gaps'] if g['cabinet_id']==cid and g['timestamp']<=at]
            return dict(cabinet_id=cid, at=at, quantities=rows, incomplete=not baseline or bool(gaps), known_gaps=copy.deepcopy(gaps))
