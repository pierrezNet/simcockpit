"""Cartes wifi (IOCP) : identité par la table ARP, historique séparé de l'USB, relevé
par le moteur sur un vrai serveur IOCP local."""

import os
import tempfile
import time
import unittest

from pepit.hw import network, usb
from pepit.logic import config
from pepit.logic.config import CardSpec
from pepit.logic.engine import Engine
from tests.test_iocp import FakeCard

ARP = """IP address       HW type     Flags       HW address            Mask     Device
192.168.1.51     0x1         0x2         40:F5:20:55:56:88     *        eno1
192.168.1.1      0x1         0x2         aa:bb:cc:dd:ee:ff     *        eno1
192.168.1.77     0x1         0x0         00:00:00:00:00:00     *        eno1
"""


class TestIdentite(unittest.TestCase):
    def test_table_arp(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(ARP)
        try:
            table = network.arp_table(f.name)
        finally:
            os.unlink(f.name)
        self.assertEqual(table, {"192.168.1.51": "40:f5:20:55:56:88",
                                 "192.168.1.1": "aa:bb:cc:dd:ee:ff"})   # incomplète : ignorée

    def test_fabricant(self):
        self.assertEqual(network.vendor("40:f5:20:55:56:88"), "Espressif (ESP8266 / ESP32)")
        self.assertEqual(network.vendor("aa:bb:cc:dd:ee:ff"), "")

    def test_plages_de_variables(self):
        self.assertEqual(network.ranges([203, 201, 202, 210, 212, 213]), "201 à 203, 210, 212, 213")

    def test_carte(self):
        d = network.NetDevice("192.168.1.51", "40:f5:20:55:56:88", 8092, (201, 202, 203),
                              ("arduino_carburant",))
        self.assertEqual((d.key, d.name, d.port), ("wifi:40:f5:20:55:56:88", "arduino_carburant",
                                                   "192.168.1.51"))
        self.assertIn("201 à 203", d.pepit)
        self.assertEqual(network.NetDevice("192.168.1.9", "", 8092, ()).key, "wifi@192.168.1.9")


class TestHistorique(unittest.TestCase):
    def test_wifi_et_usb_separes(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = usb.History(os.path.join(tmp, "p.yaml"), clock=lambda: "2026-11-28 17:00:00")
            mcp = usb.UsbDevice("1-4.4", "0000", "0009", "Manuel Velez", "IOCard-MCP", "", "1.5",
                                100, "00", (usb.Node("/dev/hidraw3", "hidraw", True),))
            carte = network.NetDevice("192.168.1.51", "40:f5:20:55:56:88", 8092, (201,),
                                      ("arduino_carburant",))
            h.update([mcp], "usb")
            h.update([carte], "wifi")
            h.update([carte], "wifi")
            self.assertEqual(h.update([], "wifi")[0][0], "débranché")   # carte wifi partie
            self.assertTrue(h.seen[mcp.key].plugged)                     # l'USB n'a pas bougé
            again = usb.History(h.path)
            s = again.seen["wifi:40:f5:20:55:56:88"]
            self.assertEqual((s.kind, s.extra["fabricant"], s.ports),
                             ("wifi", "Espressif (ESP8266 / ESP32)", ["192.168.1.51"]))
            self.assertEqual(again.seen[mcp.key].kind, "usb")


class TestMoteur(unittest.TestCase):
    def test_cartes_connectees_et_carte_du_profil(self):
        eng = Engine(config.load("config/avions/bae146-jf"))
        spec = CardSpec("x", "IOCP", None, 0)             # port 0 : libre, choisi par le système
        try:
            eng._serve_iocp("arduino_carburant", spec)
            port = next(iter(eng.servers.values()))._listener.getsockname()[1]
            wanted = sorted(eng._card_variables("arduino_carburant"))[:2]
            cards = [FakeCard(port, wanted), FakeCard(port, [9999])]
            end = time.monotonic() + 2
            while time.monotonic() < end:
                devices, ports = eng.network_devices()
                if len(devices) == 2 and all(d.variables for d in devices):
                    break
                time.sleep(0.02)
            by_vars = {d.variables: d for d in devices}
            self.assertEqual(by_vars[tuple(wanted)].cards, ("arduino_carburant",))
            self.assertEqual(by_vars[(9999,)].cards, ())                 # non déclarée
            self.assertEqual(by_vars[(9999,)].name, "carte IOCP non déclarée")
            self.assertEqual(len(ports), 1)
            for c in cards:
                c.sock.close()
        finally:
            eng.close()


if __name__ == "__main__":
    unittest.main()
