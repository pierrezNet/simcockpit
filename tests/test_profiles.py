"""Profils d'avion choisis selon l'avion chargé, et lancement d'X-Plane (sans X-Plane)."""

import os
import tempfile
import unittest

from pepit.logic import config, profiles
from pepit.sim import launcher


class TestCodes(unittest.TestCase):
    def test_formes_acceptees(self):
        self.assertEqual(config.aircraft_codes("b738"), ("B738",))
        self.assertEqual(config.aircraft_codes(["B461", "B462"]), ("B461", "B462"))
        self.assertEqual(config.aircraft_codes(None), ())

    def test_refus(self):
        for bad in (["B4 62"], "B46200", 146, [None]):
            with self.assertRaises(config.ConfigError):
                config.aircraft_codes(bad)

    def test_profils_du_depot(self):
        found = {p.name: p.aircraft for p in profiles.list_profiles()}
        self.assertIn("B462", found["bae146-jf"])
        self.assertEqual(found["b738-laminar"], ("B738",))
        self.assertEqual(found["rj85-simule"], ())                 # sans simulateur
        self.assertEqual(config.load("config/avions/bae146-jf").sim["aircraft"],
                         ("B461", "B462", "B463"))


class TestChoix(unittest.TestCase):
    def setUp(self):
        self.list = [profiles.Profile("config/avions/bae146-jf", "bae146-jf", ("B461", "B462")),
                     profiles.Profile("config/avions/b738-laminar", "b738-laminar", ("B738",))]

    def test_avion_connu(self):
        self.assertEqual(profiles.profile_for("B462", self.list).name, "bae146-jf")
        self.assertEqual(profiles.profile_for("b738", self.list).name, "b738-laminar")

    def test_avion_sans_profil(self):
        self.assertIsNone(profiles.profile_for("C172", self.list))
        self.assertIsNone(profiles.profile_for("", self.list))

    def test_meme_dossier(self):
        self.assertTrue(profiles.same("config/avions/bae146-jf/", "config/avions/bae146-jf"))
        self.assertFalse(profiles.same("config/avions/bae146-jf", "config/avions/b738-laminar"))


class TestLanceur(unittest.TestCase):
    def test_processus_trouve_par_son_nom(self):
        with tempfile.TemporaryDirectory() as proc:
            for pid, comm in (("12", "bash"), ("345", "X-Plane-x86_64"), ("self", "x")):
                os.makedirs(os.path.join(proc, pid))
                with open(os.path.join(proc, pid, "comm"), "w") as f:
                    f.write(comm + "\n")
            self.assertTrue(launcher.running("/home/x/X-Plane 12/X-Plane-x86_64", proc))
            self.assertFalse(launcher.running("/opt/autre/Simulateur", proc))
            self.assertFalse(launcher.running("", proc))

    def test_executable_absent(self):
        with self.assertRaises(OSError):
            launcher.launch("/nulle/part/X-Plane-x86_64")
        self.assertFalse(launcher.usable(""))


if __name__ == "__main__":
    unittest.main()
