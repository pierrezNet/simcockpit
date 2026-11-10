"""Logique simulée du pilote automatique RJ sur le MCP (règles validées le 2026-11-10)."""

import unittest

from simcockpit.logic import config
from simcockpit.logic.engine import Engine
from simcockpit.logic.rj_autopilot import RjAutopilot

BUTTONS = {"N1": 29, "SPEED": 28, "VNAV": 27, "LVL CHG": 26, "HDG SEL": 25, "LNAV": 24,
           "VOR LOC": 23, "APP": 22, "ALT HLD": 21, "V/S": 20, "CMD A": 19, "CMD B": 18,
           "CWS A": 17, "CWS B": 16}
FD_L, FD_R, AT, DISC = 15, 13, 30, 14


def rest():
    s = [0] * 72
    for i in BUTTONS.values():
        s[i] = 1                       # poussoirs : 1 au repos
    s[DISC] = 1                        # barre DISENGAGE relevée
    return s


class TestRjAutopilot(unittest.TestCase):
    def setUp(self):
        self.ap = RjAutopilot("ap", BUTTONS, fd_left=FD_L, fd_right=FD_R, at_arm=AT,
                              disengage=DISC)
        self.t = 0.0
        self.state = rest()
        self.ap.update(self.state, self.t)

    def push(self, *names):
        for name in names:
            i = BUTTONS[name]
            self.t += 0.3
            self.state[i] = 0
            self.ap.update(self.state, self.t)
            self.t += 0.1
            self.state[i] = 1
            self.ap.update(self.state, self.t)

    def lit(self):
        return {n for n, on in self.ap.led_states().items() if on}

    def test_lateral_and_vertical_exclusive(self):
        self.push("HDG SEL", "ALT HLD")
        self.assertEqual(self.lit(), {"HDG SEL", "ALT HLD"})
        self.push("LNAV", "V/S")
        self.assertEqual(self.lit(), {"LNAV", "V/S"})

    def test_second_press_disengages(self):
        self.push("HDG SEL", "HDG SEL")
        self.assertIsNone(self.ap.lateral)

    def test_app_takes_both_axes(self):
        self.push("HDG SEL", "ALT HLD", "APP")
        self.assertEqual(self.lit(), {"APP"})
        self.push("V/S")                       # un mode vertical annule APP
        self.assertEqual(self.lit(), {"V/S"})
        self.push("APP", "APP")                # APP puis nouvel appui : plus rien
        self.assertEqual(self.lit(), set())

    def test_thrust_and_nav_source(self):
        self.push("N1")
        self.assertIn("N1", self.lit())
        self.push("SPEED")                     # SPEED bascule aussi THRUST
        self.assertNotIn("N1", self.lit())
        self.push("CMD A")
        self.assertIn("CMD A", self.lit())
        self.push("CMD B")
        self.assertEqual(self.lit() & {"CMD A", "CMD B"}, {"CMD B"})
        self.push("CMD B")
        self.assertIsNone(self.ap.nav_source)

    def test_switches_drive_cws_and_at(self):
        self.state[FD_L] = 1
        self.state[AT] = 1
        self.ap.update(self.state, 1.0)
        self.assertEqual(self.lit(), {"CWS A", "A/T ARM"})

    def test_cws_alert_when_fd_off(self):
        self.assertEqual(self.ap.press("CWS A"), "CWS A : sans effet, F/D gauche sur OFF")
        self.state[FD_L] = 1
        self.ap.update(self.state, 1.0)
        self.assertIsNone(self.ap.press("CWS A"))
        self.assertIn("F/D droit", self.ap.press("CWS B"))

    def test_disengage_cuts_everything(self):
        self.push("HDG SEL", "ALT HLD", "N1", "CMD A")
        self.state[DISC] = 0
        self.ap.update(self.state, 5.0)
        self.assertEqual(self.lit(), set())
        self.push("HDG SEL")                   # sans effet barre baissée
        self.assertEqual(self.lit(), set())
        self.state[DISC] = 1
        self.ap.update(self.state, 9.0)
        self.push("HDG SEL")
        self.assertEqual(self.lit(), {"HDG SEL"})

    def test_bounce_is_ignored(self):
        i = BUTTONS["HDG SEL"]
        for k, v in enumerate([0, 1, 0, 1]):  # rebond en 40 ms
            self.state[i] = v
            self.ap.update(self.state, 1.0 + k * 0.01)
        self.assertEqual(self.ap.lateral, "HDG")

    def test_engine_sends_led_frame(self):
        eng = Engine(config.load("cockpit.yaml"))
        ap = eng.cockpit.instruments["mcp"].controls["pilote_auto"]
        eng.poll(0.0)
        eng._pending["mcp"].clear()
        ap.press("APP")
        eng.poll(1.0)
        self.assertIn("leds", eng._pending["mcp"])
        self.assertEqual(eng._pending["mcp"]["leds"][:2], bytes([0x01, 0x00]))   # bit 0 = APP


if __name__ == "__main__":
    unittest.main()
