import copy
import tempfile
import unittest
from pathlib import Path
from hms.service import HMS
from hms.storage import Store
from hms.inventory import classify


class CoreTests(unittest.TestCase):
    """Exercise the application policies without depending on the GUI."""

    def setUp(self):
        """Build an isolated in-memory-style database for each test."""

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.time = 1000.0
        self.store = Store(Path(self.tmp.name) / "test.db")
        self.h = HMS(self.store, clock=lambda: self.time)
        self.h.register("A")
        self.h.register("B")
        self.token = self.h.login("administrator", "DemoOnly!2026")
        self.seq = 0
        self.loc = dict(
            drawer_id="D",
            pocket_id="P",
            medication_id="M",
            name="Demo",
            din="DEMO",
            strength="1",
            dosage_form="tablet",
            quantity=30,
            full_stock=100,
            threshold=20,
        )
        self.send("inventory", {"locations": [self.loc]})

    def send(self, kind, data):
        """Send a sequential cabinet event to the application under test."""

        self.seq += 1
        e = dict(
            cabinet_id="A",
            event_id=str(self.seq),
            sequence=self.seq,
            timestamp=self.time,
            type=kind,
            data=copy.deepcopy(data),
        )
        self.h.receive(e)
        return e

    def verify(self, cid="A"):
        """Complete the next heartbeat challenge for one cabinet."""

        self.h.tick()
        c = self.h.comm.pending[cid]
        self.h.comm.answer(cid, c["request_id"], c["a"] + c["b"])

    def active(self, kind):
        """Return unresolved alarms of one kind."""

        return [
            a
            for a in self.h.state["alarms"]
            if a["kind"] == kind and a["state"] != "resolved"
        ]

    def test_duplicate_transaction_is_applied_once(self):
        e = self.send(
            "dispense",
            dict(
                drawer_id="D",
                pocket_id="P",
                medication_id="M",
                quantity=5,
                operator_id="N",
            ),
        )
        self.assertTrue(self.h.receive(e)["duplicate"])
        self.assertEqual(self.h.state["locations"]["A|D|P"]["quantity"], 25)

    def test_invalid_update_rolls_back_and_logs(self):
        bad = copy.deepcopy(self.loc)
        bad["quantity"] = -1
        with self.assertRaises(ValueError):
            self.send("inventory", {"locations": [bad]})
        self.assertEqual(self.h.state["locations"]["A|D|P"]["quantity"], 30)
        self.assertEqual(self.h.state["events"][-1]["kind"], "rejected_update")

    def test_nan_rejection_is_durable(self):
        bad = copy.deepcopy(self.loc)
        bad["quantity"] = float("nan")
        with self.assertRaises(ValueError):
            self.send("inventory", {"locations": [bad]})
        self.assertEqual(self.store.load()["locations"]["A|D|P"]["quantity"], 30)

    def test_stale_update_preserves_value(self):
        self.time += 20
        e = dict(
            cabinet_id="A",
            event_id="old",
            sequence=2,
            timestamp=1000,
            type="inventory",
            data={"locations": [self.loc]},
        )
        with self.assertRaises(ValueError):
            self.h.receive(e)
        self.assertTrue(self.active("stale_data"))

    def test_alarm_ack_is_not_clear(self):
        self.send(
            "dispense",
            dict(
                drawer_id="D",
                pocket_id="P",
                medication_id="M",
                quantity=15,
                operator_id="N",
            ),
        )
        alarm = self.active("low_stock")[0]
        self.h.action(self.token, "acknowledge", {"alarm_id": alarm["id"]})
        self.time += 31
        self.h.tick()
        self.assertEqual(alarm["state"], "active_acknowledged")
        self.send(
            "restock",
            dict(
                drawer_id="D",
                pocket_id="P",
                medication_id="M",
                quantity=20,
                operator_id="N",
            ),
        )
        self.assertEqual(alarm["state"], "resolved")

    def test_heartbeat_failure_recovery_and_isolation(self):
        self.verify("B")
        c = self.h.comm.pending["A"]
        with self.assertRaises(ValueError):
            self.h.comm.answer("A", c["request_id"], -1)
        self.assertFalse(self.h.comm.verified("A"))
        self.assertTrue(self.h.comm.verified("B"))
        self.time += 5
        self.verify("A")
        self.assertFalse(self.active("communication"))
        self.assertIsNone(self.h.state["cabinets"]["A"]["health_at"])

    def test_timeout(self):
        self.h.tick()
        self.time += 3
        self.h.tick()
        self.assertEqual(self.h.state["cabinets"]["A"]["communication"], "error")

    def test_replay_heartbeat_rejected(self):
        self.h.tick()
        c = self.h.comm.pending["A"]
        self.h.comm.answer("A", c["request_id"], c["a"] + c["b"])
        with self.assertRaises(ValueError):
            self.h.comm.answer("A", c["request_id"], c["a"] + c["b"])

    def test_unverified_configuration_blocked(self):
        with self.assertRaises(ValueError):
            self.h.action(self.token, "threshold", dict(location="A|D|P", threshold=10))
        self.verify()
        self.h.action(self.token, "threshold", dict(location="A|D|P", threshold=10))
        self.assertEqual(len(self.h.state["commands"]), 1)

    def test_three_denials_and_role(self):
        token = self.h.login("nurse", "DemoOnly!2026")
        for _ in range(3):
            with self.assertRaises(PermissionError):
                self.h.action(token, "threshold", {})
        self.assertTrue(self.active("security"))

    def test_persistence_does_not_restore_live_connection(self):
        self.verify()
        self.h.save()
        other = HMS(self.store, clock=lambda: self.time)
        self.assertEqual(other.state["locations"]["A|D|P"]["quantity"], 30)
        self.assertFalse(other.comm.verified("A"))

    def test_schedule_conflict_rejected(self):
        one = dict(record_id="1", patient_id="P", medication_id="M", start=100, end=200)
        self.assertTrue(self.h.action(self.token, "schedule", one)["ok"])
        one["record_id"] = "2"
        self.assertFalse(self.h.action(self.token, "schedule", one)["ok"])
        self.assertNotIn("2", self.h.state["schedules"])

    def test_product_conflict_preserves_stock(self):
        bad = copy.deepcopy(self.loc)
        bad["name"] = "Other"
        with self.assertRaises(ValueError):
            self.send("inventory", {"locations": [bad]})
        self.assertTrue(self.active("medication_conflict"))

    def test_reconstruction_marks_gap(self):
        self.seq += 1
        self.send("inventory", {"locations": [self.loc]})
        self.assertTrue(self.h.reconstruct(self.token, "A", self.time)["incomplete"])

    def test_classification_boundaries(self):
        self.assertEqual(
            [classify(q, 100) for q in [0, 1, 49, 50, 99, 100]],
            ["Empty", "Low", "Low", "Half", "Half", "Full"],
        )
        self.assertEqual(classify(1, 0), "Unavailable")


if __name__ == "__main__":
    unittest.main()
