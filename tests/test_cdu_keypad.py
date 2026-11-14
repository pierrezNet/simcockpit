"""CDU relié au FMS d'X-Plane (config/avions/b738-laminar/cdu.yaml)."""

import unittest

from simcockpit.hw import usbfmc
from simcockpit.logic import config
from simcockpit.logic.engine import Engine
from simcockpit.logic.sim_controls import Keypad

EXEC_LIGHT = "sim/cockpit2/radios/indicators/fms_exec_light_pilot"
CODE = {name: code for code, name in usbfmc.KEYS.items()}


class TestCduKeypad(unittest.TestCase):
    def setUp(self):
        self.eng = Engine(config.load("config/avions/b738-laminar"))
        self.eng.sim_step({}, True, 0.0)

    def test_keys_send_fms_commands(self):
        for name, cmd in (("EXEC", "sim/FMS/exec"), ("LSK1L", "sim/FMS/ls_1l"), ("A", "sim/FMS/key_A"),
                          ("1", "sim/FMS/key_1"), ("INIT REF", "sim/FMS/index"), ("CLR", "sim/FMS/key_clear")):
            self.eng.key("cdu", CODE[name], 1.0)
            self.assertIn(("cmd", cmd), self.eng.sim_step({}, True, 1.0), name)

    def test_exec_light_follows_xplane(self):
        self.eng.sim_step({EXEC_LIGHT: 1.0}, True, 1.0)
        self.eng.poll(1.0)
        self.assertEqual(self.eng._pending["cdu"]["leds"][0], 1 << usbfmc.LEDS["EXEC"])
        self.eng.sim_step({EXEC_LIGHT: 0.0}, True, 2.0)
        self.eng.poll(2.0)
        self.assertEqual(self.eng._pending["cdu"]["leds"][0], 0)

    def test_no_command_without_xplane(self):
        eng = Engine(config.load("config/avions/b738-laminar"))
        eng.key("cdu", CODE["EXEC"], 1.0)
        self.assertEqual(eng.sim_step({}, False, 1.0), [])

    def test_unknown_key_name_rejected(self):
        with self.assertRaises(ValueError):
            Keypad("k", {"EXECUTE": "sim/FMS/exec"})

    def test_keypad_needs_a_cdu(self):
        with self.assertRaisesRegex(config.ConfigError, "clavier"):
            config.parse({"cards": {"mcp": {"product": "IOCard-MCP"}},
                          "instruments": {"x": {"card": "mcp", "controls": {
                              "k": {"type": "keypad", "keys": {"EXEC": "sim/FMS/exec"}}}}}})


if __name__ == "__main__":
    unittest.main()
