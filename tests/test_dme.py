"""DME EFDE : trames comparées à celles validées à la webcam le 2026-11-10."""

import unittest

from simcockpit.hw import cards, dme


class TestDmeFrames(unittest.TestCase):
    def test_distance(self):
        self.assertEqual(dme.distance(12.3).hex(" "), "01 00 7b 00 00 00 00 00")
        self.assertEqual(dme.distance(46.6)[1:3], bytes([0x01, 0xD2]))
        self.assertEqual(dme.distance(1000)[1:3], bytes([0x27, 0x10]))
        with self.assertRaises(ValueError):
            dme.distance(-1)

    def test_right_text_padded_with_spaces(self):
        # « LIL » de la photo de référence ; un octet 00 allumerait des segments parasites
        self.assertEqual(dme.right_text("lil").hex(" "), "02 4c 49 4c 20 00 00 00")
        self.assertEqual(dme.right_text("TOUL")[1:5], b"TOUL")
        with self.assertRaises(ValueError):
            dme.right_text("LONG1")

    def test_text_column(self):
        self.assertEqual(dme.text(3, "ABCD").hex(" "), "06 03 41 42 43 44 00 00")
        with self.assertRaises(ValueError):
            dme.text(0, "AB")

    def test_annunciators(self):
        self.assertEqual(dme.annunciator("canal", "2").hex(" "), "03 00 00 00 00 00 00 02")
        self.assertEqual(dme.annunciator("unite_gauche", "NM").hex(" "), "04 00 00 00 00 02 00 00")
        self.assertEqual(dme.annunciator("unite_droite", "ID").hex(" "), "05 00 00 00 00 00 04 00")
        self.assertEqual(dme.annunciator("unite_droite").hex(" "), "05 00 00 00 00 00 00 00")

    def test_backlight_and_power(self):
        self.assertEqual(dme.backlight().hex(" "), "08 00 00 00 00 00 00 00")
        self.assertEqual(dme.backlight(255)[:2], bytes([0x08, 0xFF]))
        self.assertEqual(dme.command(dme.OFF)[0], 0x09)
        self.assertEqual(dme.command(dme.ON)[0], 0x0A)

    def test_buttons(self):
        # captures réelles : repos, SEL enfoncé, PWR enfoncé
        self.assertEqual(dme.buttons(bytes.fromhex("0a7e9bcef6974c15")), [0, 0])
        self.assertEqual(dme.buttons(bytes.fromhex("017e9bcef6974c15")), [1, 0])
        self.assertEqual(dme.buttons(bytes.fromhex("027ebbcef6974c15")), [0, 1])

    def test_reference_photo_frames(self):
        o = dme.DmeOutputs()
        o.distance, o.right = 3.2, "LIL"
        o.lit.update(canal="1", unite_gauche="NM", unite_droite="ID")
        self.assertEqual([f[0] for f in o.frames()], [0x07, 0x08, 0x01, 0x02, 0x03, 0x04, 0x05])

    def test_classified(self):
        card = cards.classify("DME USB")
        self.assertIs(card, cards.EFDE_DME)
        self.assertFalse(card.init)


if __name__ == "__main__":
    unittest.main()
