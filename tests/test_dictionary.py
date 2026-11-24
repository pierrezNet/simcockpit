"""Dictionnaire des fonctions : noms logiques résolus en datarefs et commandes."""

import unittest

from simcockpit.logic import config
from simcockpit.logic.dictionary import Dictionary, DictionaryError, load_base

BASE = {
    "transpondeur.mode": {"dataref": "sim/x/transponder_mode",
                          "valeurs": {"OFF": 0, "STBY": 1, "ON": 2, "ALT": 3}},
    "pa.mode.hdg": {"commande": "avion/hdg"},
    "pa.mode.hdg.voyant": {"dataref": "avion/hdg_lt"},
    "fd.gauche": {"commande_on": "sim/fd_on", "commande_off": "sim/fd_off"},
}


def dico():
    d = Dictionary()
    d.extend(BASE, "base")
    return d


class TestResolution(unittest.TestCase):
    def test_fonction_complete(self):
        spec = dico().resolve({"type": "selector", "positions": {"ON": 12},
                               "fonction": "transpondeur.mode"}, "transpondeur.mode")
        self.assertEqual(spec["dataref"], "sim/x/transponder_mode")
        self.assertEqual(spec["dataref_values"]["STBY"], 1)
        self.assertNotIn("fonction", spec)

    def test_la_commande_du_profil_l_emporte(self):
        spec = dico().resolve({"type": "selector", "fonction": "transpondeur.mode",
                               "dataref_values": {"ON": 3}}, "x")
        self.assertEqual(spec["dataref_values"], {"ON": 3})

    def test_noms_logiques_dans_les_tableaux(self):
        d = dico()
        spec = d.resolve({"type": "commands", "inputs": {25: "pa.mode.hdg", 17: "sim/brut"}}, "x")
        self.assertEqual(spec["inputs"], {25: "avion/hdg", 17: "sim/brut"})   # « / » : gardé
        spec = d.resolve({"type": "sim_leds", "leds": {"HDG SEL": "pa.mode.hdg.voyant"}}, "x")
        self.assertEqual(spec["leds"], {"HDG SEL": "avion/hdg_lt"})

    def test_parametre_isole(self):
        spec = dico().resolve({"type": "switch", "input": 14, "command_on": "pa.mode.hdg"}, "x")
        self.assertEqual(spec["command_on"], "avion/hdg")

    def test_erreurs_claires(self):
        d = dico()
        with self.assertRaisesRegex(DictionaryError, "absente.*pa.mode.hdg"):
            d.resolve({"type": "commands", "inputs": {1: "pa.mode.hgd"}}, "mcp.boutons")
        with self.assertRaisesRegex(DictionaryError, "pas de commande.*dataref"):
            d.resolve({"type": "commands", "inputs": {1: "pa.mode.hdg.voyant"}}, "x")
        with self.assertRaisesRegex(DictionaryError, "simple commande"):
            d.resolve({"type": "switch", "input": 1, "fonction": "pa.mode.hdg"}, "x")
        with self.assertRaisesRegex(DictionaryError, "champs inconnus"):
            Dictionary().extend({"a.b": {"datref": "x/y"}}, "base")

    def test_un_avion_remplace_une_fonction(self):
        d = dico()
        d.extend({"fd.gauche": {"commande_on": "avion/up", "commande_off": "avion/dn",
                                "etat": "avion/sw", "etat_on": 2}}, "avion")
        spec = d.resolve({"type": "switch", "input": 15, "fonction": "fd.gauche"}, "x")
        self.assertEqual((spec["command_on"], spec["state_dataref"], spec["state_on"]),
                         ("avion/up", "avion/sw", 2))
        self.assertEqual(d.origin["fd.gauche"], "avion")


class TestProfils(unittest.TestCase):
    def test_base_xplane_valide(self):
        base = load_base("xplane")
        self.assertIn("transpondeur.code", base)
        self.assertTrue(all("/" not in name for name in base))

    def test_profil_bae146_en_noms_logiques(self):
        c = config.load("config/avions/bae146-jf")
        mcp = c.instruments["mcp"].controls
        self.assertEqual(mcp["boutons"].commands[19], "thranda/buttons/Button61")
        self.assertEqual(mcp["voyants"].leds["HDG SEL"], "thranda/TCAS/AnnLtA[337]")
        self.assertEqual(mcp["fd_gauche"].state_dataref, "thranda/Switch[92]")   # remplacée
        self.assertEqual(mcp["disengage"].command_on, "sim/autopilot/servos_off_any")
        mode = c.instruments["transpondeur"].controls["mode"]
        self.assertEqual(mode.push_dataref, "sim/cockpit2/radios/actuators/transponder_mode")
        self.assertIn("bae146-jf/fonctions.yaml", c.dictionary.origin["pa.engage"])
        self.assertIn("pa.engage", "\n".join(c.dictionary.describe("engage")))

    def test_profil_sans_simulateur(self):
        with self.assertRaisesRegex(config.ConfigError, "absente"):
            config.parse({"cards": {"io": {"product": "USB32I04AD"}},
                          "instruments": {"t": {"card": "io", "controls": {
                              "code": {"type": "octal_digits", "inputs": [[0, 1, 2]],
                                       "fonction": "transpondeur.code"}}}}})


if __name__ == "__main__":
    unittest.main()
