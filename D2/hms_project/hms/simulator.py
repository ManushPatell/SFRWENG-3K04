"""Replaceable ADC simulator. Controls represent external device events, not dispensing commands."""
import copy
import uuid

class Simulator:
    def __init__(self, service):
        self.service = service
        self.devices = {}
        for cid in ('ADC-01', 'ADC-02'):
            service.register(cid)
            persisted = [copy.deepcopy(loc) for loc in service.state['locations'].values() if loc['cabinet_id'] == cid]
            locations = persisted or [dict(drawer_id='D1', pocket_id='P1', medication_id='MED-DEMO-01',
                name='Training product (fictional)', din='DEMO-NOT-A-DIN', strength='Demo strength', dosage_form='Training tablet',
                quantity=80 if cid=='ADC-01' else 40, full_stock=100, threshold=20, threshold_type='quantity', lot='DEMO-LOT-A')]
            self.devices[cid] = dict(online=True, wrong_answer=False, freeze=False, fault=False, unsafe=False,
                locations=locations, sequence=service.state['sequence'].get(cid,0), last_publish=-100,
                started=service.now(), last_event=None)

    def send(self, cid, kind, data):
        device = self.devices[cid]
        if not device['online']: raise ValueError('Simulated cabinet is disconnected')
        device['sequence'] += 1
        e=dict(cabinet_id=cid,event_id=uuid.uuid4().hex,sequence=device['sequence'],timestamp=self.service.now(),type=kind,data=copy.deepcopy(data))
        result = self.service.receive(e)
        device['last_event'] = e
        return result

    def tick(self):
        with self.service.lock:
            for cid, dev in self.devices.items():
                if not dev['online']: continue
                pending = self.service.comm.pending.get(cid)
                if pending:
                    try:
                        self.service.comm.answer(cid,pending['request_id'], pending['a']+pending['b']+(1 if dev['wrong_answer'] else 0))
                    except ValueError:
                        pass
                if not dev['freeze'] and self.service.now()-dev['last_publish']>=3:
                    health=dict(power='ok',backup='unsupported',cooling='unsupported',hardware='failed' if dev['fault'] else 'ok',
                        sensors='ok',operational_status='fault' if dev['fault'] or dev['unsafe'] else 'operational',
                        uptime=max(0,self.service.now()-dev['started']),unsafe=dev['unsafe'])
                    self.send(cid,'health',health)
                    self.send(cid,'inventory',{'locations':dev['locations']})
                    dev['last_publish']=self.service.now()
                for command in self.service.state['commands']:
                    if command['cabinet_id']==cid and command['state']=='queued' and self.service.comm.verified(cid):
                        command.update(state='accepted', accepted_at=self.service.now())
                        self.service.audit('command_acknowledgement',cid,'simulator',command)
            self.service.save()

    def control(self, cid, operation, data):
        with self.service.lock:
            dev=self.devices[cid]
            if operation in ('online','wrong_answer','freeze','fault','unsafe'):
                if type(data.get('value')) is not bool: raise ValueError('value must be Boolean')
                dev[operation]=data['value']
                if operation in ('online','freeze','fault','unsafe'): dev['last_publish']=-100
            elif operation in ('dispense','restock'):
                loc=dev['locations'][0]
                result=self.send(cid,operation,dict(drawer_id=loc['drawer_id'],pocket_id=loc['pocket_id'],medication_id=loc['medication_id'],
                    quantity=data.get('quantity',1),operator_id='SIM-OPERATOR',patient_id=None,lot=loc.get('lot')))
                # Read back accepted quantity; no second application of the delta.
                actual=self.service.state['locations'][cid+'|'+loc['drawer_id']+'|'+loc['pocket_id']]
                loc['quantity']=actual['quantity']
                return result
            elif operation=='duplicate':
                if dev['last_event'] is None: raise ValueError('No prior event')
                return self.service.receive(dev['last_event'])
            elif operation=='invalid':
                return self.send(cid,'inventory',{'locations':[dict(dev['locations'][0],quantity=-1)]})
            elif operation=='maintenance':
                return self.send(cid,'maintenance',{'activity':'Simulated inspection completed','operator_id':'SIM-TECH'})
            else: raise ValueError('Unknown simulator operation')
            return {'ok':True}

    def status(self):
        return {cid:{k:dev[k] for k in ('online','wrong_answer','freeze','fault','unsafe')} for cid,dev in self.devices.items()}
