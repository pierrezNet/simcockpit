"""Manettes des gaz : TQ à deux manettes sur quatre moteurs (sans matériel)."""

import struct
import unittest

from pepit.hw import evdev
from pepit.logic import config
from pepit.logic.engine import Engine
from pepit.logic.throttle import ThrottleAxis

T0, T1 = (f"sim/cockpit2/engine/actuators/throttle_ratio[{i}]" for i in range(2))
H0, H1, H2, H3 = (f"thranda/cockpit/Throttle[{i}]" for i in range(4))     # manettes du 146


class TestThrottleAxis(unittest.TestCase):
    def setUp(self):
        # TCA Q-Eng : 0 = plein gaz, cran vers 0,72, fond de la reverse à 1
        self.m = ThrottleAxis("gauche", axis=0, datarefs=[T0, T1], ralenti=0.70, plein_gaz=0.03)
        self.m.sim_connected = True

    def test_poussee_entre_le_cran_et_le_plein_gaz(self):
        self.assertEqual(self.m.thrust(0.0), 1.0)          # au-delà du plein gaz
        self.assertEqual(self.m.thrust(0.03), 1.0)
        self.assertAlmostEqual(self.m.thrust(0.365), 0.5)
        self.assertEqual(self.m.thrust(0.717), 0.0)        # sur le cran
        self.assertEqual(self.m.thrust(0.99), 0.0)         # zone de reverse : ralenti

    def test_ecrit_les_deux_moteurs_au_plus_30_fois_par_seconde(self):
        self.m.on_axis(0, 0.365, 1.0)
        self.m.poll(1.0)
        self.assertEqual(self.m.take_sim_actions(), [("dref", T0, 0.5), ("dref", T1, 0.5)])
        self.m.on_axis(0, 0.30, 1.01)                       # trop tôt : différé
        self.m.poll(1.01)
        self.assertEqual(self.m.take_sim_actions(), [])
        self.m.poll(1.05)                                   # rattrapé au poll suivant
        self.assertEqual(len(self.m.take_sim_actions()), 2)
        self.m.on_axis(0, 0.3001, 1.2)                      # écart négligeable : rien
        self.m.poll(1.2)
        self.assertEqual(self.m.take_sim_actions(), [])
        self.m.on_axis(1, 0.0, 1.3)                         # autre axe : ignoré
        self.assertNotEqual(self.m.ratio, 1.0)

    def test_ralenti_toujours_atteint_et_poussee_renvoyee_a_la_connexion(self):
        self.m.on_axis(0, 0.69, 1.0)                        # juste au-dessus du ralenti
        self.m.poll(1.0)
        self.m.take_sim_actions()
        self.m.on_axis(0, 0.72, 2.0)                        # le cran : 0 exactement
        self.m.poll(2.0)
        self.assertEqual(self.m.take_sim_actions(), [("dref", T0, 0.0), ("dref", T1, 0.0)])
        self.m.sim_sync()
        self.assertEqual(len(self.m.take_sim_actions()), 2)

    def test_sans_x_plane_rien_n_est_ecrit(self):
        self.m.sim_connected = False
        self.m.on_axis(0, 0.2, 1.0)
        self.m.poll(1.0)
        self.assertEqual(self.m.take_sim_actions(), [])
        self.assertIn("poussée", self.m.summary())


class TestProfil(unittest.TestCase):
    def test_bae146_deux_manettes_quatre_moteurs(self):
        eng = Engine(config.load("config/avions/bae146-jf"))
        m = eng.cockpit.instruments["manettes"].controls
        self.assertEqual(m["gauche"].datarefs, [H0, H1])
        self.assertEqual(m["droite"].datarefs, [H2, H3])
        eng.sim_step({}, True, 0.5)
        eng.axis("tq", 1, 0.03, 1.0)                        # manette droite plein gaz
        eng.poll(1.0)
        actions = eng.sim_step({}, True, 1.0)
        self.assertIn(("dref", H2, 1.0), actions)
        self.assertIn(("dref", H3, 1.0), actions)
        self.assertNotIn(("dref", H0, 1.0), actions)
        eng.axis("tq", 0, 0.99, 2.0)                        # manette gauche tout en arrière
        eng.poll(2.0)
        actions = eng.sim_step({}, True, 2.0)
        self.assertIn(("dref", H0, -0.1), actions)          # OFF : carburant coupé


class TestCoupure(unittest.TestCase):
    """BAe 146 : pas d'inverseur, OFF derrière le ralenti ; injection en revenant au cran."""

    def setUp(self):
        self.m = ThrottleAxis("gauche", axis=0, datarefs=[H0], ralenti=0.70, plein_gaz=0.03,
                              coupure=0.80, valeur_coupure=-0.1)
        self.m.sim_connected = True

    def move(self, position, t):
        self.m.on_axis(0, position, t)
        self.m.poll(t)
        return self.m.take_sim_actions()

    def test_off_puis_injection_au_cran(self):
        self.assertEqual(self.move(0.99, 1.0), [("dref", H0, -0.1)])
        self.assertTrue(self.m.cutoff)
        self.assertEqual(self.move(0.78, 2.0), [])          # hystérésis : toujours OFF
        self.assertTrue(self.m.cutoff)
        self.assertEqual(self.move(0.72, 3.0), [("dref", H0, 0.0)])   # le cran : ralenti
        self.assertFalse(self.m.cutoff)
        self.assertEqual(self.move(0.79, 4.0), [])          # près du seuil : pas de coupure

    def test_reglages_incoherents(self):
        with self.assertRaisesRegex(ValueError, "valeur_coupure"):
            ThrottleAxis("x", axis=0, datarefs=[H0], ralenti=0.7, plein_gaz=0.03, coupure=0.8)
        with self.assertRaisesRegex(ValueError, "derrière le ralenti"):
            ThrottleAxis("x", axis=0, datarefs=[H0], ralenti=0.7, plein_gaz=0.03, coupure=0.5,
                         valeur_coupure=-0.1)


class TestEvdev(unittest.TestCase):
    def test_evenements_et_normalisation(self):
        data = struct.pack("llHHi", 0, 0, evdev.EV_ABS, 1, 47002) + \
            struct.pack("llHHi", 0, 0, evdev.EV_KEY, 299, 1)
        self.assertEqual(evdev.parse_events(data), [(3, 1, 47002), (1, 299, 1)])
        self.assertAlmostEqual(evdev.normalize(47002, 0, 65535), 0.7172, places=3)
        self.assertEqual(evdev.normalize(70000, 0, 65535), 1.0)


if __name__ == "__main__":
    unittest.main()
