"""Logique du boîtier radio relié au 737 de Laminar (config/avions/b738-laminar/radio.yaml)."""

import unittest

from simcockpit.hw import radio_airbus
from simcockpit.logic import config
from simcockpit.logic.engine import Engine

COM1_ACT = "sim/cockpit2/radios/actuators/com1_frequency_hz_833"
COM1_STBY = "sim/cockpit2/radios/actuators/com1_standby_frequency_hz_833"
NAV1_ACT = "sim/cockpit2/radios/actuators/nav1_frequency_hz"
NAV1_STBY = "sim/cockpit2/radios/actuators/nav1_standby_frequency_hz"


def rest():
    s = [0] * 72
    for i in (4, 5, 6, 7, 8, 9, 10, 11):
        s[i] = 1                                   # poussoirs au repos
    s[12] = 0                                      # radio sur ON (l'entrée 12 vaut 0 sur ON)
    return s


class TestRadioPanel(unittest.TestCase):
    def setUp(self):
        self.eng = Engine(config.load("config/avions/b738-laminar"))
        self.radio = self.eng.cockpit.instruments["radio"].controls["boitier"]
        self.state = rest()
        self.t = 0.0
        self.eng.feed("radio", self.state, self.t, active_level=1)
        self.eng.sim_step({COM1_ACT: 118000, COM1_STBY: 121500, NAV1_ACT: 10950, NAV1_STBY: 11030},
                          True, 0.1)
        self.eng.poll(0.2)

    def actions(self):
        return self.eng.sim_step({}, True, self.t)

    def press(self, index):
        self.t += 0.5
        self.state[index] = 0
        self.eng.feed("radio", self.state, self.t, active_level=1)
        self.t += 0.1
        self.state[index] = 1
        self.eng.feed("radio", self.state, self.t, active_level=1)
        self.eng.poll(self.t)

    def test_displays_com1_by_default(self):
        texts, leds = self.radio.radio_display()
        self.assertEqual(texts, {"ACTIVE": "118.000", "STANDBY": "121.500"})
        self.assertEqual(leds, {"VHF1": True})
        out = self.eng.outputs["radio"]
        expected = radio_airbus.RadioOutputs()
        expected.set_display("ACTIVE", "118.000")
        expected.set_display("STANDBY", "121.500")
        self.assertEqual(out.display_frame(), expected.display_frame())

    def test_vor_button_selects_nav1(self):
        self.press(8)                               # VOR
        texts, leds = self.radio.radio_display()
        self.assertEqual(texts, {"ACTIVE": "109.50", "STANDBY": "110.30"})
        self.assertEqual(leds, {"NAV": True, "VOR": True})
        self.assertEqual(self.eng.outputs["radio"].leds, (1 << 6) | (1 << 3))

    def test_transfer_and_knobs_send_commands(self):
        self.press(4)                               # transfert
        self.assertIn(("cmd", "sim/radios/com1_standy_flip"), self.actions())
        self.state[2], self.state[3] = 1, 0         # grande bague : un cran (00 → 10)
        self.eng.feed("radio", self.state, self.t + 1, active_level=1)
        acts = self.actions()
        self.assertEqual(len([a for a in acts if "coarse" in a[1]]), 1)

    def test_power_off_blanks(self):
        self.state[12] = 1                          # interrupteur sur OFF
        self.eng.feed("radio", self.state, 1.0, active_level=1)
        self.eng.poll(1.1)
        self.assertEqual(self.radio.radio_display(), ({"ACTIVE": "", "STANDBY": ""}, {}))
        self.assertEqual(self.eng.outputs["radio"].leds, 0)
        self.press(8)                               # sans effet éteinte
        self.assertEqual(self.radio.selected.name, "COM1")

    def test_no_sim_shows_dashes(self):
        eng = Engine(config.load("config/avions/b738-laminar"))
        radio = eng.cockpit.instruments["radio"].controls["boitier"]
        self.assertEqual(radio.radio_display()[0], {"ACTIVE": "---", "STANDBY": "---"})


if __name__ == "__main__":
    unittest.main()
