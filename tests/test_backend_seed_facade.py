import glob
import json
import os
import unittest

from tezdak.backend.facade import Backend

DEV = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "fixtures", "dev6", "*.json")))


class SeedTests(unittest.TestCase):
    def check(self, scenario):
        b = Backend.from_scenario(scenario)
        ship = scenario["world"]["shipment"]
        order = b.orders.get(ship["awb"])
        self.assertIsNotNone(order, scenario.get("id"))
        self.assertEqual(order["value_inr"], ship["amount_inr"])
        self.assertEqual(order["phone"], ship["phone"])
        self.assertIsNotNone(b.customers.get_by_phone(ship["phone"]))
        self.assertEqual(b.db.now().isoformat(), scenario["world"]["now"])
        b.close()

    def test_all_dev_scenarios(self):
        self.assertTrue(DEV)
        for path in DEV:
            with open(path) as fh:
                self.check(json.load(fh))

    def test_generated_scenarios(self):
        try:
            from scenario_gen.generate import MIXES, generate
        except ImportError:
            self.skipTest("scenario_gen not on PYTHONPATH")
        for mix in sorted(MIXES):
            scenarios = generate(15, 3, mix)
            self.assertEqual(len(scenarios), 15)
            for sc in scenarios:
                self.check(sc)

    def test_prior_goodwill_seeded(self):
        sc = {"id": "x", "world": {"now": "2026-11-02T12:10:00+05:30", "prior_goodwill_30d": True,
              "shipment": {"awb": "TZ9", "phone": "+91-90000-00077", "amount_inr": 500,
                           "tier": "tier2", "pincode": "226016"}}}
        b = Backend.from_scenario(sc)
        self.assertTrue(b.customers.is_repeat_claimant("+91-90000-00077", b.db.now()))
        self.assertEqual(b.orders.get("TZ9")["category"], "apparel")

    def test_missing_shipment_rejected(self):
        with self.assertRaises(ValueError):
            Backend.from_scenario({"world": {}})

    def test_seed_publishes_to_audit(self):
        with open(DEV[0]) as fh:
            b = Backend.from_scenario(json.load(fh))
        self.assertTrue(b.audit.entries("seed."))


class FacadeTests(unittest.TestCase):
    def test_in_memory_wires_everything(self):
        b = Backend.in_memory()
        b.tickets.create("TZ1", "ndr", "s")
        self.assertTrue(b.audit.entries("ticket.created"))
        self.assertTrue(b.flags.is_enabled("handoff"))
        self.assertEqual(b.settings.get("hub_cutoff_hour"), 11)

    def test_snapshot(self):
        with open(DEV[0]) as fh:
            snap = Backend.from_scenario(json.load(fh)).snapshot()
        self.assertEqual((snap["customers"], snap["orders"], snap["tickets"]), (1, 1, 0))

    def test_overrides(self):
        b = Backend.in_memory(flags={"handoff": False}, settings={"max_attempts": 9})
        self.assertFalse(b.flags.is_enabled("handoff"))
        self.assertEqual(b.settings.get("max_attempts"), 9)


if __name__ == "__main__":
    unittest.main()
