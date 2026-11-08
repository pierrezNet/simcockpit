"""Tests du protocole Master Card, dont un rejeu d'une capture réelle (EFDE IO32 + transpondeur).

Lancer : python3 -m unittest discover -s tests -t .
"""

import os
import unittest

from simcockpit.hw.cards import EFDE_IO32, MASTERCARD, UNKNOWN, classify
from simcockpit.hw.debounce import Debouncer, GroupDebouncer
from simcockpit.hw.mastercard import Decoder, init_packet

DATA = os.path.join(os.path.dirname(__file__), "data")


def frames(name):
    with open(os.path.join(DATA, name)) as f:
        for line in f:
            t, rest = line.split("RX")
            yield float(t), bytes.fromhex(rest.strip())


def xpdr(active):
    """Code transpondeur : 3 entrées binaires par chiffre ; 12 = ON, 13 = STBY.

    Observé : en position ON, le contact STBY (13) reste aussi fermé. ON est donc prioritaire.
    """
    code = "".join(str(active[b] | active[b + 1] << 1 | active[b + 2] << 2) for b in (0, 3, 6, 9))
    mode = "ON" if active[12] else "STBY" if active[13] else "OFF"
    return code, mode


class TestDecoder(unittest.TestCase):
    def test_init_packet(self):
        self.assertEqual(init_packet(1, 4).hex(" "), "3d 00 3a 01 39 04 ff ff")

    def test_axis_only_frame_has_no_inputs(self):
        d = Decoder()
        upd = d.feed(bytes.fromhex("30 3d 00 00 00 00 00 00"))
        self.assertEqual(upd.axis, (3, 0x3D))
        self.assertFalse(upd.inputs_changed)

    def test_axis_byte_is_skipped(self):
        d = Decoder()
        upd = d.feed(bytes.fromhex("41 00 03 24 14 01 00 00"))  # état initial réel : 4444 + STBY
        self.assertEqual(upd.axis, (4, 0))
        self.assertTrue(upd.inputs_changed)
        self.assertEqual([i for i, v in enumerate(d.inputs()) if v], [2, 5, 8, 11, 13])

    def test_ninth_bit_follows_present_slots(self):
        # Bug corrigé : une trame ne concernant que le slot 1 ne doit pas effacer l'entrée 8
        d = Decoder()
        d.feed(bytes.fromhex("01 03 24 14 01 00 00 00"))
        d.feed(bytes.fromhex("31 3d 02 04 00 00 00 00"))
        self.assertEqual(d.inputs()[8], 1)
        self.assertEqual(d.inputs()[13], 0)

    def test_continuation(self):
        d = Decoder()
        self.assertFalse(d.feed(bytes.fromhex("01 ff e7 65 65 65 65 65")).inputs_changed)
        self.assertTrue(d.feed(bytes.fromhex("80 65 65 e5 65 65 65 65")).inputs_changed)
        self.assertEqual(d.slots, [0xE7, 0x65, 0x65, 0x65, 0x65, 0x65, 0x65, 0x65])
        self.assertEqual(d.ninth, 0xE5)

    def test_continuation_without_start_is_ignored(self):
        self.assertFalse(Decoder().feed(bytes.fromhex("80 00 00 00 00 00 00 00")).inputs_changed)


class TestReplay(unittest.TestCase):
    def test_transponder_capture(self):
        """Capture réelle : 4444 STBY, molettes ramenées à 2000, puis passage ON."""
        dec, grp = Decoder(), GroupDebouncer(range(14), delay=0.05)
        seen = []
        for t, pkt in frames("efde_xpdr_4444_to_2000.txt"):
            if dec.feed(pkt).inputs_changed:
                grp.update(dec.inputs(), t)
            stable = grp.poll(t)
            if stable:
                state = xpdr([int(v == EFDE_IO32.active_level) for v in stable])
                if not seen or seen[-1] != state:
                    seen.append(state)
        codes = [c for c, _ in seen]
        dedup = [c for i, c in enumerate(codes) if i == 0 or codes[i - 1] != c]
        self.assertEqual(dedup, ["4444", "3444", "2444", "2344", "2244", "2144", "2044",
                                 "2043", "2033", "2023", "2013", "2012", "2000"])
        self.assertEqual(seen[0], ("4444", "STBY"))
        self.assertEqual(seen[-1], ("2000", "ON"))

    def test_per_input_debounce_shows_transients(self):
        """Documente pourquoi le filtre de groupe est nécessaire pour les valeurs multi-bits."""
        dec, deb = Decoder(), Debouncer(72, delay=0.05)
        codes = []
        for t, pkt in frames("efde_xpdr_4444_to_2000.txt"):
            if dec.feed(pkt).inputs_changed:
                deb.update(dec.inputs(), t)
            if deb.poll(t) and deb.ready(14):
                codes.append(xpdr([int(v == 1) for v in deb.stable[:14]])[0])
        self.assertIn("2040", codes)  # code intermédiaire faux entre 2044 et 2043


class TestCards(unittest.TestCase):
    def test_classify(self):
        self.assertIs(classify("USB32I04AD"), EFDE_IO32)
        self.assertIs(classify("IOCardUSB"), MASTERCARD)
        self.assertIs(classify("mini keyboard"), UNKNOWN)
        self.assertFalse(UNKNOWN.send_init)


if __name__ == "__main__":
    unittest.main()
