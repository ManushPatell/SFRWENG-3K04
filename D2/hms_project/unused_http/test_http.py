import json,tempfile,threading,unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from pathlib import Path
from hms.service import HMS
from hms.storage import Store
from hms.simulator import Simulator
from hms.server import make_server
class HTTPTests(unittest.TestCase):
 def test_login_simulation_export_and_boundary(self):
  with tempfile.TemporaryDirectory() as d:
   app=HMS(Store(Path(d)/'db'));sim=Simulator(app);app.tick();sim.tick()
   server=make_server(app,sim,'127.0.0.1',0);thread=threading.Thread(target=server.serve_forever);thread.start()
   base='http://127.0.0.1:'+str(server.server_port)
   try:
    with self.assertRaises(HTTPError) as error:urlopen(base+'/api/state')
    self.assertEqual(error.exception.code,403)
    req=Request(base+'/api/login',data=json.dumps(dict(username='administrator',password='DemoOnly!2026')).encode(),headers={'Content-Type':'application/json'})
    with urlopen(req) as r:cookie=r.headers['Set-Cookie'].split(';')[0]
    with urlopen(Request(base+'/api/state',headers={'Cookie':cookie})) as r:
     state=json.load(r);self.assertEqual(len(state['cabinets']),2);self.assertNotIn('device_key',state)
    with urlopen(Request(base+'/api/export',headers={'Cookie':cookie})) as r:self.assertIn(b'event_id',r.read())
    with urlopen(base+'/app.js') as r:self.assertEqual(r.status,200)
    req=Request(base+'/api/action',data=b'{}',headers={'Cookie':cookie,'Content-Type':'application/json','Origin':'https://evil.example'})
    with self.assertRaises(HTTPError) as error:urlopen(req)
    self.assertEqual(error.exception.code,403)
   finally:server.shutdown();thread.join();server.server_close()
