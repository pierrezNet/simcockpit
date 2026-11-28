"""Noms donnés aux périphériques : enregistrés, effacés, retrouvés depuis la page Cartes."""

import os
import tempfile
import unittest

from pepit.hw import usb
from pepit.hw.names import Names


class TestNoms(unittest.TestCase):
    def test_nommer_relire_effacer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "pepit", "noms.yaml")
            names = Names(path)
            names.set("10c4:ea60:01A2B3C4", "  Écran des vitesses\n(LilyGo) ")
            names.set("wifi:40:f5:20:55:56:88", "Écran des vitesses (wifi)")
            again = Names(path)
            self.assertEqual(again.get("10c4:ea60:01A2B3C4"), "Écran des vitesses (LilyGo)")
            again.set("10c4:ea60:01A2B3C4", "")                  # vide : nom annoncé
            self.assertEqual(Names(path).get("10c4:ea60:01A2B3C4", "CP2104"), "CP2104")
            self.assertEqual(Names(path).get("wifi:40:f5:20:55:56:88"), "Écran des vitesses (wifi)")

    def test_fichier_absent_ou_abime(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(Names(os.path.join(tmp, "absent.yaml")).names, {})
            bad = os.path.join(tmp, "abime.yaml")
            with open(bad, "w") as f:
                f.write("[pas : un dictionnaire\n")
            self.assertEqual(Names(bad).names, {})

    def test_cle_depuis_la_page_cartes(self):
        with tempfile.TemporaryDirectory() as sysfs:
            os.makedirs(os.path.join(sysfs, "1-14"))
            with open(os.path.join(sysfs, "1-14", "serial"), "w") as f:
                f.write("01A2B3C4\n")
            os.makedirs(os.path.join(sysfs, "1-4.4"))              # carte OpenCockpits : sans n°
            self.assertEqual(usb.key_for("10c4:ea60", "1-14", sysfs), "10c4:ea60:01A2B3C4")
            self.assertEqual(usb.key_for("0000:0009", "1-4.4", sysfs), "0000:0009@1-4.4")


if __name__ == "__main__":
    unittest.main()
