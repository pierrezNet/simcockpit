"""Périphériques USB : lecture d'une arborescence sysfs factice, historique, uevent."""

import os
import tempfile
import unittest

from pepit.hw import usb
from pepit.hw.uevent import parse


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text + "\n")


class FakeSys:
    """/sys/bus/usb/devices et /dev, dans un dossier temporaire."""

    def __init__(self, root):
        self.sysfs = os.path.join(root, "sys")
        self.dev = os.path.join(root, "dev")
        os.makedirs(self.sysfs)
        os.makedirs(os.path.join(self.dev, "input"))

    def device(self, port, vid, pid, product, manufacturer="", serial=None, cls="00",
               speed="12", power="100mA"):
        d = os.path.join(self.sysfs, port)
        for name, value in (("idVendor", vid), ("idProduct", pid), ("product", product),
                            ("manufacturer", manufacturer), ("bDeviceClass", cls),
                            ("speed", speed), ("bMaxPower", power)):
            write(os.path.join(d, name), value)
        if serial is not None:
            write(os.path.join(d, "serial"), serial)
        return d

    def node(self, devdir, rel, name, access=True):
        """Nœud sysfs (dossier) et son fichier /dev ; access=False : fichier fermé."""
        os.makedirs(os.path.join(devdir, rel, name))
        path = os.path.join(self.dev, "input", name) if name.startswith("event") \
            else os.path.join(self.dev, name)
        write(path, "")
        os.chmod(path, 0o600 if access else 0o000)

    def scan(self):
        return usb.scan(self.sysfs, self.dev)


@unittest.skipIf(os.geteuid() == 0, "root ouvre tout : l'accès refusé ne se simule pas")
class TestScan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fs = FakeSys(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_carte_mcp(self):
        d = self.fs.device("1-4.4", "0000", "0009", "IOCard-MCP", "Manuel Velez", speed="1.5")
        self.fs.node(d, "1-4.4:1.0/0003:0000:0009.0003/hidraw", "hidraw3")
        (dev,) = self.fs.scan()
        self.assertEqual((dev.vid_pid, dev.port, dev.key), ("0000:0009", "1-4.4", "0000:0009@1-4.4"))
        self.assertTrue(dev.cockpit)
        self.assertEqual(dev.speed_label, "1,5 Mbit/s (low)")
        self.assertEqual([n.path for n in dev.nodes], [os.path.join(self.fs.dev, "hidraw3")])
        self.assertEqual(dev.access, "ok")

    def test_manette_lue_par_evdev(self):
        d = self.fs.device("1-4.1.6", "044f", "0407", "TCA Q-Eng 1&2", "Thrustmaster")
        self.fs.node(d, "1-4.1.6:1.0/hid/hidraw", "hidraw5", access=False)
        self.fs.node(d, "1-4.1.6:1.0/hid/input/input24", "event24")
        (dev,) = self.fs.scan()
        self.assertEqual({n.kind for n in dev.nodes}, {"hidraw", "evdev"})
        self.assertEqual(dev.access, "ok")              # hidraw fermé, mais inutile à Pepit

    def test_inconnu_partiel_ou_refuse(self):
        d = self.fs.device("1-13", "1997", "2433", "mini keyboard")
        self.fs.node(d, "1-13:1.0/hid/hidraw", "hidraw1", access=False)
        self.fs.node(d, "1-13:1.0/hid/input/input3", "event3")
        (dev,) = self.fs.scan()
        self.assertFalse(dev.cockpit)
        self.assertEqual(dev.access, "partiel")

    def test_arduino_serie_avec_numero_de_serie(self):
        d = self.fs.device("1-2", "2341", "0043", "Arduino Uno", "Arduino", serial="85735313")
        self.fs.node(d, "1-2:1.0/tty", "ttyACM0", access=False)
        (dev,) = self.fs.scan()
        self.assertEqual(dev.key, "2341:0043:85735313")
        self.assertEqual((dev.nodes[0].kind, dev.access), ("serie", "refusé"))

    def test_concentrateur_sans_les_noeuds_de_ses_enfants(self):
        hub = self.fs.device("1-4", "1a40", "0101", "USB 2.0 Hub", cls="09", speed="480")
        child = os.path.join(hub, "1-4.4")              # comme dans sysfs : l'enfant est dedans
        os.makedirs(child)
        self.fs.node(child, "1-4.4:1.0/hid/hidraw", "hidraw3")
        hubdev = self.fs.scan()[0]
        self.assertTrue(hubdev.is_hub)
        self.assertEqual(hubdev.nodes, ())
        self.assertEqual(hubdev.pepit, "concentrateur USB")

    def test_racines_et_interfaces_ignorees(self):
        self.fs.device("1-8", "1b1c", "0c18", "H100i")
        os.makedirs(os.path.join(self.fs.sysfs, "usb1"))
        os.makedirs(os.path.join(self.fs.sysfs, "1-8:1.0"))
        self.assertEqual([d.port for d in self.fs.scan()], ["1-8"])


def dev(port="1-4.4", access_ok=True, serial=""):
    node = usb.Node("/dev/hidraw3", "hidraw", access_ok)
    return usb.UsbDevice(port=port, vid="0000", pid="0009", manufacturer="Manuel Velez",
                         product="IOCard-MCP", serial=serial, speed="1.5", max_power=100,
                         device_class="00", nodes=(node,))


class TestHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "pepit", "peripheriques.yaml")
        self.t = iter(f"2026-11-28 15:00:{i:02d}" for i in range(60))
        self.h = usb.History(self.path, clock=lambda: next(self.t))

    def tearDown(self):
        self.tmp.cleanup()

    def test_premier_releve_silencieux_puis_debranche_rebranche(self):
        self.assertEqual(self.h.update([dev()]), [])       # déjà là au lancement
        self.assertEqual([c[0] for c in self.h.update([])], ["débranché"])
        changes = self.h.update([dev()])
        self.assertEqual([c[0] for c in changes], ["branché"])
        s = self.h.seen["0000:0009@1-4.4"]
        self.assertEqual((s.plugs, s.plugged, s.first, s.cockpit), (2, True, "2026-11-28 15:00:00", True))

    def test_relu_depuis_le_fichier(self):
        self.h.update([dev()])
        self.h.update([dev(access_ok=False)])
        again = usb.History(self.path)
        s = again.seen["0000:0009@1-4.4"]
        self.assertEqual((s.name, s.ports, s.access, s.plugged),
                         ("Manuel Velez IOCard-MCP", ["1-4.4"], "refusé", True))

    def test_changement_d_acces_signale(self):
        self.h.update([dev(access_ok=False)])
        self.assertEqual([c[0] for c in self.h.update([dev(access_ok=True)])], ["accès"])

    def test_debranche_pendant_l_arret_sans_fausse_date(self):
        self.h.update([dev()])
        later = usb.History(self.path, clock=lambda: "2026-11-29 09:00:00")
        self.assertEqual(later.update([]), [])
        s = later.seen["0000:0009@1-4.4"]
        self.assertEqual((s.plugged, s.last), (False, "2026-11-28 15:00:00"))

    def test_numero_de_serie_suit_le_peripherique_de_port_en_port(self):
        self.h.update([dev(port="1-2", serial="A1")])
        self.h.update([dev(port="1-3", serial="A1")])
        self.assertEqual(self.h.seen["0000:0009:A1"].ports, ["1-2", "1-3"])


class TestUevent(unittest.TestCase):
    def test_parse(self):
        data = (b"add@/devices/pci0000:00/0000:00:14.0/usb1/1-4/1-4.4\0ACTION=add\0"
                b"DEVPATH=/devices/pci0000:00/0000:00:14.0/usb1/1-4/1-4.4\0SUBSYSTEM=usb\0"
                b"PRODUCT=0/9/100\0")
        action, props = parse(data)
        self.assertEqual((action, props["SUBSYSTEM"], props["PRODUCT"]), ("add", "usb", "0/9/100"))


if __name__ == "__main__":
    unittest.main()
