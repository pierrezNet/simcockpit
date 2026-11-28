"""Assistant d'autorisation (udev/pepit-autoriser) et préparation de la demande, sans root
ni udevadm : on vérifie les refus et les lignes produites."""

import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

from pepit.hw import authorize, usb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_helper():
    path = os.path.join(ROOT, "udev", "pepit-autoriser")
    loader = importlib.machinery.SourceFileLoader("pepit_autoriser", path)
    spec = importlib.util.spec_from_loader("pepit_autoriser", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


H = load_helper()


class TestHelper(unittest.TestCase):
    def test_entrees_refusees(self):
        for vid, pid, types in [("2341", "43", ["serie"]), ("23g1", "0043", ["serie"]),
                                ("2341", "0043", ["tout"]), ("0000", "0000", ["hidraw"]),
                                ('2341"', "0043", ["serie"]), ("2341", "0043", ["serie;rm"])]:
            with self.assertRaises(H.Refus, msg=(vid, pid, types)):
                H.check(vid, pid, types)
        self.assertEqual(H.check("2341", "0043", ["serie"]), ("2341", "0043"))
        self.assertEqual(H.check("10C4", "EA60", ["serie"]), ("10c4", "ea60"))   # minuscules

    def test_ligne_udev(self):
        self.assertEqual(
            H.rule("10c4", "ea60", "serie"),
            'SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60",'
            ' TAG+="uaccess"  # pepit 10c4:ea60 serie')
        self.assertIn('KERNEL=="event*"', H.rule("044f", "0402", "evdev"))

    def test_ajouter_deux_fois_puis_retirer(self):
        lines = H.add([], "10c4", "ea60", ["serie"])
        self.assertEqual(H.add(lines, "10c4", "ea60", ["serie"]), lines)      # pas de doublon
        lines = H.add(lines, "044f", "0402", ["hidraw", "evdev"])
        self.assertEqual(len(lines), 3)
        self.assertEqual(len(H.remove(lines, "044f", "0402")), 1)

    def test_fichier_ecrit_lu_par_pepit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "70-pepit-autorises.rules")
            H.write_lines(path, H.add(H.read_lines(path), "10c4", "ea60", ["serie"]))
            H.write_lines(path, H.add(H.read_lines(path), "10c4", "ea60", ["hidraw"]))
            with open(path) as f:
                self.assertEqual(f.read().count("# Pepit"), 1)                # un seul en-tête
            self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o644")
            self.assertEqual(authorize.authorized(path), {("10c4", "ea60"): {"serie", "hidraw"}})

    def test_peripheriques_de_ce_modele(self):
        with tempfile.TemporaryDirectory() as tmp:
            for port, vid in (("1-14", "10c4"), ("1-8", "1b1c")):
                os.makedirs(os.path.join(tmp, port))
                for name, value in (("idVendor", vid), ("idProduct", "ea60")):
                    with open(os.path.join(tmp, port, name), "w") as f:
                        f.write(value + "\n")
            self.assertEqual([os.path.basename(p) for p in H.present("10c4", "ea60", tmp)], ["1-14"])

    def test_main_refuse_sans_rien_ecrire(self):
        with mock.patch.object(H, "write_lines") as write, mock.patch.object(H, "apply") as apply:
            self.assertEqual(H.main(["ajouter", "10c4", "ea60", "../../etc"]), 2)
            self.assertEqual(H.main(["effacer", "10c4", "ea60"]), 2)
            if os.geteuid() != 0:
                self.assertEqual(H.main(["ajouter", "10c4", "ea60", "serie"]), 1)
            write.assert_not_called()
            apply.assert_not_called()


def device(product="CP2104 USB to UART Bridge Controller", maker="Silicon Labs",
           nodes=(("/dev/ttyUSB0", "serie", False),)):
    return usb.UsbDevice(port="1-14", vid="10C4", pid="EA60", manufacturer=maker,
                         product=product, serial="", speed="12", max_power=100,
                         device_class="00", nodes=tuple(usb.Node(*n) for n in nodes))


class TestDemande(unittest.TestCase):
    def test_commande(self):
        self.assertEqual(authorize.command(device()),
                         [authorize.PKEXEC, authorize.HELPER, "ajouter", "10c4", "ea60", "serie"])

    def test_rien_a_ouvrir(self):
        self.assertIsNone(authorize.command(device(nodes=(("/dev/ttyUSB0", "serie", True),))))

    def test_seulement_les_noeuds_utiles_fermes(self):
        tca = device(product="TCA Q-Eng 1&2", maker="Thrustmaster",
                     nodes=(("/dev/hidraw5", "hidraw", False), ("/dev/input/event24", "evdev", False)))
        self.assertEqual(authorize.kinds_needed(tca), ["evdev"])    # Pepit lit la TCA par evdev

    def test_mise_en_garde_hors_simulation(self):
        self.assertIsNotNone(authorize.warning(device()))
        self.assertIsNone(authorize.warning(device(product="IOCard-MCP", maker="Manuel Velez")))

    def test_installe(self):
        self.assertFalse(authorize.installed(helper="/nulle/part", policy="/nulle/part"))


if __name__ == "__main__":
    unittest.main()
