"""Serveur IOCP (protocole réseau de SIOC) : messages, et une fausse carte ESP8266."""

import socket
import time
import unittest

from simcockpit.hw import iocp
from simcockpit.logic import config
from simcockpit.logic.engine import Engine


class TestMessages(unittest.TestCase):
    def test_lecture(self):
        self.assertEqual(iocp.parse_line("Arn.Inicio:201:202:203:\r"), ("Inicio", [201, 202, 203]))
        self.assertEqual(iocp.parse_line("Arn.Resp:12=1:13=-4:"), ("Resp", {12: 1, 13: -4}))
        self.assertEqual(iocp.parse_line("Arn.Vivo:"), ("Vivo", None))
        self.assertIsNone(iocp.parse_line("bonjour"))

    def test_ecriture_lue_par_le_programme_esp8266(self):
        # le programme coupe sur « : » et « = » et attend la fin de ligne « \n »
        self.assertEqual(iocp.resp_line({203: 998.4, 201: 3961}), "Arn.Resp:201=3961:203=998:\n")


class FakeCard:
    """Se comporte comme l'afficheur carburant : connexion, annonce, lecture de lignes."""

    def __init__(self, port, variables):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=2)
        self.sock.sendall(("Arn.Inicio:" + "".join(f"{v}:" for v in variables) + "\r\n").encode())
        self.buf = b""

    def lines(self, wait=1.0):
        end, out = time.monotonic() + wait, []
        self.sock.settimeout(0.05)
        while time.monotonic() < end:
            try:
                data = self.sock.recv(4096)
            except socket.timeout:
                continue
            if not data:
                break
            self.buf += data
            while b"\n" in self.buf:
                line, self.buf = self.buf.split(b"\n", 1)
                out.append(line.decode())
        return out


class TestServeur(unittest.TestCase):
    def test_carte_recoit_ses_variables_puis_les_changements(self):
        server = iocp.IocpServer(port=0, host="127.0.0.1").start()
        port = server._listener.getsockname()[1]
        try:
            server.set_values({201: 3961, 202: 4129, 203: 998, 999: 1})
            card = FakeCard(port, [201, 202, 203])
            self.assertEqual(card.lines(0.5), ["Arn.Resp:201=3961:202=4129:203=998:"])
            server.set_values({202: 4100, 999: 2})                 # 999 : pas demandée
            self.assertEqual(card.lines(0.5), ["Arn.Resp:202=4100:"])
            self.assertEqual(server.clients, ["127.0.0.1"])
            card.sock.sendall(b"Arn.Resp:5=1:\n")                  # entrée venant de la carte
            time.sleep(0.2)
            self.assertEqual(server.poll_inputs(), {5: 1})
            card.sock.close()
            time.sleep(0.2)
            self.assertEqual(server.clients, [])
        finally:
            server.stop()


class TestProfil(unittest.TestCase):
    def test_bae146_reservoirs_vers_variables_201_202_203(self):
        eng = Engine(config.load("config/avions/bae146-jf"))
        aff = eng.cockpit.instruments["carburant"].controls["afficheur"]
        eng.sim_step({"sim/flightmodel/weight/m_fuel[0]": 3961.4,
                      "sim/flightmodel/weight/m_fuel[2]": 998.0}, True, 1.0)
        self.assertEqual(aff.take_values(), {201: 3961, 203: 998})
        self.assertEqual(aff.take_values(), {})
        self.assertIn("201 = 3961", aff.summary())


if __name__ == "__main__":
    unittest.main()
