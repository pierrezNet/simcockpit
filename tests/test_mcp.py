"""Sorties du MCP : trames comparées à celles validées à la webcam le 2026-11-08."""

import unittest

from simcockpit.hw import mcp


class TestMcpFrames(unittest.TestCase):
    def test_page0_marker_frame(self):
        # essai B : CRS1 « 100 », IAS « 432 », HDG « 765 », ALT « 98··· »
        f = mcp.frame([0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9], page=0)
        self.assertEqual(f.hex(" "), "00 21 43 65 87 09 00 00")

    def test_page1_selector(self):
        self.assertEqual(mcp.frame([0] * 11, page=1)[6], 0x01)

    def test_led_frame(self):
        # essai H : seules HDG SEL et APP allumées
        o = mcp.McpOutputs()
        o.set_led("HDG SEL", True)
        o.set_led("APP", True)
        self.assertEqual(o.led_frame().hex(" "), "01 20 00 00 00 00 02 00")
        o.set_led("APP", False)
        self.assertEqual(o.led_frame()[:2], bytes([0x00, 0x20]))

    def test_displays_reproduce_photo(self):
        # photo de l'essai F : ALT « 98110 », V/S « 98765 », CRS2 « 432 »
        o = mcp.McpOutputs()
        o.set_display("ALT", 98110)
        o.set_display("VS", 98765)
        o.set_display("CRS2", 432)
        p0, p1 = o.display_frames()
        self.assertEqual((p0[4] >> 4, p0[5] & 0x0F), (8, 9))          # n9=8, n10=9
        self.assertEqual(p1[:6].hex(" "), "10 21 43 65 87 09")         # n0..n10 = 0 1 1 2 3 4 5 6 7 8 9

    def test_format_value(self):
        B, M = mcp.DIGIT_BLANK, mcp.DIGIT_MINUS
        self.assertEqual(mcp.format_value(5, 3), [B, B, 5])
        self.assertEqual(mcp.format_value(0, 3), [B, B, 0])
        self.assertEqual(mcp.format_value(-700, 5), [B, M, 7, 0, 0])
        self.assertEqual(mcp.format_value(7, 3, blank_leading=False), [0, 0, 7])
        self.assertEqual(mcp.format_value(None, 3), [B, B, B])
        with self.assertRaises(ValueError):
            mcp.format_value(1234, 3)

    def test_brightness_byte(self):
        self.assertEqual(mcp.frame([0] * 11, 0, brightness=0x0F)[7], 0x0F)


if __name__ == "__main__":
    unittest.main()
