"""Jauges FDBUS reliées au simulateur : configuration, modules, trames (sans matériel)."""

import unittest

from pepit.hw import fdbus
from pepit.logic import config
from pepit.logic.engine import Engine

CALS = {
    (250, 1): fdbus.Calibration({0: 10, 18: 158, 24: 202, 33: 255}, 49, "Volets", "°"),
    (251, 1): fdbus.Calibration({-5000: 0, 0: 133, 5000: 255}, 2, "Vitesse verticale", "ft/min"),
}
VS = "sim/cockpit2/gauges/indicators/vvi_fpm_pilot"
FLAPS = "sim/flightmodel2/wing/flap1_deg[0]"


def cockpit(controls, product="FDBUS", cals=CALS):
    return config.parse({
        "cards": {"jauges": {"product": product}},
        "instruments": {"jauges": {"card": "jauges", "controls": controls}},
        "sim": {"type": "xplane"},
    }, calibrations=cals)


BOTH = {"vs": {"type": "gauge", "gauge": "vitesse verticale", "dataref": VS},
        "volets": {"type": "gauge", "gauge": "Volets", "dataref": FLAPS}}
MODULES = [fdbus.Module(250, 49, 0, {"Mini1": 10, "Maxi1": 255}),
           fdbus.Module(251, 2, 1, {"Mini1": 0, "Maxi1": 255})]


def frames(engine):
    """Trames en attente, horloge avancée d'une seconde par trame (écart d'écriture)."""
    out = []
    while True:
        engine._clock = getattr(engine, "_clock", 1e9) + 1
        f = engine.take_frame("jauges", now=engine._clock)
        if f is None:
            return out
        out.append(f[:3].hex(" "))


class TestGauges(unittest.TestCase):
    def setUp(self):
        self.engine = Engine(cockpit(BOTH))
        self.ctrls = self.engine.cockpit.instruments["jauges"].controls

    def test_nom_du_banc_vers_sortie_et_etalonnage(self):
        vs = self.ctrls["vs"]
        self.assertEqual((vs.address, vs.channel, vs.unit), (251, 1, "ft/min"))
        self.assertEqual(self.engine.cockpit.cards["jauges"].product, "FDBUS")

    def test_repos_apres_init_puis_valeurs_du_simulateur(self):
        self.engine.bus_ready("jauges", MODULES)
        self.engine.poll(0)
        # repos : volets 0° → 10, IVSI 0 ft/min → 133 ; 1re commande doublée
        self.assertEqual(frames(self.engine), ["03 fb 85", "03 fb 85", "03 fa 0a", "03 fa 0a"])
        self.engine.sim_step({VS: -2500.0, FLAPS: 18.0}, True, 1.0)
        self.engine.poll(1)
        self.assertEqual(sorted(frames(self.engine)), ["03 fa 9e", "03 fb 42"])
        self.engine.sim_step({VS: -2500.4}, True, 1.1)     # même position : rien
        self.engine.poll(1.1)
        self.assertEqual(frames(self.engine), [])
        self.assertAlmostEqual(self.ctrls["volets"].shown_value, 18)
        self.engine.sim_step({}, False, 2.0)               # X-Plane perdu : repos
        self.engine.poll(2)
        self.assertEqual(sorted(frames(self.engine)), ["03 fa 0a", "03 fb 85"])

    def test_valeur_bornee_au_cadran(self):
        self.engine.bus_ready("jauges", MODULES)
        self.ctrls["vs"].set_value(9000)
        self.assertEqual(self.ctrls["vs"].position, 255)
        self.assertAlmostEqual(self.ctrls["vs"].shown_value, 5000)

    def test_module_absent_ou_d_un_autre_type(self):
        self.engine.bus_ready("jauges", [fdbus.Module(251, 49, 0)])
        self.assertIn("type 49", self.ctrls["vs"].problem)
        self.assertIn("absent", self.ctrls["volets"].problem)
        self.ctrls["vs"].set_value(1000)
        self.engine.poll(0)
        self.assertEqual(frames(self.engine), [])           # rien n'est envoyé
        self.assertIn("modules 251", self.engine.status["jauges"])

    def test_reinit_du_bus_redouble_la_premiere_commande(self):
        self.engine.bus_ready("jauges", MODULES)
        self.engine.poll(0)
        frames(self.engine)
        self.engine.resend_all("jauges")                    # carte rebranchée
        self.assertIsNotNone(self.ctrls["vs"].problem)
        self.engine.bus_ready("jauges", MODULES)
        self.engine.poll(1)
        self.assertEqual(len(frames(self.engine)), 4)

    def test_erreurs_de_configuration(self):
        with self.assertRaisesRegex(config.ConfigError, "inconnue.*Vitesse verticale, Volets"):
            cockpit({"x": {"type": "gauge", "gauge": "Essence"}})
        with self.assertRaisesRegex(config.ConfigError, "carte EFDE FDBUS"):
            cockpit({"x": {"type": "gauge", "gauge": "Volets"}}, product="USB32I04AD")
        with self.assertRaisesRegex(config.ConfigError, "deux repères"):
            cockpit({"x": {"type": "gauge", "gauge": "Volets"}},
                    cals={(250, 1): fdbus.Calibration({0: 10}, 49, "Volets")})

    def test_profil_bae146(self):
        c = config.load("config/avions/bae146-jf")
        self.assertIn("jauges", c.instruments)
        self.assertEqual(c.cards["jauges"].product, "FDBUS")


if __name__ == "__main__":
    unittest.main()
