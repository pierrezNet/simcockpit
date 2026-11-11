"""Liaison X-Plane : protocole UDP (contre un faux X-Plane local) et logique du moteur."""

import socket
import struct
import time
import unittest

from simcockpit.logic import config
from simcockpit.logic.engine import Engine
from simcockpit.sim import xplane


class FakeXPlane:
    """Serveur UDP qui répond aux RREF et enregistre ce qu'il reçoit."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.5)
        self.port = self.sock.getsockname()[1]
        self.received = []

    def serve(self, values, rounds=1):
        subs = {}
        for _ in range(rounds):
            try:
                data, addr = self.sock.recvfrom(1024)
            except socket.timeout:
                break
            self.received.append(data)
            if data.startswith(b"RREF\x00"):
                freq, idx, name = struct.unpack("<ii400s", data[5:])
                subs[idx] = name.rstrip(b"\x00").decode()
                body = b"".join(struct.pack("<if", i, values.get(n, 0.0)) for i, n in subs.items())
                self.sock.sendto(b"RREF," + body, addr)


class TestProtocol(unittest.TestCase):
    def test_packets(self):
        self.assertEqual(len(xplane.rref_packet(20, 3, "sim/x")), 5 + 408)
        self.assertEqual(len(xplane.dref_packet("sim/x", 1.5)), 5 + 504)
        self.assertEqual(xplane.cmnd_packet("sim/autopilot/heading"),
                         b"CMND\x00sim/autopilot/heading\x00")
        reply = b"RREF," + struct.pack("<if", 0, 152.5) + struct.pack("<if", 1, 0.0)
        self.assertEqual(xplane.parse_rref(reply), [(0, 152.5), (1, 0.0)])

    def test_round_trip_with_fake_xplane(self):
        fake = FakeXPlane()
        xp = xplane.XPlane("127.0.0.1", fake.port)
        xp.subscribe("sim/cockpit2/autopilot/heading_dial_deg_mag_pilot")
        fake.serve({"sim/cockpit2/autopilot/heading_dial_deg_mag_pilot": 152.5})
        time.sleep(0.05)
        changed = xp.poll()
        self.assertEqual(changed, {"sim/cockpit2/autopilot/heading_dial_deg_mag_pilot": 152.5})
        self.assertTrue(xp.connected)
        xp.command("laminar/B738/autopilot/hdg_sel_press")
        fake.serve({})
        self.assertEqual(fake.received[-1], b"CMND\x00laminar/B738/autopilot/hdg_sel_press\x00")
        xp.close()
        fake.sock.close()


def mcp_rest():
    s = [0] * 72
    for i in list(range(16, 30)) + [12, 14]:
        s[i] = 1                                 # poussoirs et barre DISENGAGE au repos
    return s


class TestEngineWithSim(unittest.TestCase):
    def setUp(self):
        self.eng = Engine(config.load("config/avions/b738-laminar"))
        self.state = mcp_rest()
        self.eng.feed("mcp", self.state, 0.0, active_level=1)
        self.eng.poll(0.1)

    def connect(self, values=None, t=1.0):
        actions = self.eng.sim_step(values or {}, True, t)
        self.eng.poll(t)
        return actions + self.eng.sim_step({}, True, t)

    def test_switch_positions_pushed_on_connect(self):
        self.state[15] = 1                         # F/D gauche sur ON
        self.eng.feed("mcp", self.state, 0.2, active_level=1)
        self.eng.poll(0.3)
        actions = self.connect()
        self.assertIn(("cmd", "sim/autopilot/fdir_command_bars_on"), actions)
        self.assertIn(("cmd", "sim/autopilot/fdir2_command_bars_off"), actions)
        self.assertIn(("cmd", "sim/autopilot/autothrottle_hard_off"), actions)

    def test_button_sends_command(self):
        self.connect()
        self.state[25] = 0                         # HDG SEL appuyé
        self.eng.feed("mcp", self.state, 2.0, active_level=1)
        actions = self.eng.sim_step({}, True, 2.0)
        self.assertIn(("cmd", "laminar/B738/autopilot/hdg_sel_press"), actions)

    def test_leds_follow_datarefs(self):
        self.connect({"laminar/B738/autopilot/hdg_sel_status": 1.0,
                      "laminar/B738/autopilot/app_status": 2.0})
        self.assertEqual(self.eng.outputs["mcp"].leds, (1 << 13) | (1 << 0))   # HDG SEL et APP

    def test_heading_follows_and_writes(self):
        self.connect({"sim/cockpit2/autopilot/heading_dial_deg_mag_pilot": 152.48})
        cap = self.eng.cockpit.instruments["mcp"].controls["cap"]
        self.assertEqual(cap.value, 152)
        cap.turn(1, 3.0)                           # un cran
        actions = self.eng.sim_step({"sim/cockpit2/autopilot/heading_dial_deg_mag_pilot": 152.48},
                                    True, 3.1)
        self.assertIn(("dref", "sim/cockpit2/autopilot/heading_dial_deg_mag_pilot", 153), actions)
        self.assertEqual(cap.value, 153)           # l'ancienne valeur d'X-Plane est ignorée

    def test_disengage_bar_toggles_until_in_sync(self):
        self.connect({"laminar/B738/autopilot/disconnect_pos": 0.0})
        self.state[14] = 0                         # barre baissée
        self.eng.feed("mcp", self.state, 2.0, active_level=1)
        self.eng.poll(2.1)
        actions = self.eng.sim_step({}, True, 2.1)
        self.assertIn(("cmd", "laminar/B738/autopilot/disconnect_toggle"), actions)
        actions = self.eng.sim_step({"laminar/B738/autopilot/disconnect_pos": 1.0}, True, 3.0)
        self.assertNotIn(("cmd", "laminar/B738/autopilot/disconnect_toggle"), actions)

    def test_display_options(self):
        from simcockpit.hw import mcp
        from simcockpit.logic.controls import Encoder
        alt = Encoder("alt", [2, 3], min=0, max=41000, step=100, display="ALT", min_digits=3)
        vs = Encoder("vs", [10, 11], min=-7900, max=6000, step=100, display="VS",
                     blank_unless="laminar/B738/autopilot/vs_status")
        self.assertEqual(alt.shown(0), ("000", False))          # min_digits: 3
        self.assertEqual(alt.shown(10000), ("10000", False))
        self.assertEqual(vs.shown(-500), (-500, False))         # X-Plane absent : affiché
        vs.sim_connected = True
        vs.on_sim("laminar/B738/autopilot/vs_status", 0.0, 1.0)
        self.assertEqual(vs.shown(-500), (None, False))         # mode V/S désengagé : éteint
        vs.on_sim("laminar/B738/autopilot/vs_status", 1.0, 2.0)
        self.assertEqual(vs.shown(-500), (-500, False))
        self.assertIsNotNone(vs.poll(2.0))                      # réaffiché au changement
        # bout à bout : l'altitude 0 de la config 737 s'affiche « 000 » sur le MCP
        self.connect({"sim/cockpit2/autopilot/altitude_dial_ft": 0.0})
        p0, p1 = self.eng.outputs["mcp"].display_frames()
        # ALT de gauche à droite = page 0 n10 n9, page 1 n2 n1 n0 (demi-octet k : octet k//2)
        digits = [p0[5] & 0x0F, p0[4] >> 4, p1[1] & 0x0F, p1[0] >> 4, p1[0] & 0x0F]
        B = mcp.DIGIT_BLANK
        self.assertEqual(digits, [B, B, 0, 0, 0])

    def test_blank_when(self):
        from simcockpit.logic.controls import Encoder
        e = Encoder("vs", [10, 11], min=-1000, max=1000, step=100, display="VS", blank_when=0)
        self.assertEqual(e.shown(0), (None, False))
        self.assertEqual(e.shown(100), (100, False))

    def test_mach_mode_from_sim(self):
        self.connect({"sim/cockpit2/autopilot/airspeed_dial_kts_mach": 0.78,
                      "sim/cockpit2/autopilot/airspeed_is_mach": 1.0})
        v = self.eng.cockpit.instruments["mcp"].controls["vitesse"]
        self.assertEqual((v.mode, v.value), ("MACH", 78))


if __name__ == "__main__":
    unittest.main()
