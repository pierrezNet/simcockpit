"""Application Pepit : instance unique et options des lanceurs (sans fenêtre)."""

import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication  # noqa: E402

from pepit.app import instance  # noqa: E402
from pepit.app.main import parse  # noqa: E402

APP = QCoreApplication.instance() or QCoreApplication([])


class TestInstance(unittest.TestCase):
    def setUp(self):
        self.name = f"pepit-test-{os.getpid()}-{time.monotonic_ns()}"

    def wait(self, received, n=1):
        end = time.monotonic() + 2
        while len(received) < n and time.monotonic() < end:
            APP.processEvents()
            time.sleep(0.01)

    def test_sans_instance_le_lanceur_le_sait(self):
        self.assertFalse(instance.send("afficher\tcartes", name=self.name, timeout=100))

    def test_le_second_lanceur_transmet_sa_page(self):
        canal = instance.Instance(self.name)
        self.assertTrue(canal.listen())
        received = []
        canal.message.connect(received.append)
        try:
            self.assertTrue(instance.send(instance.encode("afficher", "peripheriques"), name=self.name))
            self.assertTrue(instance.send(instance.encode("afficher", "simulateur",
                                                          "config/avions/bae146-jf"), name=self.name))
            self.wait(received, 2)
        finally:
            canal.close()
        self.assertEqual([instance.decode(m) for m in received],
                         [["afficher", "peripheriques"],
                          ["afficher", "simulateur", "config/avions/bae146-jf"]])

    def test_canal_abandonne_repris(self):
        premier = instance.Instance(self.name)
        self.assertTrue(premier.listen())
        premier.close()                          # Pepit arrêté : le canal est libre
        second = instance.Instance(self.name)
        self.assertTrue(second.listen())
        second.close()


class TestOptions(unittest.TestCase):
    def test_pages_et_profil(self):
        a = parse(["--page", "cartes"])
        self.assertEqual((a.page, a.fond, a.profil), ("cartes", False, None))
        a = parse(["--page", "simulateur", "config/avions/bae146-jf"])
        self.assertEqual(a.profil, "config/avions/bae146-jf")
        self.assertTrue(parse(["--fond"]).fond)
        with self.assertRaises(SystemExit):
            parse(["--page", "inconnue"])


if __name__ == "__main__":
    unittest.main()
