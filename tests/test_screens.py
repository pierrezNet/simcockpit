"""Écrans physiques : cadrage et fichier de réglage (sans Qt)."""

import tempfile
import unittest
from pathlib import Path

from pepit.hw import screens


class TestScreens(unittest.TestCase):
    def test_zone_utile(self):
        self.assertEqual(screens.content_rect(1024, 768, [0, 0, 0, 0]), (0, 0, 1024, 768))
        self.assertEqual(screens.content_rect(1024, 768, [40, 20, 60, 10]), (40, 20, 924, 738))
        # marges trop grandes : la zone garde une taille minimale et reste dans l'écran
        x, y, w, h = screens.content_rect(1024, 768, [2000, 0, 0, 0])
        self.assertEqual((w, x), (screens.MIN_SIZE, 1024 - screens.MIN_SIZE))

    def test_fichier(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ecrans.yaml"
            self.assertEqual(screens.load_screens(path), {})
            screens.save_screens({"cdu1": screens.ScreenSetup("HDMI-2", [12, 8, 12, 30]),
                                  "cdu2": screens.ScreenSetup("")}, path)    # sans écran : omis
            back = screens.load_screens(path)
            self.assertEqual(list(back), ["cdu1"])
            self.assertEqual((back["cdu1"].output, back["cdu1"].margins), ("HDMI-2", [12, 8, 12, 30]))
            path.write_text("cdu1:\n  sortie: HDMI-2\n  marges: [5]\n", encoding="utf-8")
            self.assertEqual(screens.load_screens(path)["cdu1"].margins, [5, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()
