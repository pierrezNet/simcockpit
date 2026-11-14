"""Transpondeur (IO32) poussé vers X-Plane : config/avions/b738-laminar/transpondeur.yaml."""

import os
import unittest

from simcockpit.hw.mastercard import Decoder
from simcockpit.logic import config
from simcockpit.logic.engine import Engine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = "sim/cockpit2/radios/actuators/transponder_code"
MODE = "sim/cockpit2/radios/actuators/transponder_mode"


def frames(name):
    with open(os.path.join(ROOT, "tests", "data", name)) as f:
        for line in f:
            parts = line.split()
            if len(parts) > 2 and parts[1] == "RX":         # « temps RX octets… »
                yield float(parts[0]), bytes.fromhex("".join(parts[2:]))


class TestTransponderXPlane(unittest.TestCase):
    def test_capture_pushes_code_and_mode(self):
        # capture réelle : 4444 → … → 2000, puis STBY et ON
        eng = Engine(config.load(os.path.join(ROOT, "config/avions/b738-laminar")))
        eng.sim_step({}, True, 0.0)
        dec, sent, prev = Decoder(), [], None
        for t, pkt in frames("efde_xpdr_4444_to_2000.txt"):
            if prev is not None and prev + 0.1 < t:
                eng.poll(prev + 0.1)
                sent += eng.sim_step({}, True, prev + 0.1)
            if dec.feed(pkt).inputs_changed:
                eng.feed("io32", dec.inputs(), t, active_level=1)
            eng.poll(t)
            sent += eng.sim_step({}, True, t)
            prev = t
        codes = [a[2] for a in sent if a[1] == CODE]
        modes = [a[2] for a in sent if a[1] == MODE]
        self.assertEqual(codes[0], 4444.0)
        self.assertEqual(codes[-1], 2000.0)
        self.assertIn(1.0, modes)                 # STBY
        self.assertEqual(modes[-1], 2.0)          # ON

    def test_positions_pushed_on_connect(self):
        eng = Engine(config.load(os.path.join(ROOT, "config/avions/b738-laminar")))
        state = [0] * 72                          # molettes à 0000, sélecteur sur OFF
        eng.feed("io32", state, 0.0, active_level=1)
        eng.poll(0.2)
        actions = eng.sim_step({}, True, 0.3)     # X-Plane apparaît
        self.assertIn(("dref", CODE, 0.0), actions)
        self.assertIn(("dref", MODE, 0.0), actions)


if __name__ == "__main__":
    unittest.main()
