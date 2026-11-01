"""HTTP/JSON transport and presentation adapter. Domain policy is in service modules."""
import csv
import hmac
import io
import json
import mimetypes
import ssl
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

STATIC=Path(__file__).parent/'static'

def make_server(service, simulator, host, port, cert=None, key=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Avoid logging credentials, cookies or request bodies.
            pass

        def reply(self,status,data,content_type='application/json',headers=None):
            body=json.dumps(data,allow_nan=False).encode() if content_type=='application/json' else data.encode() if isinstance(data,str) else data
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
            for k,v in (headers or {}).items():self.send_header(k,v)
            self.end_headers();self.wfile.write(body)

        def token(self):
            cookies=SimpleCookie();cookies.load(self.headers.get('Cookie',''))
            return cookies['hms_session'].value if 'hms_session' in cookies else ''

        def device_auth(self):
            value=self.headers.get('Authorization','')
            if not hmac.compare_digest(value,'Bearer '+service.state['device_key']):
                with service.lock:
                    service.denied('device', 'device_api', self.client_address[0], True)
                raise PermissionError('Invalid device credential')

        def body(self):
            length=int(self.headers.get('Content-Length','0'))
            if length<=0 or length>1024*1024:raise ValueError('Body must be 1 byte to 1 MiB')
            def invalid(value):raise ValueError('Non-finite JSON number')
            body=json.loads(self.rfile.read(length),parse_constant=invalid)
            if not isinstance(body,dict):raise ValueError('JSON body must be an object')
            return body

        def do_GET(self):self.handle_request(False)
        def do_POST(self):self.handle_request(True)

        def handle_request(self,post):
            try:
                host_header=self.headers.get('Host','')
                allowed_hosts={f'{host}:{self.server.server_port}',f'localhost:{self.server.server_port}',f'127.0.0.1:{self.server.server_port}'}
                if host_header not in allowed_hosts:raise PermissionError('Unexpected Host header')
                path=urlparse(self.path).path;query=parse_qs(urlparse(self.path).query)
                source=self.client_address[0]
                if post:
                    origin=self.headers.get('Origin')
                    expected=('https' if cert else 'http')+'://'+host_header
                    if origin and origin!=expected:raise PermissionError('Cross-origin request rejected')
                    if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Use application/json')
                    data=self.body()
                else:data={}
                if path.startswith('/api/device/'):
                    self.device_auth()
                    with service.lock:
                        if post and path=='/api/device/register':
                            service.register(data['cabinet_id']);result={'ok':True}
                        elif post and path=='/api/device/event':result=service.receive(data)
                        elif post and path=='/api/device/heartbeat':
                            try:
                                service.comm.answer(data['cabinet_id'],data['request_id'],data['answer'])
                            finally:
                                service.save()
                            result={'ok':True}
                        elif not post and path=='/api/device/poll':
                            cid=query.get('cabinet_id',[''])[0]
                            if cid not in service.state['cabinets']:raise ValueError('Unknown cabinet')
                            result={'heartbeat':service.comm.pending.get(cid),'commands':[c for c in service.state['commands'] if c['cabinet_id']==cid and c['state']=='queued' and service.comm.verified(cid)]}
                        elif post and path=='/api/device/command-ack':
                            result={'ok':False}
                            for command in service.state['commands']:
                                if command['id']==data['command_id'] and command['cabinet_id']==data['cabinet_id']:
                                    if command['state']!='queued':raise ValueError('Command already acknowledged')
                                    if not service.comm.verified(data['cabinet_id']):raise ValueError('Communication must be verified')
                                    if data.get('status') not in ('accepted','rejected'):raise ValueError('Invalid acknowledgement')
                                    command.update(state=data['status'],accepted_at=service.now())
                                    service.audit('command_acknowledgement',data['cabinet_id'],'device',command);service.save();result={'ok':True};break
                            if not result['ok']:raise ValueError('Unknown command')
                        else:raise ValueError('Unknown device endpoint')
                    return self.reply(200,result)
                if post and path=='/api/login':
                    token=service.login(str(data.get('username','')),str(data.get('password','')),source)
                    cookie=f'hms_session={token}; HttpOnly; SameSite=Strict; Path=/' + ('; Secure' if cert else '')
                    return self.reply(200,{'ok':True},headers={'Set-Cookie':cookie})
                if post and path=='/api/logout':
                    with service.lock:service.sessions.pop(self.token(),None)
                    return self.reply(200,{'ok':True},headers={'Set-Cookie':'hms_session=; Max-Age=0; HttpOnly; SameSite=Strict; Path=/'})
                if not post and path=='/api/state':
                    result=service.snapshot(self.token(),source)
                    if simulator and service.state['users'][result['user']]['role'] in ('administrator','technician'):
                        result['simulator']=simulator.status()
                    return self.reply(200,result)
                if post and path=='/api/action':return self.reply(200,service.action(self.token(),data['operation'],data,source))
                if post and path=='/api/simulate':
                    with service.lock:
                        user=service.authorize(self.token(),'simulate',source)
                        if not simulator:raise ValueError('Simulator is disabled')
                        service.audit('simulation_control',data['cabinet_id'],user,data)
                        result=simulator.control(data['cabinet_id'],data['operation'],data)
                    return self.reply(200,result)
                if not post and path in ('/api/history','/api/export'):
                    result=service.history(self.token(),query.get('kind',['all'])[0],int(query.get('days',['1'])[0]),source)
                    if path=='/api/history':return self.reply(200,result)
                    out=io.StringIO();writer=csv.writer(out)
                    writer.writerow(['period_start_epoch','period_end_epoch','timezone','event_id','kind','cabinet_id','actor','receipt_timestamp','details'])
                    def safe(value):
                        s=str(value or '')
                        return "'"+s if s.startswith(('=','+','-','@','\t','\r')) else s
                    for e in result['events']:writer.writerow([result['start'],result['end'],'UTC',e['id'],e['kind'],safe(e['cabinet_id']),safe(e['actor']),e['received_at'],json.dumps(e['details'])])
                    return self.reply(200,out.getvalue(),'text/csv',{'Content-Disposition':'attachment; filename=hms-report.csv'})
                if not post and path=='/api/reconstruct':
                    return self.reply(200,service.reconstruct(self.token(),query.get('cabinet_id',[''])[0],float(query.get('at',['0'])[0]),source))
                if not post and path in ('/','/app.js','/style.css'):
                    filename='index.html' if path=='/' else path[1:]
                    return self.reply(200,(STATIC/filename).read_bytes(),mimetypes.guess_type(filename)[0] or 'text/plain')
                self.reply(404,{'error':'Not found'})
            except PermissionError as exc:self.reply(403,{'error':str(exc)})
            except (ValueError,KeyError,TypeError) as exc:self.reply(400,{'error':str(exc)})
            except Exception:
                import traceback;traceback.print_exc()
                self.reply(500,{'error':'Internal error; inspect terminal log'})
    server=ThreadingHTTPServer((host,port),Handler)
    if cert:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
        server.socket=context.wrap_socket(server.socket,server_side=True)
    return server
