"""Tests de la logique des assistants (sans carte)."""

import unittest

from simcockpit.diag.input_check import TerminalProbe, TerminalResult, summarize
from simcockpit.diag.output_check import segments_for
from simcockpit.hw.mastercard import output_location, output_report

REST = [0] * 72


class TestProbe(unittest.TestCase):
    def test_push_button(self):
        p = TerminalProbe(1, REST)
        p.feed(5, 1, 1.0)
        self.assertFalse(p.done(1.1))           # encore appuyé
        p.feed(5, 0, 1.5)
        self.assertTrue(p.done(1.5))
        r = p.result()
        self.assertEqual((r.status, r.indexes, r.released), ("ok", [5], True))

    def test_toggle_switch_held(self):
        p = TerminalProbe(2, REST)
        p.feed(12, 1, 1.0)
        self.assertFalse(p.done(1.5))
        self.assertTrue(p.done(2.1))            # stable 1 s sans relâcher
        self.assertFalse(p.result().released)

    def test_bridged(self):
        p = TerminalProbe(3, REST)
        p.feed(3, 1, 1.0)
        p.feed(4, 1, 1.01)
        p.feed(3, 0, 1.5)
        p.feed(4, 0, 1.5)
        self.assertEqual(p.result().status, "pontée")
        self.assertEqual(p.result().indexes, [3, 4])

    def test_noisy_ignored_and_silent(self):
        p = TerminalProbe(4, REST, ignore={7})
        p.feed(7, 1, 1.0)
        self.assertFalse(p.done(5.0))
        self.assertEqual(p.result().status, "muette")

    def test_active_at_rest_input_detected_on_release(self):
        base = list(REST)
        base[1] = 1                             # ex. molette du transpondeur sur 2
        p = TerminalProbe(2, base)
        p.feed(1, 0, 1.0)
        p.feed(1, 1, 1.4)
        self.assertEqual(p.result().indexes, [1])

    def test_summary(self):
        res = [TerminalResult(1, "ok", [0]), TerminalResult(2, "ok", [0]),
               TerminalResult(3, "muette"), TerminalResult(4, "pontée", [3, 4])]
        s = summarize(res, noisy=[9])
        self.assertEqual(s["mapping"], {1: 0, 2: 0})
        self.assertEqual(s["doublons"], {0: [1, 2]})
        self.assertEqual(s["muettes"], [3])
        self.assertEqual(s["instables"], [9])


class TestOutputs(unittest.TestCase):
    def test_report_matches_libiocards(self):
        self.assertEqual(output_report(0, 0b101).hex(" "), "0b 05 ff ff ff ff ff ff")
        self.assertEqual(output_report(3, 0xFF)[0], 11 + 24)
        self.assertEqual(output_report(1, 0, card=1)[0], 64 + 8 + 11)

    def test_location(self):
        self.assertEqual(output_location(11), (0, 0))
        self.assertEqual(output_location(42), (3, 7))
        self.assertEqual(segments_for(11, 42), [0, 1, 2, 3])
        with self.assertRaises(ValueError):
            output_location(10)



class TestDisplays(unittest.TestCase):
    def test_pairs_value_position(self):
        from simcockpit.hw.mastercard import BLANK, display_reports
        reps = display_reports({0: 0, 1: 1, 2: 2, 3: 3, 4: 4})
        self.assertEqual([r.hex(" ") for r in reps],
                         ["00 00 01 01 02 02 03 03", "04 04 ff ff ff ff ff ff"])
        self.assertEqual(display_reports({5: BLANK})[0][:2], bytes([0x0A, 5]))


if __name__ == "__main__":
    unittest.main()
