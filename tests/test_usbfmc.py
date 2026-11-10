"""CDU OpenCockpits (USBFMC V1.0) : trames réelles du 2026-11-10."""

import unittest

from simcockpit.hw import cards, usbfmc


class TestUsbFmc(unittest.TestCase):
    def test_captured_keys(self):
        # appuis réels, dans l'ordre : 1 2 3 A B EXEC CLR
        captured = ["20", "1f", "1e", "3d", "3c", "42", "01"]
        names = [usbfmc.key_name(usbfmc.keys_pressed(bytes.fromhex(c + "00" * 7))[0])
                 for c in captured]
        self.assertEqual(names, ["1", "2", "3", "A", "B", "EXEC", "CLR"])

    def test_table_is_consistent(self):
        self.assertEqual(len(set(usbfmc.KEYS.values())), len(usbfmc.KEYS))   # noms uniques
        self.assertTrue(all(1 <= c <= usbfmc.MAX_KEY for c in usbfmc.KEYS))
        laid_out = [n for names in usbfmc.LAYOUT.values() for n in names]
        self.assertEqual(sorted(laid_out), sorted(usbfmc.KEYS.values()))   # chaque touche affichée une fois

    def test_no_key_on_empty_frame(self):
        self.assertEqual(usbfmc.keys_pressed(bytes(8)), [])
        self.assertIn("inconnue", usbfmc.key_name(33))

    def test_led_mask(self):
        # vérifié à la webcam : 04 = EXEC seul, 1f = les cinq
        self.assertEqual(usbfmc.led_frame(["EXEC"]).hex(" "), "04 00 00 00 00 00 00 00")
        self.assertEqual(usbfmc.led_frame(usbfmc.LEDS)[0], 0x1F)
        self.assertEqual(usbfmc.led_frame()[0], 0x00)
        # l'ancienne init Master 3d allumait OFST, EXEC, DSPY et FAIL
        self.assertEqual(usbfmc.led_frame(["OFST", "EXEC", "DSPY", "FAIL"])[0] | 0x20, 0x3D)

    def test_classified(self):
        self.assertIs(cards.classify("USBFMC V1.0"), cards.OC_USBFMC)


if __name__ == "__main__":
    unittest.main()
