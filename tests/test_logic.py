"""Tests de la logique métier : configuration, commandes, moteur rejoué sur capture réelle.

Nécessite PyYAML : .venv/bin/python -m unittest discover -s tests -t .
"""

import os
import unittest

from simcockpit.hw.mastercard import Decoder
from simcockpit.logic import config, controls
from simcockpit.logic.engine import Engine
from tests.test_mastercard import frames

ROOT = os.path.dirname(os.path.dirname(__file__))


class TestControls(unittest.TestCase):
    def test_octal_digits(self):
        c = controls.make("code", {"type": "octal_digits",
                                   "inputs": [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10, 11]]})
        active = [0] * 72
        for i in (1, 3, 4, 5, 6, 8, 9, 11):   # 2 / 7 / 5 / 5
            active[i] = 1
        c.update(active, 0.0)
        self.assertIsNone(c.poll(0.01))        # pas encore stable
        self.assertEqual(c.poll(0.06), "2755")
        self.assertIsNone(c.poll(0.2))         # inchangé

    def test_selector_priority(self):
        c = controls.make("mode", {"type": "selector", "positions": {"ON": 12, "STBY": 13}})
        active = [0] * 72
        c.update(active, 0)
        self.assertEqual(c.poll(1), "OFF")
        active[13] = 1
        c.update(active, 2)
        self.assertEqual(c.poll(3), "STBY")
        active[12] = 1                          # en ON, STBY reste fermé
        c.update(active, 4)
        self.assertEqual(c.poll(5), "ON")

    def test_bad_specs(self):
        with self.assertRaises(ValueError):
            controls.make("x", {"type": "bidule"})
        with self.assertRaises(ValueError):
            controls.make("x", {"type": "octal_digits", "inputs": [[0, 1]]})


class TestConfig(unittest.TestCase):
    def test_project_file_loads(self):
        ck = config.load(os.path.join(ROOT, "config/avions/rj85-simule"))
        self.assertEqual(sorted(ck.instruments), ["dme", "mcp", "transpondeur"])
        self.assertEqual(ck.cards["io32"].product, "USB32I04AD")

    def test_errors(self):
        with self.assertRaises(config.ConfigError):
            config.parse({"cards": {"a": {"product": "Inconnu"}}})
        with self.assertRaises(config.ConfigError):
            config.parse({"cards": {"a": {"product": "USB32I04AD"}},
                          "instruments": {"x": {"card": "b"}}})
        with self.assertRaises(config.ConfigError):   # entrée utilisée deux fois
            config.parse({"cards": {"a": {"product": "USB32I04AD"}},
                          "instruments": {"x": {"card": "a", "controls": {
                              "s1": {"type": "switch", "input": 5},
                              "s2": {"type": "switch", "input": 5}}}}})


class TestEngineReplay(unittest.TestCase):
    def test_capture_through_cockpit_yaml(self):
        eng = Engine(config.load(os.path.join(ROOT, "config/avions/rj85-simule")))
        dec, seen = Decoder(), []
        for t, pkt in frames("efde_xpdr_4444_to_2000.txt"):
            if dec.feed(pkt).inputs_changed:
                eng.feed("io32", dec.inputs(), t, active_level=1)
            seen += [(c.control, c.value) for c in eng.poll(t)]
        codes = [v for k, v in seen if k == "code"]
        modes = [v for k, v in seen if k == "mode"]
        self.assertEqual(codes, ["4444", "3444", "2444", "2344", "2244", "2144", "2044",
                                 "2043", "2033", "2023", "2013", "2012", "2000"])
        self.assertEqual(modes[0], "STBY")
        self.assertEqual(modes[-1], "ON")


if __name__ == "__main__":
    unittest.main()


class TestConfigErrors(unittest.TestCase):
    def test_tab_is_reported_with_line(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("cards:\n  mcp:\n\tproduct: IOCard-MCP\n")
        with self.assertRaisesRegex(config.ConfigError, "ligne 3 : tabulation"):
            config.load(f.name)
        os.unlink(f.name)
