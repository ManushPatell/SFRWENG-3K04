"""Run with Python 3.10+; only standard-library dependencies."""
import argparse
import threading
import webbrowser
from pathlib import Path
from hms.service import HMS
from hms.storage import Store
from hms.simulator import Simulator
from hms.server import make_server

def main():
    parser=argparse.ArgumentParser(description='HMS course prototype')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--database',default=str(Path(__file__).parent/'data'/'hms.sqlite3'))
    parser.add_argument('--no-simulator',action='store_true')
    parser.add_argument('--open',action='store_true',help='Open default browser')
    parser.add_argument('--cert');parser.add_argument('--key')
    args=parser.parse_args()
    if bool(args.cert)!=bool(args.key):parser.error('--cert and --key must be supplied together')
    app=HMS(Store(args.database));sim=None if args.no_simulator else Simulator(app)
    app.tick()
    if sim:sim.tick()
    server=make_server(app,sim,'127.0.0.1',args.port,args.cert,args.key)
    stop=threading.Event()
    def loop():
        while not stop.wait(app.config.tick_seconds):
            try:
                app.tick()
                if sim:sim.tick()
            except Exception:
                import traceback;traceback.print_exc()
    worker=threading.Thread(target=loop,daemon=True);worker.start()
    url=f"{'https' if args.cert else 'http'}://127.0.0.1:{server.server_port}"
    print(f'Open {url}\nDemo users: administrator, pharmacist, nurse, technician\nDemo password: DemoOnly!2026')
    print('Local course simulation. Device integration token is in the local database; use tools/device_client.py for testing.')
    if args.open:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        stop.set();worker.join(timeout=2);server.server_close()
        with app.lock:app.save()
        print('Saved and stopped.')
if __name__=='__main__':main()
