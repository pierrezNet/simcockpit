"""Écran du CDU lu dans X-Plane, et connecteur au-delà de 500 abonnements."""

import unittest

from simcockpit.logic.cdu_screen import BASE, COLUMNS, CduScreen
from simcockpit.sim import xplane


def feed(scr, line, text, styles=()):
    raw = text.encode("utf-8")
    for i, b in enumerate(raw):
        scr.on_sim(BASE.format(side=1, kind="text", line=line, i=i), b, 0)
    for i, st in enumerate(styles):
        scr.on_sim(BASE.format(side=1, kind="style", line=line, i=i), st, 0)


class TestCduScreen(unittest.TestCase):
    def test_title_and_style(self):
        # relevé réel du 737 : « INDEX 1/1 », style 0x81 (gros caractère, cyan)
        scr = CduScreen("ecran")
        feed(scr, 0, "          INDEX      1/1", [0] * 10 + [0x81] * 5)
        self.assertEqual(scr.poll(0), "INDEX      1/1")
        text, styles = scr.lines()[0]
        self.assertEqual(len(text), COLUMNS)
        self.assertEqual(styles[10], 0x81)

    def test_utf8_boxes_take_one_column(self):
        scr = CduScreen("ecran")
        feed(scr, 2, "☐☐☐☐                ☐☐☐☐")            # 3 octets par case
        self.assertEqual(scr.lines()[2][0], "☐☐☐☐                ☐☐☐☐")

    def test_subscriptions_cover_screen(self):
        self.assertEqual(len(CduScreen("ecran").sim_datarefs()), 16 * (72 + 24))
        with self.assertRaises(ValueError):
            CduScreen("ecran", side=3)


class TestManySubscriptions(unittest.TestCase):
    def test_sockets_split_by_400(self):
        xp = xplane.XPlane("127.0.0.1", 9)               # port de rejet : rien n'est reçu
        for i in range(900):
            xp.subscribe(f"sim/test/x[{i}]")
        self.assertEqual(len(xp.socks), 3)
        self.assertIs(xp._sock_for(399), xp.socks[0])
        self.assertIs(xp._sock_for(400), xp.socks[1])
        xp.close()


if __name__ == "__main__":
    unittest.main()
