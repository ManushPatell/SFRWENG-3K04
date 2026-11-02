"""Module 9 - Screen.

Shows the operator what is going on and turns what they do into calls on
the modules below.

Hides: the layout and the wording. This module only calls the public
operations of the modules below - it never reads their variables - which
is why the screen cannot show something no module agreed to publish.
"""
from shared import Action, FaultType

TITLES = {Action.DISPENSE: "Dispense against an order",
          Action.RESTOCK: "Restock a drawer"}


class Screen:
    def __init__(self, cabinet):
        self._cabinet = cabinet

    # --- the operator's actions ---------------------------------------------

    def do(self, action, values):
        """Carry out one operator action. Each branch calls one operation
        on one module; nothing here changes any module's data directly. A
        bad entry becomes a message, never a crash."""
        cabinet = self._cabinet
        try:
            if action == "login":
                result = cabinet.users.login(values.get("user", ""),
                                             values.get("pin", ""))
                return self._said(result, "Signed in.")

            if action == "logout":
                cabinet.users.logout("user")
                return {"ok": True, "message": "Signed out."}

            if action == "dispense":
                result = cabinet.dispensing.start_dispense(
                    values["order"], _number(values["qty"]))
                return self._said(result, "Drawer open. " + cabinet.dispensing.prompt())

            if action == "restock":
                result = cabinet.dispensing.start_restock(
                    _number(values["drawer"]), _number(values["qty"]))
                return self._said(result, "Drawer open. " + cabinet.dispensing.prompt())

            if action == "cancel":
                return self._said(cabinet.dispensing.cancel(),
                                  "Cancelled. Nothing was recorded.")

            if action == "ack":
                allowed = cabinet.users.may(Action.ACK_ALARM)
                if not allowed.ok:
                    return self._said(allowed, "")
                return self._said(cabinet.modes.acknowledge(
                    FaultType(values["fault"]), _maybe(values.get("drawer")),
                    _user(cabinet)), "Alarm acknowledged. The fault is still active.")

            if action == "clear":
                allowed = cabinet.users.may(Action.CLEAR_FAULT)
                if not allowed.ok:
                    return self._said(allowed, "")
                return self._said(cabinet.modes.clear_fault(
                    FaultType(values["fault"]), _maybe(values.get("drawer")),
                    _user(cabinet)), "Fault cleared.")

            if action == "enter_maintenance":
                return self._said(cabinet.modes.request_maintenance(
                    cabinet.users.session(), cabinet.dispensing.busy()),
                    "Maintenance mode.")

            if action == "exit_maintenance":
                return self._said(
                    cabinet.modes.request_normal(cabinet.users.session()),
                    "Back to Normal mode.")

            return {"ok": False, "message": "Unknown action %r." % action}

        except (KeyError, ValueError) as e:
            return {"ok": False, "message": "Check the entries. (%s)" % e}

    def _said(self, result, message_when_ok):
        if result.ok:
            return {"ok": True, "message": message_when_ok or "Done."}
        return {"ok": False, "message": result.message() or "Not allowed."}

    # --- what to draw ---------------------------------------------------------

    def render(self, message="", ok=True):
        """The full markup for the cabinet screen. The test bench the demo
        wraps around this is not part of the product."""
        cabinet = self._cabinet
        status = cabinet.status()
        session = status["session"]

        parts = [self._topbar(status, session)]
        if message:
            parts.append('<div class="%s">%s</div>' %
                         ("note" if ok else "note bad", _esc(message)))
        parts.append(self._banner(status))

        if session is None:
            parts.append(self._login_card())
        else:
            role = session.role
            if cabinet.dispensing.busy():
                parts.append(self._active_card())
            else:
                if cabinet.users.can(Action.DISPENSE):
                    parts.append(self._dispense_card())
                if cabinet.users.can(Action.RESTOCK):
                    parts.append(self._restock_card())
            parts.append(self._drawers_card(status))
            parts.append(self._faults_card(status, role))
            if cabinet.users.can(Action.ENTER_MAINTENANCE) or \
                    cabinet.users.can(Action.EXIT_MAINTENANCE):
                parts.append(self._maintenance_card(status))
            if cabinet.users.can(Action.VIEW_LOG):
                parts.append(self._log_card())

        return "\n".join(parts)

    def _topbar(self, status, session):
        who = "%s (%s)" % (session.user_id, session.role.value) if session else "nobody"
        logout = '<form method="post" action="/action/logout" style="display:inline"><button class="btn">Sign out</button></form>' if session else ""
        return """<div class="topbar"><b>%s</b><span>Mode <b>%s</b></span>
<span>Monitoring System <b>%s</b></span><span>User <b>%s</b></span>%s</div>""" % (
            _esc(status["adc"]), status["mode"], status["link"], _esc(who), logout)

    def _banner(self, status):
        parts = []
        if status["mode"] != "NORMAL":
            parts.append("%s mode" % status["mode"].title())
        if status["link"] == "OFFLINE":
            parts.append("Working offline - %s event(s) waiting to send" % status["waiting"])
        if status["faults"]:
            parts.append("%s active fault(s)" % len(status["faults"]))
        if not parts:
            return ""
        return '<div class="alert">%s</div>' % " &middot; ".join(_esc(p) for p in parts)

    def _login_card(self):
        return """<div class="card"><h2>Sign in</h2>
<form method="post" action="/action/login" class="formrow">
<label>Staff ID<input name="user" autocomplete="off"></label>
<label>PIN<input name="pin" type="password" autocomplete="off"></label>
<button class="btn go">Sign in</button></form>
<p class="hint">N001/1111 nurse &middot; T001/2222 pharmacy technician &middot;
P001/3333 pharmacist &middot; M001/5555 maintenance technician</p></div>"""

    def _active_card(self):
        cabinet = self._cabinet
        drawer = cabinet.dispensing.drawer()
        return """<div class="card step"><h2>Next step</h2>
<p class="stepline">%s</p>
<form method="post" action="/action/cancel"><button class="btn">Cancel this transaction</button></form>
</div>""" % _esc(cabinet.dispensing.prompt())

    def _dispense_card(self):
        cabinet = self._cabinet
        rows = []
        for order in cabinet.dispensing.orders():
            medication = cabinet.inventory.medication(order.medication_id)
            name = medication.name if medication else order.medication_id
            rows.append('<option value="%s">%s - %s for %s (dose %s)</option>' % (
                _esc(order.order_id), _esc(order.order_id), _esc(name),
                _esc(order.patient), order.dose))
        return """<div class="card"><h2>Dispense against an order</h2>
<form method="post" action="/action/dispense" class="formrow">
<label class="grow">Order<select name="order">%s</select></label>
<label>Quantity<input name="qty" type="number" min="1" value="1"></label>
<button class="btn go">Unlock drawer</button></form></div>""" % "".join(rows)

    def _restock_card(self):
        cabinet = self._cabinet
        rows = []
        for view in cabinet.inventory.views():
            medication = cabinet.inventory.medication(view.medication_id)
            name = medication.name if medication else "-"
            rows.append('<option value="%s">Drawer %s - %s</option>' %
                       (view.drawer_id, view.drawer_id, _esc(name)))
        return """<div class="card"><h2>Restock a drawer</h2>
<p class="hint">Scan the package on the test bench first.</p>
<form method="post" action="/action/restock" class="formrow">
<label class="grow">Drawer<select name="drawer">%s</select></label>
<label>Quantity<input name="qty" type="number" min="1" value="10"></label>
<button class="btn go">Unlock drawer</button></form></div>""" % "".join(rows)

    def _drawers_card(self, status):
        cabinet = self._cabinet
        rows = []
        for view in status["stock"]:
            medication = cabinet.inventory.medication(view.medication_id)
            name = medication.name if medication else "-"
            flags = []
            if view.out_of_stock:
                flags.append("OUT OF STOCK")
            elif view.low:
                flags.append("LOW")
            if view.drawer_id in status["out_of_service"]:
                flags.append("OUT OF SERVICE")
            rows.append("<tr><td>%s</td><td>%s</td><td class='num'>%s</td>"
                        "<td>%s</td><td>%s</td><td>%s</td></tr>" % (
                view.drawer_id, _esc(name), view.quantity, _esc(", ".join(flags)),
                cabinet.hardware.indicator(view.drawer_id).value,
                cabinet.hardware.door(view.drawer_id).value))
        return """<div class="card"><h2>Drawers</h2>
<table><tr><th>#</th><th>Medication</th><th class="num">Qty</th>
<th>Flags</th><th>Light</th><th>Door</th></tr>%s</table></div>""" % "".join(rows)

    def _faults_card(self, status, role):
        cabinet = self._cabinet
        if not status["faults"]:
            return '<div class="card"><h2>Alarms and faults</h2><p class="hint">None active.</p></div>'
        rows = []
        for fault in cabinet.modes.active_faults():
            seen = " (acknowledged)" if fault.acknowledged else ""
            buttons = ""
            if not fault.acknowledged and cabinet.users.can(Action.ACK_ALARM):
                buttons += _fault_button("ack", fault, "Acknowledge")
            if cabinet.users.can(Action.CLEAR_FAULT):
                buttons += _fault_button("clear", fault, "Clear")
            rows.append("<tr><td>%s%s</td><td>drawer %s</td><td>%s</td><td>%s</td></tr>" % (
                _esc(fault.fault_type.value), seen,
                fault.drawer_id if fault.drawer_id is not None else "-",
                _esc(fault.detail), buttons))
        return """<div class="card"><h2>Alarms and faults</h2>
<table><tr><th>Fault</th><th>Drawer</th><th>Detail</th><th></th></tr>%s</table></div>""" % "".join(rows)

    def _maintenance_card(self, status):
        if status["mode"] == "MAINTENANCE":
            action, label = "exit_maintenance", "Return to Normal mode"
        else:
            action, label = "enter_maintenance", "Enter Maintenance mode"
        return """<div class="card"><h2>Maintenance</h2>
<form method="post" action="/action/%s"><button class="btn">%s</button></form></div>""" % (action, label)

    def _log_card(self):
        rows = []
        for entry in self._cabinet.log.read(limit=25)[::-1]:
            details = ", ".join("%s=%s" % (k, v) for k, v in entry.details.items())
            rows.append("<tr><td class='num'>%s</td><td>%s</td><td>%s</td><td class='logl'>%s</td></tr>" % (
                entry.sequence, _esc(entry.event_type), _esc(entry.user_id or "-"),
                _esc(details)))
        return """<div class="card"><h2>Recent events</h2>
<table><tr><th class="num">#</th><th>Event</th><th>User</th><th>Detail</th></tr>%s</table></div>""" % "".join(rows)


def _fault_button(action, fault, label):
    drawer = fault.drawer_id if fault.drawer_id is not None else ""
    return ('<form method="post" action="/action/%s" style="display:inline">'
           '<input type="hidden" name="fault" value="%s">'
           '<input type="hidden" name="drawer" value="%s">'
           '<button class="btn quiet">%s</button></form>') % (
        action, fault.fault_type.value, drawer, label)


def _number(value):
    return int(str(value).strip())


def _maybe(value):
    if value in (None, "", "None"):
        return None
    return int(value)


def _user(cabinet):
    session = cabinet.users.session()
    return session.user_id if session else None


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))
