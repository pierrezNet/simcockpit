"""Écran de l'UFMC (BAe 146) lu par l'API web d'X-Plane : décodage, WebSocket, moteur."""

import base64
import unittest

from pepit.logic import config
from pepit.logic.engine import Engine
from pepit.logic.ufmc_screen import COLUMNS, LARGE, decode_line
from pepit.sim import xplane_web


def sizes(styles):
    return "".join("G" if s & LARGE else "p" for s in styles)


class TestDecode(unittest.TestCase):
    """Lignes relevées le 2026-11-17 sur la page PERF INIT, comparées à la capture de l'avion."""

    def line(self, raw, row):
        text, styles = decode_line(raw.encode("latin-1"), row)
        self.assertEqual(len(text), COLUMNS)
        return text, sizes(styles)

    def test_libelles_en_petits_caracteres_majuscules(self):
        text, size = self.line(" GW/CRZ CG  trip/Crz Alt ", 1)
        self.assertEqual(text, " GW/CRZ CG  TRIP/CRZ ALT ")
        self.assertEqual(size, "p" * COLUMNS)

    def test_code_petits_caracteres_et_calage_a_droite(self):
        text, size = self.line("---.- / 10.1;2CALC    100", 4)
        self.assertEqual(text, "---.- / 10.1CALC      100")      # 100 sous FL100
        self.assertEqual(size[12:16], "pppp")                     # CALC en petit
        self.assertEqual(size[-3:], "GGG")

    def test_cases_et_degre(self):
        text, size = self.line("[][][][]          -35=;2c", 6)
        self.assertEqual(text, "□□□□                -35°C")
        self.assertEqual(size[-5:], "GGGGp")                      # le C en petit

    def test_ligne_pleine_inchangee(self):
        self.assertEqual(self.line("<83.3/16.7%   FL287/FL100", 2)[0], "<83.3/16.7%   FL287/FL100")
        self.assertEqual(self.line("", 13)[0], " " * COLUMNS)


class TestWebSocket(unittest.TestCase):
    def test_trames(self):
        frame = xplane_web.ws_frame(b'{"a":1}', mask=b"\x01\x02\x03\x04")
        self.assertEqual(xplane_web.parse_frame(frame), (True, 1, b'{"a":1}', len(frame)))
        self.assertIsNone(xplane_web.parse_frame(frame[:5]))
        big = bytes(range(256)) * 2                                # longueur sur 16 bits
        frame = xplane_web.ws_frame(big)
        self.assertEqual(xplane_web.parse_frame(frame)[2], big)
        server = bytes([0x81, 3]) + b"abc"                         # trame serveur, non masquée
        self.assertEqual(xplane_web.parse_frame(server + b"x"), (True, 1, b"abc", 5))

    def test_valeur_texte_en_base64(self):
        raw = b"<INDEX\x00\x00"
        self.assertEqual(xplane_web.decode_value(base64.b64encode(raw).decode()), raw)
        self.assertEqual(xplane_web.decode_value(1.0), 1.0)


class TestEngine(unittest.TestCase):
    def test_lignes_aiguillees_vers_l_ecran(self):
        eng = Engine(config.load("config/avions/bae146-jf"))
        ecran = eng.cockpit.instruments["cdu"].controls["ecran"]
        self.assertIn("FJCC/UFMC/LINE_1", eng._web_refs)
        self.assertNotIn("FJCC/UFMC/LINE_1", [r for r in eng._sim_listeners
                                               if r not in eng._web_refs])
        eng.sim_step({"FJCC/UFMC/LINE_1": b"       PERF INIT       \x00"}, True, 1.0)
        self.assertEqual(ecran.poll(1.0), "PERF INIT")


if __name__ == "__main__":
    unittest.main()
