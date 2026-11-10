"""Logique métier du MCP : encodeurs, IAS/Mach, A/T ARM, sorties — rejeu d'une capture réelle."""

import os
import unittest

from simcockpit.hw import mcp
from simcockpit.hw.bitmap import BitmapDecoder
from simcockpit.logic import config, controls
from simcockpit.logic.engine import Engine
from tests.test_mastercard import frames

ROOT = os.path.dirname(os.path.dirname(__file__))
GRAY = [(0, 0), (1, 0), (1, 1), (0, 1)]   # ordre « sens horaire » observé


def turn(enc, clicks, t0=0.0, dt=0.5):
    """Simule `clicks` crans (signés) espacés de dt secondes, à partir de la position
    atteinte précédemment par cet encodeur. Retourne l'instant final."""
    active = [0] * 72
    pos, t = getattr(enc, "_test_pos", 0), t0
    a, b = enc.indexes[:2]
    active[a], active[b] = GRAY[pos % 4]
    enc.update(active, t)
    for _ in range(abs(clicks)):
        pos += 1 if clicks > 0 else -1
        t += dt
        active[a], active[b] = GRAY[pos % 4]
        enc.update(active, t)
    enc._test_pos = pos
    return t


class TestEncoder(unittest.TestCase):
    def test_wrap_heading(self):
        e = controls.make("hdg", {"type": "encoder", "inputs": [6, 7], "min": 0, "max": 359,
                                  "wrap": True, "initial": 358})
        turn(e, 3)
        self.assertEqual(e.value, 1)       # 358 → 359 → 0 → 1
        turn(e, -2, t0=10)
        self.assertEqual(e.value, 359)

    def test_clamp_altitude(self):
        e = controls.make("alt", {"type": "encoder", "inputs": [2, 3], "min": 0, "max": 36000,
                                  "step": 100, "initial": 35900, "accel": False})
        turn(e, 5)
        self.assertEqual(e.value, 36000)
        turn(e, -3, t0=10)
        self.assertEqual(e.value, 35700)

    def test_invert_vs(self):
        e = controls.make("vs", {"type": "encoder", "inputs": [10, 11], "min": -6000,
                                 "max": 6000, "step": 100, "invert": True, "accel": False})
        turn(e, 5)                          # 5 crans « vers DN »
        self.assertEqual(e.value, -500)

    def test_acceleration(self):
        e = controls.make("hdg", {"type": "encoder", "inputs": [6, 7], "min": 0, "max": 359,
                                  "wrap": True})
        turn(e, 4, dt=0.5)                  # lent : +1 par cran
        self.assertEqual(e.value, 4)
        turn(e, 4, t0=10, dt=0.03)  # rapide : ×10 après le 1er cran
        self.assertEqual(e.value, 4 + 1 + 3 * 10)

    def test_poll_publishes_initial_then_changes_only(self):
        e = controls.make("crs", {"type": "encoder", "inputs": [4, 5]})
        self.assertEqual(e.poll(0), 0)
        self.assertIsNone(e.poll(0))
        turn(e, 1)
        self.assertEqual(e.poll(1), 1)


class TestSpeed(unittest.TestCase):
    def test_ias_mach_toggle_with_bounce(self):
        s = controls.make("v", {"type": "speed_encoder", "inputs": [0, 1], "toggle_input": 12,
                                "toggle_level": 0})
        active = [0] * 72
        active[12] = 1                      # C/O au repos = 1
        s.update(active, 0.0)
        self.assertEqual((s.mode, s.value), ("IAS", 250))
        for t, v in ((1.00, 0), (1.04, 1), (1.08, 0), (1.12, 1)):   # appui avec rebonds
            active[12] = v
            s.update(active, t)
        self.assertEqual((s.mode, s.value), ("MACH", 78))
        active[12] = 0
        s.update(active, 3.0)
        self.assertEqual((s.mode, s.value), ("IAS", 250))


class TestEngineReplay(unittest.TestCase):
    def test_knob_capture_drives_values_and_outputs(self):
        eng = Engine(config.load(os.path.join(ROOT, "cockpit.yaml")))
        dec, last, prev_t = BitmapDecoder(), {}, None
        for t, pkt in frames("mcp_knobs.txt"):
            # la capture ne garde que les trames qui changent : on consulte quand même
            # le moteur entre deux trames, comme le fait step() toutes les 20 ms
            if prev_t is not None and prev_t + 0.1 < t:
                for c in eng.poll(prev_t + 0.1):
                    last.setdefault(c.control, []).append(c.value)
            if dec.feed(pkt).inputs_changed:
                eng.feed("mcp", dec.inputs(), t, active_level=1)
            for c in eng.poll(t):
                last.setdefault(c.control, []).append(c.value)
            prev_t = t
        final = {k: v[-1] for k, v in last.items()}
        self.assertEqual(final["crs1"], 6)
        self.assertEqual(final["cap"], 5)
        self.assertEqual(final["altitude"], 10500)
        self.assertEqual(final["vitesse_verticale"], -500)
        # CRS2 : 5 crans, dont deux à 0,12 s d'écart → accélération ×3 sur l'un d'eux
        self.assertEqual(final["crs2"], 8)
        # A/T ARM basculé puis rebasculé : géré par le pilote automatique RJ
        ap = last["pilote_auto"]
        self.assertTrue(any(v.endswith("AT") for v in ap))
        self.assertFalse(ap[-1].endswith("AT"))
        # C/O ×2 : 255 kt → Mach .47 à 10500 ft (ISA), puis retour exact à 255 kt
        self.assertEqual(last["vitesse"], [250, 251, 252, 253, 254, 255, 47, 255])
        out = eng.outputs["mcp"]
        expected = mcp.McpOutputs()
        for disp, v in (("CRS1", 6), ("IAS", 255), ("HDG", 5), ("ALT", 10500), ("VS", -500),
                        ("CRS2", 8)):
            expected.set_display(disp, v, blank_leading=disp not in ("CRS1", "HDG", "CRS2"))
        self.assertEqual(out.display_frames(), expected.display_frames())
        self.assertEqual(out.leds, 0)        # A/T ARM rebasculé à la fin

    def test_leading_zeros_for_course(self):
        eng = Engine(config.load(os.path.join(ROOT, "cockpit.yaml")))
        eng.poll(0.0)                                   # publie les valeurs initiales
        p0, _ = eng.outputs["mcp"].display_frames()
        # CRS1 « 000 » (n2 n1 n0), IAS « 250 » (n5 n4 n3), HDG « 000 », ALT « 10··· » (n10 n9)
        self.assertEqual(p0.hex(" "), "00 00 25 00 00 01 00 00")

    def test_mach_display_and_conversion(self):
        eng = Engine(config.load(os.path.join(ROOT, "cockpit.yaml")))
        speed = eng.cockpit.instruments["mcp"].controls["vitesse"]
        speed.altitude_control.value = 30000
        speed.value = 280
        speed._switch_mode()
        self.assertEqual((speed.mode, speed.value), ("MACH", 74))   # 280 kt FL300 ≈ M .74
        eng.poll(0.0)
        p0, _ = eng.outputs["mcp"].display_frames()
        n3, n4, n5, n11 = p0[1] >> 4, p0[2] & 0x0F, p0[2] >> 4, p0[5] >> 4
        self.assertEqual((n5, n4, n3), (mcp.DIGIT_BLANK, 7, 4))      # « .74 »
        self.assertEqual(n11 & 0x8, 0x8)                             # point allumé
        speed.value = 76                                             # Mach retouché
        speed._switch_mode()
        self.assertEqual(speed.value, 287)                           # M .76 FL300 ≈ 287 kt
        eng.poll(1.0)
        self.assertEqual(eng.outputs["mcp"].display_frames()[0][5] >> 4 & 0x8, 0)  # point éteint

    def test_bad_output_name_is_reported(self):
        with self.assertRaises(config.ConfigError):
            config.parse({"cards": {"m": {"product": "IOCard-MCP"}},
                          "instruments": {"x": {"card": "m", "controls": {
                              "h": {"type": "encoder", "inputs": [6, 7], "display": "HDGX"}}}}})


if __name__ == "__main__":
    unittest.main()
