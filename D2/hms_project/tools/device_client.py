"""Standalone transport example, run from the project directory. Fictional device only."""
import argparse,json,os,sqlite3,time,uuid
from urllib.request import Request,urlopen
p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8765');p.add_argument('--cabinet',default='EXTERNAL-01');p.add_argument('--database',default='data/hms.sqlite3');a=p.parse_args()
token=os.environ.get('HMS_DEVICE_TOKEN')
if not token:
    with sqlite3.connect(a.database) as db: state=json.loads(db.execute('SELECT body FROM snapshot WHERE id=1').fetchone()[0])
    token=state['device_key'];sequence=state['sequence'].get(a.cabinet,0)
else:sequence=int(os.environ.get('HMS_DEVICE_SEQUENCE','0'))
def request(path,data=None):
    req=Request(a.url+'/api/device/'+path,data=None if data is None else json.dumps(data).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    with urlopen(req,timeout=3) as r:return json.load(r)
request('register',{'cabinet_id':a.cabinet});print('Device connected. Ctrl+C stops heartbeats and updates. No physical hardware is controlled.')
start=time.time();last=0
try:
    while True:
        result=request('poll?cabinet_id='+a.cabinet)
        challenge=result['heartbeat']
        if challenge:request('heartbeat',dict(cabinet_id=a.cabinet,request_id=challenge['request_id'],answer=challenge['a']+challenge['b']))
        for command in result['commands']:
            request('command-ack',dict(cabinet_id=a.cabinet,command_id=command['id'],status='accepted'))
        if time.time()-last>=3:
            for kind,data in [('health',dict(operational_status='operational',power='ok',hardware='ok',sensors='ok',backup='unsupported',cooling='unsupported',uptime=time.time()-start,unsafe=False)),('inventory',{'locations':[dict(drawer_id='D1',pocket_id='P1',medication_id='EXAMPLE',name='Fictional product',din='DEMO',strength='1 demo unit',dosage_form='demo tablet',quantity=50,full_stock=100,threshold=20)]})]:
                sequence+=1
                request('event',dict(cabinet_id=a.cabinet,event_id=uuid.uuid4().hex,sequence=sequence,timestamp=time.time(),type=kind,data=data))
            last=time.time()
        time.sleep(.5)
except KeyboardInterrupt:print('Device stopped.')
