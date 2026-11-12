"""Radio OpenCockpits Airbus : trames vérifiées à la webcam le 2026-11-12."""

import unittest

from simcockpit.hw import cards, radio_airbus as r


class TestRadioAirbus(unittest.TestCase):
    def test_frequencies_frame(self):
        # photo : ACTIVE « 118.700 », STANDBY « 121.500 »
        o = r.RadioOutputs()
        o.set_display("ACTIVE", "118.700")
        o.set_display("STANDBY", "121.500")
        self.assertEqual(o.display_frame().hex(" "), "00 87 11 00 15 12 0a 00")

    def test_digit_order(self):
        # essai : « 21 43 65 87 a9 cb » → ACTIVE 654321, STANDBY « ␣-␣987 »
        o = r.RadioOutputs()
        o.set_display("ACTIVE", "654321")
        o.set_display("STANDBY", " - 987")
        self.assertEqual(o.display_frame()[:6].hex(" "), "21 43 65 87 a9 ab")

    def test_dots(self):
        self.assertEqual(r.parse("8888.88")[1], 4)
        self.assertEqual(r.parse("88888.8")[1], 5)
        self.assertEqual(r.parse("117.95")[1], 4)            # calé à droite : « ␣117.95 »
        o = r.RadioOutputs()
        o.set_display("STANDBY", "8888.88")
        self.assertEqual(o.display_frame()[6], 0x04)
        o.set_display("STANDBY", "888888")                   # le point s'efface
        self.assertEqual(o.display_frame()[6], 0x00)
        with self.assertRaises(ValueError):
            r.parse("1.23456")

    def test_leds(self):
        o = r.RadioOutputs()
        o.set_led("VHF1", True)
        o.set_led("SEL", True)
        self.assertEqual(o.led_frame().hex(" "), "05 00 00 00 00 00 80 00")
        o.set_led("ILS", True)
        self.assertEqual(o.led_frame()[0], 0x85)

    def test_blank(self):
        o = r.RadioOutputs()
        o.set_display("ACTIVE", "")
        self.assertEqual(o.display_frame()[:3], bytes([0xAA] * 3))

    def test_classified(self):
        self.assertIs(cards.classify("IOCard-RadioAirb"), cards.OC_RADIO_AIRBUS)


if __name__ == "__main__":
    unittest.main()
