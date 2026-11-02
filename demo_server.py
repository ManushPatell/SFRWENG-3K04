"""Demo harness - NOT part of the cabinet.

Serves two things on one page: the cabinet screen, which is module 9 of
the product, and the simulated hardware and Monitoring System, which stand
in for things that are not software we wrote.

Everything below the dashed rule acts through SimulatedHardware,
SimulatedStorage or the MonitoringSystem stub. None of it is reachable from
any module of the cabinet - those switches are not on the Hardware/Storage
interfaces the product modules are written against.

No JavaScript: every control is a plain HTML form. A click is a POST, the
server updates one module, and the whole page re-renders from the modules'
own public state - so there is nothing happening that is not visible by
reading this file and screen.py.
"""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode

from cabinet import TICK_SECONDS, Cabinet, load_demo_data
from screen import Screen
from shared import MedicationOrder
from demo_monitoring import MonitoringSystem

STYLE = """
* { box-sizing: border-box; }
body { margin: 0; background: #fff; color: #1a1a1a;
       font: 14px/1.45 system-ui, "Segoe UI", sans-serif; }
.topbar { display: flex; flex-wrap: wrap; gap: 20px; align-items: baseline;
          border-bottom: 2px solid #1a1a1a; padding: 10px 16px; }
.alert { padding: 10px 16px; margin: 0; background: #fdf3df; color: #8a5a00;
         font-weight: 700; border-bottom: 1px solid #c9c9c9; }
.note { padding: 10px 16px; margin: 0; background: #eef6f0; color: #0f6b3f;
        border-bottom: 1px solid #c9c9c9; }
.note.bad { background: #fbe9ea; color: #b00020; }
.wrap { padding: 16px; max-width: 980px; }
.card { border: 1px solid #c9c9c9; margin-bottom: 14px; background: #fff; }
.card > :not(h2):not(table) { margin: 10px; }
.card h2 { font-size: 13px; letter-spacing: .04em; text-transform: uppercase;
           color: #444; margin: 0; padding: 7px 10px; border-bottom: 1px
           solid #c9c9c9; background: #f2f2f2; font-weight: 600; }
.step { border: 2px solid #11486b; }
.step h2 { background: #e8f0f5; color: #11486b; }
.stepline { font-size: 18px; font-weight: 700; }
.formrow { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
label { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: #555; }
label.grow { flex: 1 1 200px; }
input, select { font: inherit; font-size: 13px; padding: 5px 7px; border: 1px solid #8a8a8a; }
input[type="number"] { width: 84px; }
.btn { font: inherit; font-size: 13px; padding: 5px 12px; cursor: pointer;
       background: #fff; border: 1px solid #8a8a8a; }
.btn.go { background: #11486b; border-color: #11486b; color: #fff; font-weight: 600; }
.btn.quiet { font-size: 12px; padding: 3px 8px; }
table { border-collapse: collapse; width: 100%; }
th { text-align: left; font-size: 11px; text-transform: uppercase; color: #555;
     padding: 6px 10px; border-bottom: 1px solid #c9c9c9; background: #f8f8f8; }
td { padding: 7px 10px; border-bottom: 1px solid #e2e2e2; vertical-align: top; }
td.num, th.num { text-align: right; }
.logl { font: 11.5px ui-monospace, Consolas, monospace; color: #444; }
.hint { color: #666; font-size: 12px; margin: 8px 0 0; }
.bench { margin-top: 10px; border-top: 2px dashed #8a8a8a; padding-top: 10px; }
.bench summary { cursor: pointer; color: #555; }
.benchgrid { display: grid; gap: 10px; margin-top: 10px;
             grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
.benchbox { border: 1px solid #c9c9c9; padding: 10px 12px; background: #fafafa;
            margin-top: 10px; }
.benchbox table { margin: 8px 0; }
.benchbox td, .benchbox th { padding: 5px 8px; }
.benchbox h3 { font-size: 13px; margin: 0 0 6px; }
.rigrow { display: flex; align-items: center; gap: 6px; margin: 5px 0; }
.rigrow > span:first-child { color: #666; flex: 0 0 112px; }
.rigrow .ctl { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.feed { font: 11px ui-monospace, Consolas, monospace; max-height: 140px;
        overflow: auto; color: #444; margin-top: 6px; }
.feed.alarm { color: #b00020; }
"""


class Demo:
    def __init__(self, store_path=None):
        self.cabinet = Cabinet(store_path=store_path)
        self.monitoring = MonitoringSystem("ADC-01", self.cabinet.hardware)
        self.cabinet.link.connect(self.monitoring)
        self.screen = Screen(self.cabinet)

        load_demo_data(self.cabinet, self.monitoring)
        self.monitoring.set_orders([
            MedicationOrder("ORD-1", "A. Brown", "MED-001", 2),
            MedicationOrder("ORD-2", "R. Osei", "MED-003", 1),
            MedicationOrder("ORD-3", "L. Fontaine", "MED-004", 1)])

        self._lock = threading.Lock()
        self._stop = threading.Event()

        self.cabinet.start()
        self.cabinet.tick()
        self.cabinet.users.sync()

    def start_ticking(self):
        def loop():
            while not self._stop.is_set():
                with self._lock:
                    try:
                        self.cabinet.tick()
                    except Exception as e:
                        print("tick error:", type(e).__name__, e)
                time.sleep(TICK_SECONDS)
        threading.Thread(target=loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def do(self, action, values):
        with self._lock:
            return self.screen.do(action, values)

    def simulate(self, what, values):
        with self._lock:
            hw = self.cabinet.hardware
            drawer = _int(values.get("drawer"))
            if what == "door":
                hw.set_door(drawer, not hw.is_really_open(drawer))
            elif what == "jam":
                (hw.unjam if hw.is_jammed(drawer) else hw.jam)(drawer)
            elif what == "sensor":
                (hw.plug_sensor if not hw.is_plugged(drawer) else hw.unplug_sensor)(drawer)
            elif what == "power":
                hw.set_power(not hw.is_powered())
            elif what == "storage":
                self.cabinet.storage.set_failing(not self.cabinet.storage.is_failing())
            elif what == "scan":
                hw.present_package(values.get("med") or "")
            elif what == "advance":
                hw.advance(float(values.get("seconds", 10)))
            elif what == "link":
                self.monitoring.set_reachable(not self.monitoring.is_reachable())
            return True

    def page(self, message="", ok=True):
        return self.screen.render(message, ok) + self._bench()

    def _bench(self):
        hw = self.cabinet.hardware
        rows = []
        for d in self.cabinet.drawer_ids:
            rows.append("""<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td>
<td>%s</td></tr>""" % (
                d, _simbtn("door", d, "Close door" if hw.is_really_open(d) else "Open door"),
                _simbtn("jam", d, "Unjam" if hw.is_jammed(d) else "Jam lock"),
                _simbtn("sensor", d, "Plug sensor" if not hw.is_plugged(d) else "Unplug sensor"),
                hw.describe_light(d)))

        meds = sorted({v.medication_id for v in self.cabinet.inventory.views() if v.medication_id})
        scan_options = "".join('<option value="%s">%s</option>' % (m, m) for m in meds)

        recent = [_short(m) for m in self.monitoring.received[-10:]][::-1]
        alarms = [_short(m) for m in self.monitoring.alarms[-6:]][::-1]
        invariants = self.cabinet.check_invariants()
        inv_lines = "".join("%s: %s<br>" % (k, "ok" if v else "BROKEN")
                            for k, v in invariants.items())

        return """
<details class="bench" open>
<summary><b>Test bench</b> - simulated hardware and the Monitoring System.
Not part of the product.</summary>

<section class="benchbox">
  <h3>Cabinet hardware</h3>
  <p class="hint">Stands in for the physical cabinet.</p>
  <table><tr><th>Drawer</th><th>Door</th><th>Lock</th><th>Sensor</th><th>Light</th></tr>
  %s</table>
  <div class="rigrow"><span>Sounder</span><span class="ctl"><b>%s</b></span></div>
  <div class="rigrow"><span>Mains power</span><span class="ctl">%s</span></div>
  <div class="rigrow"><span>Storage</span><span class="ctl">%s</span></div>
  <div class="rigrow"><span>Scanner</span><span class="ctl">
    <form method="post" action="/sim/scan" class="formrow">
    <select name="med">%s</select><button class="btn quiet">Present package</button></form></span></div>
  <div class="rigrow"><span>Clock</span><span class="ctl">%s%s%s</span></div>
</section>

<div class="benchgrid">
  <section class="benchbox">
    <h3>Monitoring System (Part B stand-in)</h3>
    <p class="hint">Reached only through the documented messages.</p>
    <div class="rigrow"><span>Link</span><span class="ctl">%s<b>%s</b></span></div>
    <div class="rigrow"><span>Received</span><span class="ctl"><b>%s</b></span></div>
    <div class="rigrow"><span>Alarms</span><span class="ctl"><b>%s</b></span></div>
    <div class="feed alarm">%s</div>
    <div class="feed">%s</div>
  </section>
  <section class="benchbox">
    <h3>Module invariants</h3>
    <p class="hint">Checked after every operation.</p>
    <div class="logl">%s</div>
  </section>
</div>
</details>""" % (
            "".join(rows), hw.describe_sound(),
            _simbtn("power", None, "Cut power" if hw.is_powered() else "Restore power"),
            _simbtn("storage", None, "Make writes fail" if not self.cabinet.storage.is_failing() else "Let writes succeed"),
            scan_options,
            _simbtn("advance", None, "+10 s", seconds=10),
            _simbtn("advance", None, "+35 s", seconds=35),
            _simbtn("advance", None, "+65 s", seconds=65),
            _simbtn("link", None, "Cut the link" if self.monitoring.is_reachable() else "Restore the link"),
            "ONLINE" if self.monitoring.is_reachable() else "OFFLINE",
            len(self.monitoring.received), len(self.monitoring.alarms),
            "<br>".join(a["text"] for a in alarms) or "(none)",
            "<br>".join(r["text"] for r in recent) or "(none)",
            inv_lines)


def _short(message):
    kind = message.get("kind")
    if kind == "ALARM":
        where = " drawer %s" % message["drawer"] if message.get("drawer") is not None else ""
        return {"text": "%s%s: %s" % (message.get("fault"), where, message.get("detail", ""))}
    if kind == "EVENT":
        return {"text": "#%s %s" % (message.get("seq"), message.get("event"))}
    if kind == "INVENTORY":
        return {"text": "drawer %s qty %s" % (message.get("drawer"), message.get("qty"))}
    if kind == "MODE":
        return {"text": "%s -> %s" % (message.get("from"), message.get("to"))}
    return {"text": str(kind)}


def _simbtn(what, drawer, label, seconds=None):
    hidden = '<input type="hidden" name="drawer" value="%s">' % drawer if drawer is not None else ""
    if seconds is not None:
        hidden += '<input type="hidden" name="seconds" value="%s">' % seconds
    return ('<form method="post" action="/sim/%s" style="display:inline">%s'
           '<button class="btn quiet">%s</button></form>') % (what, hidden, label)


def _int(value):
    return int(value) if value not in (None, "", "None") else None


def make_handler(demo):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_GET(self):
            path, _, query = self.path.partition("?")
            if path != "/":
                return self.send_error(404)
            q = parse_qs(query)
            message = q.get("msg", [""])[0]
            ok = q.get("ok", ["1"])[0] == "1"
            self._html(render_page(demo.page(message, ok)))

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = parse_qs(self.rfile.read(length).decode())
            values = {k: v[0] for k, v in body.items()}

            path = self.path
            if path.startswith("/action/"):
                result = demo.do(path[len("/action/"):], values)
                return self._redirect(result.get("message", ""), result.get("ok", False))
            if path.startswith("/sim/"):
                demo.simulate(path[len("/sim/"):], values)
                return self._redirect("", True)
            self.send_error(404)

        def _redirect(self, message, ok):
            query = urlencode({"msg": message, "ok": "1" if ok else "0"})
            self.send_response(303)
            self.send_header("Location", "/?" + query)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _html(self, payload):
            payload = payload.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def render_page(body):
    # plain concatenation, not %-formatting: STYLE and body both contain
    # literal "%" (CSS widths) that a second %-substitution would choke on
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
           '<title>ADC - Deliverable 2</title><style>' + STYLE + '</style>\n'
           '</head><body><div class="wrap">' + body + '</div></body></html>')


def serve(port=8000, store_path=None):
    demo = Demo(store_path)
    demo.start_ticking()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(demo))
    return demo, server
