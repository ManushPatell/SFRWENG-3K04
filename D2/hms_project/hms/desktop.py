"""Native PyQt5 desktop interface for the Hospital Monitoring System.

The desktop window talks directly to :class:`HMS`.  The application and
simulator therefore share one clear local execution path during the demo.
"""

import csv
import json
from datetime import datetime

from PyQt5.QtCore import QDateTime, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QDoubleSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

DEMO_PASSWORD = "DemoOnly!2026"
ROLE_NAMES = ("administrator", "pharmacist", "nurse", "technician")


def format_time(timestamp):
    """Return a readable local time, or a clear value for missing data."""

    if timestamp is None:
        return "Unavailable"

    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def item(value):
    """Create a table item without making table-building code noisy."""

    return QTableWidgetItem("Unavailable" if value is None else str(value))


class LoginDialog(QDialog):
    """Collect a local demo user's credentials before opening the dashboard."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hospital Monitoring System - Sign in")
        self.setModal(True)

        self.username = QComboBox()
        self.username.addItems(ROLE_NAMES)

        self.password = QLineEdit(DEMO_PASSWORD)
        self.password.setEchoMode(QLineEdit.Password)

        form = QFormLayout()
        form.addRow("Username", self.username)
        form.addRow("Password", self.password)

        note = QLabel(
            "Local demo accounts only.\n"
            f"The demonstration password is {DEMO_PASSWORD}."
        )
        note.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select a role to explore its permitted operations."))
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def credentials(self):
        """Return the values entered by the operator."""

        return self.username.currentText(), self.password.text()


class HMSWindow(QMainWindow):
    """Main native operator interface."""

    def __init__(self, service, simulator=None):
        super().__init__()
        self.service = service
        self.simulator = simulator
        self.token = None
        self.current_state = None

        self.setWindowTitle("Hospital Monitoring System")
        self.resize(1350, 850)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("Ready")

        self.build_overview_tab()
        self.build_inventory_tab()
        self.build_alarm_tab()
        self.build_history_tab()
        self.build_schedule_tab()
        self.build_simulator_tab()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(1000)

        self.application_timer = QTimer(self)
        self.application_timer.timeout.connect(self.tick_application)
        self.application_timer.start(int(self.service.config.tick_seconds * 1000))

    # ---------- Common window helpers ----------

    def show_error(self, message):
        """Show an operation failure without hiding the current dashboard."""

        self.statusBar().showMessage(message, 8000)
        QMessageBox.warning(self, "Operation failed", message)

    def run_action(self, operation, data):
        """Run a protected application operation and refresh the dashboard."""

        try:
            result = self.service.action(self.token, operation, data)
            self.statusBar().showMessage("Operation completed", 5000)
            self.refresh()
            return result
        except (ValueError, KeyError, PermissionError, TypeError) as exc:
            self.show_error(str(exc))
            return None

    def add_table(self, headers, rows, parent=None):
        """Create a read-only table from simple row values."""

        table = QTableWidget(parent)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)

        for row_number, row in enumerate(rows):
            for column_number, value in enumerate(row):
                table.setItem(row_number, column_number, item(value))

        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def add_section(self, title, widget):
        """Wrap a widget in a titled group box."""

        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.addWidget(widget)
        return group

    def combo_from(self, values):
        """Create a combo box populated with values from the current state."""

        combo = QComboBox()
        combo.addItems([str(value) for value in values])
        return combo

    # ---------- Overview ----------

    def build_overview_tab(self):
        self.overview = QWidget()
        layout = QVBoxLayout(self.overview)

        self.identity_label = QLabel()
        self.metrics_label = QLabel()
        self.cabinet_table = QTableWidget()
        self.command_table = QTableWidget()

        layout.addWidget(self.identity_label)
        layout.addWidget(self.metrics_label)
        layout.addWidget(self.add_section("Cabinet status", self.cabinet_table))
        layout.addWidget(self.add_section("Supervisory requests", self.command_table))

        form = QFormLayout()
        self.overview_cabinet = QComboBox()
        self.overview_action = QComboBox()
        self.overview_action.addItem("Record completed maintenance", "maintenance")
        self.overview_action.addItem("Report observed fault", "fault")
        self.overview_details = QLineEdit()
        form.addRow("Cabinet", self.overview_cabinet)
        form.addRow("Action", self.overview_action)
        form.addRow("Details", self.overview_details)

        submit = QPushButton("Submit")
        submit.clicked.connect(self.submit_overview_action)
        form.addRow(submit)
        layout.addWidget(
            self.add_section("Maintenance and fault reporting", self.form_widget(form))
        )

        self.tabs.addTab(self.overview, "Overview")

    def submit_overview_action(self):
        operation = self.overview_action.currentData()
        cabinet_id = self.overview_cabinet.currentText()
        details = self.overview_details.text().strip()

        if not details:
            self.show_error("Details are required.")
            return

        data = {
            "cabinet_id": cabinet_id,
            "activity": details,
            "message": details,
        }
        self.run_action(operation, data)

    # ---------- Inventory ----------

    def build_inventory_tab(self):
        self.inventory = QWidget()
        layout = QVBoxLayout(self.inventory)

        self.inventory_filter = QLineEdit()
        self.inventory_filter.setPlaceholderText("Search product, cabinet, or location")
        self.inventory_filter.textChanged.connect(self.refresh_inventory_table)
        layout.addWidget(self.inventory_filter)

        self.inventory_table = QTableWidget()
        layout.addWidget(
            self.add_section("Inventory by location", self.inventory_table)
        )

        form = QFormLayout()
        self.inventory_location = QComboBox()
        self.inventory_operation = QComboBox()
        self.inventory_operation.addItem("Set restock threshold", "threshold")
        self.inventory_operation.addItem("Report observed quantity", "discrepancy")
        self.inventory_value = QDoubleSpinBox()
        self.inventory_value.setRange(0, 1000000)
        self.inventory_value.setValue(20)
        self.threshold_type = QComboBox()
        self.threshold_type.addItems(["quantity", "percent"])
        form.addRow("Location", self.inventory_location)
        form.addRow("Operation", self.inventory_operation)
        form.addRow("Value", self.inventory_value)
        form.addRow("Threshold unit", self.threshold_type)

        button = QPushButton("Apply")
        button.clicked.connect(self.submit_inventory_action)
        form.addRow(button)
        layout.addWidget(
            self.add_section("Configure or report inventory", self.form_widget(form))
        )

        alternate_form = QFormLayout()
        self.alternate_location = QComboBox()
        self.needed_quantity = QSpinBox()
        self.needed_quantity.setRange(1, 1000000)
        self.needed_quantity.setValue(50)
        alternate_form.addRow("Requested location", self.alternate_location)
        alternate_form.addRow("Needed quantity", self.needed_quantity)
        find_button = QPushButton("Find stock")
        find_button.clicked.connect(self.find_alternate_stock)
        alternate_form.addRow(find_button)

        self.alternate_table = QTableWidget()
        alternate_box = QWidget()
        alternate_layout = QVBoxLayout(alternate_box)
        alternate_layout.addLayout(alternate_form)
        alternate_layout.addWidget(self.alternate_table)
        layout.addWidget(self.add_section("Alternate stock", alternate_box))

        self.tabs.addTab(self.inventory, "Inventory")

    def submit_inventory_action(self):
        location = self.inventory_location.currentText()
        value = self.inventory_value.value()
        operation = self.inventory_operation.currentData()
        data = {
            "location": location,
            "threshold": value,
            "observed": int(value),
            "threshold_type": self.threshold_type.currentText(),
        }
        self.run_action(operation, data)

    def find_alternate_stock(self):
        if not self.current_state:
            return

        requested_key = self.alternate_location.currentText()
        needed = self.needed_quantity.value()
        requested = next(
            (
                loc
                for loc in self.current_state["locations"]
                if loc["key"] == requested_key
            ),
            None,
        )
        if not requested:
            self.show_error("Select a valid requested location.")
            return

        rows = []
        for location in self.current_state["locations"]:
            same_product = location["medication_id"] == requested["medication_id"]
            is_alternate = location["key"] != requested_key
            if same_product and is_alternate and location["quantity"] > 0:
                rows.append(
                    (
                        location["key"],
                        location["quantity"],
                        "Yes" if location["quantity"] >= needed else "No",
                        "Current" if location["fresh"] else "Stale / unavailable",
                    )
                )

        self.set_table(
            self.alternate_table,
            ["Alternate", "Recorded quantity", "Enough", "Freshness"],
            rows,
        )

    # ---------- Alarms ----------

    def build_alarm_tab(self):
        self.alarms_tab = QWidget()
        layout = QVBoxLayout(self.alarms_tab)

        self.show_resolved = QCheckBox("Show resolved alarms")
        self.show_resolved.stateChanged.connect(self.refresh_alarm_table)
        layout.addWidget(self.show_resolved)

        self.alarm_table = QTableWidget()
        layout.addWidget(self.alarm_table)

        acknowledge_form = QFormLayout()
        self.acknowledge_alarm_id = QLineEdit()
        acknowledge_button = QPushButton("Acknowledge alarm")
        acknowledge_button.clicked.connect(self.acknowledge_selected_alarm)
        acknowledge_form.addRow("Alarm identifier", self.acknowledge_alarm_id)
        acknowledge_form.addRow(acknowledge_button)
        layout.addWidget(
            self.add_section(
                "Acknowledge an active alarm",
                self.form_widget(acknowledge_form),
            )
        )

        form = QFormLayout()
        self.resolve_alarm_id = QLineEdit()
        self.resolve_evidence = QLineEdit()
        form.addRow("Alarm identifier", self.resolve_alarm_id)
        form.addRow("Resolution evidence", self.resolve_evidence)
        resolve_button = QPushButton("Confirm manual resolution")
        resolve_button.clicked.connect(self.resolve_alarm)
        form.addRow(resolve_button)
        layout.addWidget(self.add_section("Manual resolution", self.form_widget(form)))

        self.tabs.addTab(self.alarms_tab, "Alarms")

    def resolve_alarm(self):
        data = {
            "alarm_id": self.resolve_alarm_id.text().strip(),
            "evidence": self.resolve_evidence.text().strip(),
        }
        self.run_action("resolve", data)

    def acknowledge_alarm(self, alarm_id):
        self.run_action("acknowledge", {"alarm_id": alarm_id})

    def acknowledge_selected_alarm(self):
        alarm_id = self.acknowledge_alarm_id.text().strip()
        if not alarm_id:
            self.show_error("Enter an alarm identifier.")
            return
        self.acknowledge_alarm(alarm_id)

    # ---------- History and reports ----------

    def build_history_tab(self):
        self.history_tab = QWidget()
        layout = QVBoxLayout(self.history_tab)

        form = QFormLayout()
        self.history_kind = QComboBox()
        self.history_kind.addItems(
            [
                "all",
                "dispense",
                "restock",
                "maintenance",
                "alarm",
                "acknowledgement",
                "resolution",
                "rejected_update",
                "authorization_failure",
                "threshold_change",
            ]
        )
        self.history_days = QComboBox()
        self.history_days.addItem("Last 24 hours", 1)
        self.history_days.addItem("Last 7 days", 7)
        form.addRow("Event type", self.history_kind)
        form.addRow("Period", self.history_days)

        report_button = QPushButton("Generate report")
        report_button.clicked.connect(self.generate_history)
        export_button = QPushButton("Save CSV")
        export_button.clicked.connect(self.save_history_csv)
        buttons = QHBoxLayout()
        buttons.addWidget(report_button)
        buttons.addWidget(export_button)
        form.addRow(buttons)
        layout.addLayout(form)

        self.report_period = QLabel()
        self.events_table = QTableWidget()
        layout.addWidget(self.report_period)
        layout.addWidget(self.events_table)

        reconstruction_form = QFormLayout()
        self.reconstruct_cabinet = QComboBox()
        self.reconstruct_at = QDateTimeEdit(QDateTime.currentDateTime())
        self.reconstruct_at.setCalendarPopup(True)
        reconstruction_form.addRow("Cabinet", self.reconstruct_cabinet)
        reconstruction_form.addRow("Time", self.reconstruct_at)
        reconstruct_button = QPushButton("Reconstruct")
        reconstruct_button.clicked.connect(self.reconstruct_stock)
        reconstruction_form.addRow(reconstruct_button)

        self.reconstruction_text = QPlainTextEdit()
        self.reconstruction_text.setReadOnly(True)
        reconstruction_box = QWidget()
        reconstruction_layout = QVBoxLayout(reconstruction_box)
        reconstruction_layout.addLayout(reconstruction_form)
        reconstruction_layout.addWidget(self.reconstruction_text)
        layout.addWidget(
            self.add_section("Recorded stock reconstruction", reconstruction_box)
        )

        self.last_history = None
        self.tabs.addTab(self.history_tab, "History and reports")

    def generate_history(self):
        try:
            kind = self.history_kind.currentText()
            days = self.history_days.currentData()
            self.last_history = self.service.history(self.token, kind, days)
            self.report_period.setText(
                f"{format_time(self.last_history['start'])} through "
                f"{format_time(self.last_history['end'])} UTC; "
                f"{len(self.last_history['events'])} events"
            )
            rows = []
            for event in reversed(self.last_history["events"]):
                rows.append(
                    (
                        format_time(event["received_at"]),
                        event["kind"],
                        event["cabinet_id"] or "System",
                        event["actor"],
                        json.dumps(event["details"], sort_keys=True),
                    )
                )
            self.set_table(
                self.events_table,
                ["Received", "Kind", "Cabinet", "Actor", "Details"],
                rows,
            )
        except (ValueError, KeyError, PermissionError, TypeError) as exc:
            self.show_error(str(exc))

    def save_history_csv(self):
        if not self.last_history:
            self.generate_history()
        if not self.last_history:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save report",
            "hms-report.csv",
            "CSV files (*.csv)",
        )
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8") as report_file:
            writer = csv.writer(report_file)
            writer.writerow(
                [
                    "start",
                    "end",
                    "timezone",
                    "event_id",
                    "kind",
                    "cabinet",
                    "actor",
                    "received_at",
                    "details",
                ]
            )
            for event in self.last_history["events"]:
                writer.writerow(
                    [
                        self.last_history["start"],
                        self.last_history["end"],
                        "UTC",
                        event["id"],
                        event["kind"],
                        event["cabinet_id"],
                        event["actor"],
                        event["received_at"],
                        json.dumps(event["details"]),
                    ]
                )

        self.statusBar().showMessage(f"Report saved to {path}", 5000)

    def reconstruct_stock(self):
        try:
            timestamp = self.reconstruct_at.dateTime().toSecsSinceEpoch()
            result = self.service.reconstruct(
                self.token,
                self.reconstruct_cabinet.currentText(),
                timestamp,
            )
            self.reconstruction_text.setPlainText(json.dumps(result, indent=2))
        except (ValueError, KeyError, PermissionError, TypeError) as exc:
            self.show_error(str(exc))

    # ---------- Schedules ----------

    def build_schedule_tab(self):
        self.schedule_tab = QWidget()
        layout = QVBoxLayout(self.schedule_tab)

        form = QFormLayout()
        self.schedule_record = QLineEdit("SCH-1")
        self.schedule_patient = QLineEdit("DEMO-PATIENT")
        self.schedule_medication = QLineEdit("MED-DEMO-01")
        self.schedule_start = QDateTimeEdit(QDateTime.currentDateTime())
        self.schedule_end = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        for field in (self.schedule_start, self.schedule_end):
            field.setCalendarPopup(True)
        form.addRow("Record ID", self.schedule_record)
        form.addRow("Patient ID", self.schedule_patient)
        form.addRow("Medication ID", self.schedule_medication)
        form.addRow("Start", self.schedule_start)
        form.addRow("End", self.schedule_end)

        button = QPushButton("Save schedule")
        button.clicked.connect(self.save_schedule)
        form.addRow(button)
        layout.addLayout(form)

        self.schedule_table = QTableWidget()
        layout.addWidget(self.schedule_table)
        self.tabs.addTab(self.schedule_tab, "Schedules")

    def save_schedule(self):
        data = {
            "record_id": self.schedule_record.text().strip(),
            "patient_id": self.schedule_patient.text().strip(),
            "medication_id": self.schedule_medication.text().strip(),
            "start": self.schedule_start.dateTime().toSecsSinceEpoch(),
            "end": self.schedule_end.dateTime().toSecsSinceEpoch(),
        }
        self.run_action("schedule", data)

    # ---------- Simulator ----------

    def build_simulator_tab(self):
        self.simulator_tab = QWidget()
        layout = QVBoxLayout(self.simulator_tab)

        self.simulator_status = QPlainTextEdit()
        self.simulator_status.setReadOnly(True)
        layout.addWidget(self.simulator_status)

        form = QFormLayout()
        self.simulator_cabinet = QComboBox()
        self.simulator_operation = QComboBox()
        self.simulator_operation.addItems(
            [
                "dispense",
                "restock",
                "maintenance",
                "duplicate",
                "invalid",
            ]
        )
        self.simulator_quantity = QSpinBox()
        self.simulator_quantity.setRange(1, 1000000)
        self.simulator_quantity.setValue(10)
        form.addRow("Cabinet", self.simulator_cabinet)
        form.addRow("Event", self.simulator_operation)
        form.addRow("Quantity", self.simulator_quantity)

        button = QPushButton("Inject event")
        button.clicked.connect(self.inject_simulator_event)
        form.addRow(button)
        layout.addWidget(self.add_section("Simulation event", self.form_widget(form)))

        self.tabs.addTab(self.simulator_tab, "Simulator")

    def inject_simulator_event(self):
        if not self.simulator:
            self.show_error("The simulator is disabled for this run.")
            return

        try:
            self.simulator.control(
                self.simulator_cabinet.currentText(),
                self.simulator_operation.currentText(),
                {"quantity": self.simulator_quantity.value()},
            )
            self.refresh()
        except (ValueError, KeyError, PermissionError, TypeError) as exc:
            self.show_error(str(exc))

    # ---------- Refresh and table updates ----------

    def refresh(self):
        if not self.token:
            return

        try:
            self.current_state = self.service.snapshot(self.token)
            self.update_combos()
            self.refresh_overview()
            self.refresh_inventory_table()
            self.refresh_alarm_table()
            self.refresh_schedules()
            self.refresh_simulator()
        except PermissionError as exc:
            self.show_error(str(exc))

    def tick_application(self):
        """Advance monitoring and simulator time inside the Qt event loop."""

        try:
            self.service.tick()
            if self.simulator:
                self.simulator.tick()
        except (ValueError, KeyError, TypeError) as exc:
            self.show_error(str(exc))

    def update_combo(self, combo, values):
        old_value = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems([str(value) for value in values])
        index = combo.findText(old_value)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def update_combos(self):
        cabinets = [cabinet["cabinet_id"] for cabinet in self.current_state["cabinets"]]
        locations = [location["key"] for location in self.current_state["locations"]]
        self.update_combo(self.overview_cabinet, cabinets)
        self.update_combo(self.inventory_location, locations)
        self.update_combo(self.alternate_location, locations)
        self.update_combo(self.reconstruct_cabinet, cabinets)
        self.update_combo(self.simulator_cabinet, cabinets)

    def refresh_overview(self):
        state = self.current_state
        active_alarms = [
            alarm for alarm in state["alarms"] if alarm["state"] != "resolved"
        ]
        available = sum(
            cabinet["communication"] == "available" for cabinet in state["cabinets"]
        )
        self.identity_label.setText(f"Signed in as {state['user']} ({state['role']})")
        self.metrics_label.setText(
            f"Registered cabinets: {len(state['cabinets'])}    "
            f"Communication available: {available}    "
            f"Active alarms: {len(active_alarms)}"
        )

        rows = []
        for cabinet in state["cabinets"]:
            health = cabinet.get("health", {})
            rows.append(
                (
                    cabinet["cabinet_id"],
                    cabinet["communication"],
                    cabinet["operational_status"],
                    "Current" if cabinet["health_fresh"] else "Stale / unavailable",
                    "Current" if cabinet["inventory_fresh"] else "Stale / unavailable",
                    health.get("power"),
                    health.get("hardware"),
                    health.get("sensors"),
                    format_time(cabinet.get("health_at")),
                )
            )
        self.set_table(
            self.cabinet_table,
            [
                "Cabinet",
                "Communication",
                "Operation",
                "Health",
                "Inventory",
                "Power",
                "Hardware",
                "Sensors",
                "Last health",
            ],
            rows,
        )

        command_rows = [
            (
                command["operation"],
                command["cabinet_id"],
                command["state"],
                format_time(command["created_at"]),
            )
            for command in reversed(state["commands"][-15:])
        ]
        self.set_table(
            self.command_table,
            ["Request", "Cabinet", "State", "Created"],
            command_rows,
        )

    def refresh_inventory_table(self):
        if not self.current_state:
            return

        filter_text = self.inventory_filter.text().lower()
        rows = []
        for location in self.current_state["locations"]:
            searchable = json.dumps(location).lower()
            if filter_text and filter_text not in searchable:
                continue
            percentage = location["percentage"]
            percentage_text = (
                "Unavailable" if percentage is None else f"{percentage:.1f}%"
            )
            rows.append(
                (
                    location["key"],
                    location["name"],
                    location["quantity"],
                    f"{percentage_text} / {location['classification']}",
                    f"{location['threshold']} {location['threshold_type']}",
                    "Current" if location["fresh"] else "Stale / unavailable",
                    location.get("lot"),
                )
            )
        self.set_table(
            self.inventory_table,
            [
                "Location",
                "Product",
                "Quantity",
                "% / class",
                "Threshold",
                "Freshness",
                "Lot",
            ],
            rows,
        )

    def refresh_alarm_table(self):
        if not self.current_state:
            return

        rows = []
        for alarm in reversed(self.current_state["alarms"]):
            if not self.show_resolved.isChecked() and alarm["state"] == "resolved":
                continue
            rows.append(
                (
                    alarm["id"],
                    alarm["severity"],
                    alarm["kind"],
                    alarm["cabinet_id"] or "System",
                    alarm["state"],
                    alarm["message"],
                    alarm.get("acknowledged_by") or "",
                )
            )
        self.set_table(
            self.alarm_table,
            [
                "ID",
                "Severity",
                "Kind",
                "Cabinet",
                "State",
                "Message",
                "Acknowledged by",
            ],
            rows,
        )

    def refresh_schedules(self):
        rows = [
            (
                schedule["record_id"],
                schedule["patient_id"],
                schedule["medication_id"],
                format_time(schedule["start"]),
                format_time(schedule["end"]),
            )
            for schedule in self.current_state["schedules"]
        ]
        self.set_table(
            self.schedule_table,
            ["Record", "Patient", "Medication", "Start", "End"],
            rows,
        )

    def refresh_simulator(self):
        if not self.simulator:
            self.simulator_status.setPlainText("Simulator controls are disabled.")
            return

        status = self.simulator.status()
        self.simulator_status.setPlainText(json.dumps(status, indent=2))

    def set_table(self, table, headers, rows):
        """Replace a table's contents while keeping the table configuration consistent."""

        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)

        for row_number, row in enumerate(rows):
            for column_number, value in enumerate(row):
                table.setItem(row_number, column_number, item(value))

        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)

    def form_widget(self, form_layout):
        """Place a form layout inside a normal QWidget for use in sections."""

        widget = QWidget()
        widget.setLayout(form_layout)
        return widget


def run_desktop(service, simulator=None):
    """Start the native interface and return Qt's exit code."""

    application = QApplication.instance() or QApplication([])
    login = LoginDialog()
    if login.exec_() != QDialog.Accepted:
        return 0

    username, password = login.credentials()
    try:
        token = service.login(username, password)
    except PermissionError as exc:
        QMessageBox.critical(None, "Sign in failed", str(exc))
        return 1

    window = HMSWindow(service, simulator)
    window.token = token
    window.show()
    window.refresh()
    return application.exec_()
