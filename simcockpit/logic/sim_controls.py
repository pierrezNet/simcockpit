"""Commandes reliées directement au simulateur (X-Plane).

- `commands` : chaque poussoir déclenche une commande X-Plane à l'appui ;
- `sim_leds` : chaque voyant (du MCP) suit un dataref (allumé si la valeur est non nulle).

C'est l'avion simulé qui décide de l'état des modes : simcockpit transmet les appuis
et recopie les voyants, comme un vrai MCP relié à ses calculateurs.
"""

from .controls import Control

LOCKOUT = 0.15     # s : un rebond dans ce délai n'est pas un nouvel appui


class Commands(Control):
    type = "commands"

    def __init__(self, name, inputs, level=1, **kw):
        self.commands = {int(i): c for i, c in dict(inputs).items()}   # entrée → commande
        super().__init__(name, list(self.commands), **kw)
        self.level = level                      # valeur de l'entrée pendant l'appui
        self._down = None
        self._last = {}
        self._pressed = None

    def update(self, active, t):
        down = {i: active[i] == self.level for i in self.commands}
        if self._down is not None:              # premier état : aucun appui
            for i, d in down.items():
                if d and not self._down[i] and t - self._last.get(i, -1e9) >= LOCKOUT:
                    self._last[i] = t
                    self.press(i)
        self._down = down

    def press(self, index):
        """Appui sur le poussoir de l'entrée `index` (matériel ou bouton virtuel)."""
        cmd = self.commands[index]
        if self.sim_connected:
            self._sim("cmd", cmd)
        self._pressed = cmd

    def poll(self, t):
        if self._pressed is None:
            return None
        cmd, self._pressed = self._pressed, None
        return cmd.rsplit("/", 1)[-1] + ("" if self.sim_connected else " (X-Plane absent)")

    def describe(self):
        return f"{len(self.commands)} poussoirs → commandes X-Plane"


class SimLeds(Control):
    type = "sim_leds"

    def __init__(self, name, leds, **kw):
        self.leds = dict(leds)                  # voyant → dataref
        super().__init__(name, [], **kw)
        self.values = {}
        self._changed = False

    def update(self, active, t):
        pass

    def sim_datarefs(self):
        return list(dict.fromkeys(self.leds.values()))

    def on_sim(self, name, value, t):
        if self.values.get(name) != value:
            self.values[name] = value
            self._changed = True

    def led_states(self):
        return {led: bool(self.values.get(ref, 0)) for led, ref in self.leds.items()}

    def poll(self, t):
        if not self._changed:
            return None
        self._changed = False
        lit = [led for led, on in self.led_states().items() if on]
        return ", ".join(lit) or "aucun"

    def describe(self):
        return f"{len(self.leds)} voyants ← datarefs X-Plane"


class Keypad(Control):
    """Clavier (CDU) : chaque touche, désignée par son nom, déclenche une commande X-Plane.

    Les touches arrivent comme des événements « key » (une trame par appui, rien au
    relâchement) ; les noms sont ceux de simcockpit/hw/usbfmc.py (EXEC, LSK1L, A, 1…).
    """
    type = "keypad"

    def __init__(self, name, keys, **kw):
        from ..hw import usbfmc
        known = set(usbfmc.KEYS.values())
        unknown = sorted(set(map(str, keys)) - known)
        if unknown:
            raise ValueError(f"{name} : touches inconnues {unknown}")
        self.keys = {str(k): c for k, c in dict(keys).items()}
        self._code_to_name = usbfmc.KEYS
        super().__init__(name, [], **kw)
        self._pressed = None

    def update(self, active, t):
        pass

    def on_key(self, code, t):
        self.press(self._code_to_name.get(code))

    def press(self, key):
        """Appui sur une touche (matériel ou panneau virtuel)."""
        cmd = self.keys.get(key)
        if cmd is None:
            return
        if self.sim_connected:
            self._sim("cmd", cmd)
        self._pressed = key

    def poll(self, t):
        if self._pressed is None:
            return None
        key, self._pressed = self._pressed, None
        return key + ("" if self.sim_connected else " (X-Plane absent)")

    def describe(self):
        return f"{len(self.keys)} touches → commandes X-Plane"
