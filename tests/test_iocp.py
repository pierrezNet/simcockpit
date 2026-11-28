"""Serveur IOCP (protocole réseau de SIOC) : messages, et une fausse carte ESP8266."""

import socket
import time
import unittest

from pepit.hw import iocp
from pepit.logic import config
from pepit.logic.engine import Engine


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


class TestLivret(unittest.TestCase):
    """Carte des vitesses du BAe 146 : une page par masse, page de la masse supérieure."""

    def lookup(self, **kw):
        from pepit.logic.iocp_lookup import IocpLookup
        return IocpLookup("livret", source="sim/m", variables={"page": 210, "vr": 211, "v2": 212},
                          pages={36000: {"vr": 120, "v2": 128}, 38000: {"vr": 125}}, **kw)

    def test_page_superieure_et_case_absente(self):
        l = self.lookup()
        l.on_sim("sim/m", 37808.1, 1.0)
        self.assertEqual(l.take_values(), {210: 38000, 211: 125, 212: 0})   # V2 absente : 0
        l.on_sim("sim/m", 37900, 2.0)                    # même page : rien à envoyer
        self.assertEqual(l.take_values(), {})
        l.on_sim("sim/m", 35000, 3.0)
        self.assertEqual(l.take_values(), {210: 36000, 211: 120, 212: 128})
        l.on_sim("sim/m", 45000, 4.0)                    # au-delà du livret : dernière page
        self.assertEqual(l.page, 38000)

    def test_page_la_plus_proche(self):
        l = self.lookup(choix="proche")
        l.on_sim("sim/m", 36500, 1.0)
        self.assertEqual(l.page, 36000)

    def test_profil_bae146(self):
        eng = Engine(config.load("config/avions/bae146-jf"))
        carte = eng.cockpit.instruments["carte_vitesses"].controls["livret"]
        self.assertEqual(carte.source, "sim/flightmodel/weight/m_total")
        eng.sim_step({"sim/flightmodel/weight/m_total": 37808.1}, True, 1.0)
        values = carte.take_values()
        self.assertEqual((values[210], values[211], values[212], values[223]), (38000, 128, 134, 183))


class TestPortPartage(unittest.TestCase):
    def test_deux_cartes_un_serveur(self):
        from pepit.logic.config import CardSpec
        eng = Engine(config.load("config/avions/bae146-jf"))
        spec = CardSpec("x", "IOCP", None, 0)            # port 0 : libre, choisi par le système
        try:
            eng._serve_iocp("arduino_carburant", spec)
            eng._serve_iocp("ecran_vitesses", spec)
            self.assertEqual(len(eng.servers), 1)
            self.assertEqual(set(eng._iocp_port), {"arduino_carburant", "ecran_vitesses"})
            self.assertIn("en attente", eng.status["ecran_vitesses"])
        finally:
            eng.close()
