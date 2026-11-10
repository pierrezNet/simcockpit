"""Logique de l'indicateur DME IND-42C, sans matériel."""

import unittest

from simcockpit.hw import dme
from simcockpit.logic.dme_indicator import DmeIndicator

SEL, PWR = 0, 1


def state(sel=0, pwr=0):
    s = [0] * 72
    s[SEL], s[PWR] = sel, pwr
    return s


class TestDmeIndicator(unittest.TestCase):
    def setUp(self):
        self.d = DmeIndicator("dme", self_test=2.0)
        self.d.set_sim(distance=3.2, groundspeed=240, ident="lil")
        self.d.restart()                       # comme à la connexion de la carte
        self.d.poll(0.0)

    def frames(self):
        return [f for _, f in self.d.take_frames()]

    def boot(self):
        self.frames()
        self.d.poll(2.0)                       # fin du test des segments
        return self.frames()

    def press_sel(self, t, duration=0.06):
        self.d.update(state(sel=1), t)
        self.d.poll(t + duration)
        self.d.update(state(sel=0), t + duration)
        self.d.poll(t + duration + 0.02)

    def test_power_on_sequence(self):
        self.assertEqual(self.frames(), [dme.command(dme.ON)])
        self.assertTrue(self.d.testing)
        self.d.poll(1.0)
        self.assertEqual(self.frames(), [])        # rien pendant le test des segments
        out = self.boot()
        self.assertEqual(out[0], dme.command(dme.CLEAR))
        self.assertIn(dme.distance(3.2), out)
        self.assertIn(dme.right_text("LIL"), out)
        self.assertIn(dme.annunciator("canal", "1"), out)
        self.assertIn(dme.annunciator("unite_gauche", "NM"), out)
        self.assertIn(dme.annunciator("unite_droite", "ID"), out)
        self.assertEqual(self.d.summary(), "3.2 NM · LIL ID")

    def test_cold_restart_turns_off_first(self):
        self.frames()
        self.d.restart(cold=True)                 # connexion : le DME est peut-être déjà allumé
        self.assertEqual(self.frames(), [dme.command(dme.OFF), dme.command(dme.ON)])

    def test_sel_cycles_id_kt_min(self):
        self.boot()
        self.press_sel(3.0)
        self.assertEqual(self.d.mode, "KT")
        self.assertEqual(self.frames(), [dme.right_text("240", align_right=True),
                                         dme.annunciator("unite_droite", "KT")])
        self.press_sel(4.0)
        self.assertEqual(self.d.mode, "MIN")      # 3,2 NM à 240 kt = 0,8 min → « 1 »
        self.assertIn(dme.right_text("1", align_right=True), self.frames())
        self.press_sel(5.0)
        self.assertEqual(self.d.mode, "ID")

    def test_sel_acts_on_press(self):
        self.boot()
        self.d.update(state(sel=1), 3.0)          # dès l'appui, sans attendre le relâchement
        self.assertEqual(self.d.mode, "KT")
        self.d.update(state(sel=0), 3.06)
        self.assertEqual(self.d.mode, "KT")

    def test_pwr_toggles(self):
        self.boot()
        self.d.update(state(pwr=1), 3.0)
        self.d.update(state(pwr=0), 3.06)
        self.assertFalse(self.d.powered)
        self.assertEqual(self.frames(), [dme.command(dme.OFF)])
        self.press_sel(4.0)                       # sans effet éteint
        self.assertEqual(self.d.mode, "ID")
        self.d.update(state(pwr=1), 5.0)
        self.assertTrue(self.d.testing)
        self.assertEqual(self.frames(), [dme.command(dme.ON)])

    def test_no_signal_shows_dashes(self):
        self.boot()
        self.d.set_sim(distance=None, groundspeed=None, ident="")
        out = self.frames()
        self.assertIn(dme.no_distance(), out)
        self.assertIn(dme.right_text("---", align_right=True), out)   # ID sans signal
        self.press_sel(3.0)                       # KT sans signal : toujours des tirets
        self.assertIsNone(self.d.fields()[1])

    def test_no_repeated_frames(self):
        self.boot()
        self.d.set_sim(distance=3.2)              # rien n'a changé à l'écran
        self.assertEqual(self.frames(), [])
        self.d.set_sim(distance=3.1)
        self.assertEqual(self.frames(), [dme.distance(3.1)])

    def test_time_needs_groundspeed(self):
        self.boot()
        self.d.set_sim(groundspeed=10)
        self.press_sel(3.0)
        self.press_sel(4.0)                       # MIN à 10 kt : tirets
        self.assertEqual(self.d.fields()[1], None)


if __name__ == "__main__":
    unittest.main()
