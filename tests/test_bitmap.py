"""Tests du protocole « bitmap » (OpenCockpits IOCard-MCP), sur capture réelle."""

import unittest

from simcockpit.hw.bitmap import BitmapDecoder
from simcockpit.hw.cards import OC_MCP, classify
from simcockpit.hw.debounce import Debouncer
from tests.test_mastercard import frames


class TestBitmap(unittest.TestCase):
    def test_classify(self):
        self.assertIs(classify("IOCard-MCP"), OC_MCP)

    def test_full_state_and_index(self):
        d = BitmapDecoder()
        self.assertTrue(d.feed(bytes.fromhex("a5 5d ff 3f 02 b3 60 8e")).inputs_changed)
        self.assertFalse(d.feed(bytes.fromhex("a5 5d ff 3f 02 b3 60 8e")).inputs_changed)
        bits = d.inputs()
        self.assertEqual(len(bits), 72)
        self.assertEqual(bits[0], 1)        # octet 0 = a5 -> bit 0 = 1
        self.assertEqual(bits[1], 0)
        self.assertEqual(bits[31], 0)       # octet 3 = 3f -> bit 7 = 0
        self.assertTrue(d.feed(bytes.fromhex("a5 5d ff bf 02 b3 60 8e")).inputs_changed)
        self.assertEqual(d.inputs()[31], 1)

    def test_capture_events(self):
        """Interrupteur (31), poussoirs (30 et 15) vus après anti-rebond, comme dans l'analyse."""
        dec, deb = BitmapDecoder(), Debouncer(72, delay=0.03)
        events = []
        for t, pkt in frames("mcp_after_init.txt"):
            if dec.feed(pkt).inputs_changed:
                deb.update(dec.inputs(), t)
            events += [(i, new) for i, old, new in deb.poll(t) if old is not None]
        self.assertEqual([v for i, v in events if i == 31], [1, 0, 1])   # interrupteur
        self.assertEqual([v for i, v in events if i == 30], [1, 0, 1, 0])  # poussoir ×2
        self.assertEqual([v for i, v in events if i == 15], [1, 0])        # poussoir
        moved = {i for i, _ in events}
        self.assertFalse(moved & set(range(16, 24)))   # octet 2 jamais touché
        self.assertTrue(moved <= set(range(8)) | {15, 30, 31})


if __name__ == "__main__":
    unittest.main()
