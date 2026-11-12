"""Boîtier radio (radio OpenCockpits de type Airbus) relié aux radios d'un avion X-Plane.

- un bouton de source choisit la radio réglée (COM1, NAV1, ADF1…) et allume son voyant ;
- la grande bague envoie les commandes « coarse » de la fréquence en attente, la petite
  bague les commandes « fine » (un changement d'état du code Gray = un cran) ;
- le bouton de transfert envoie la commande d'échange active / attente ;
- les afficheurs ACTIVE et STANDBY montrent les fréquences lues dans X-Plane, mises à
  l'échelle (`scale`) avec `decimals` décimales : COM en kHz → 118.000, NAV en 10 kHz → 109.50 ;
- l'interrupteur ON/OFF éteint afficheurs et voyants.

Tout est décrit dans le YAML : les noms de datarefs et de commandes viennent de
X-Plane 12/Resources/plugins (DataRefs.txt, Commands.txt).
"""

from .controls import _GRAY, Control

LOCKOUT = 0.15      # s : un rebond dans ce délai n'est pas un nouvel appui


class Source:
    def __init__(self, name, inputs, leds=(), active=None, standby=None, scale=1.0, decimals=0,
                 flip=None, coarse=(None, None), fine=(None, None)):
        self.name = name
        self.inputs = [inputs] if isinstance(inputs, int) else list(inputs)
        self.leds = [leds] if isinstance(leds, str) else list(leds)
        self.active, self.standby = active, standby
        self.scale, self.decimals = float(scale), int(decimals)
        self.flip = flip
        self.coarse = tuple(coarse)       # (commande « baisser », commande « monter »)
        self.fine = tuple(fine)

    def text(self, value):
        if value is None:
            return "---"
        return f"{value * self.scale:.{self.decimals}f}"


class RadioPanel(Control):
    type = "radio_panel"

    def __init__(self, name, sources, outer, inner, transfer, power=None, power_on=1,
                 button_level=0, **kw):
        self.sources = [Source(n, **dict(spec)) for n, spec in dict(sources).items()]
        if not self.sources:
            raise ValueError(f"{name} : au moins une source (sources)")
        self.outer, self.inner = list(outer), list(inner)
        self.transfer, self.power = transfer, power
        indexes = self.outer + self.inner + [transfer] + ([power] if power is not None else [])
        for s in self.sources:
            indexes += s.inputs
        super().__init__(name, indexes, **kw)
        self.power_on_level, self.button_level = power_on, button_level
        self.selected = self.sources[0]
        self.powered = True
        self.values = {}                       # dataref → valeur reçue d'X-Plane
        self._down = None
        self._last_press = {}
        self._gray = {}
        self._changed = True
        self.value = self.summary()

    # ------------------------------------------------------------ entrées
    def update(self, active, t):
        if self.power is not None:
            on = active[self.power] == self.power_on_level
            if on != self.powered:
                self.powered, self._changed = on, True
        buttons = {i: active[i] == self.button_level for s in self.sources for i in s.inputs}
        buttons[self.transfer] = active[self.transfer] == self.button_level
        if self._down is not None:
            for i, down in buttons.items():
                if down and not self._down[i] and t - self._last_press.get(i, -1e9) >= LOCKOUT:
                    self._last_press[i] = t
                    self._press(i)
        self._down = buttons
        for ring, pair in (("coarse", self.outer), ("fine", self.inner)):
            state = _GRAY[(active[pair[0]], active[pair[1]])]
            old = self._gray.get(ring)
            if old is not None and state != old:
                d = (state - old) % 4
                if d in (1, 3):
                    self.turn(ring, 1 if d == 1 else -1)
            self._gray[ring] = state

    def _press(self, index):
        if index == self.transfer:
            self.swap()
            return
        for s in self.sources:
            if index in s.inputs:
                self.select(s.name)
                return

    # actions (matériel ou panneau virtuel)
    def select(self, name):
        if self.powered:
            self.selected = next(s for s in self.sources if s.name == name)
            self._changed = True

    def swap(self):
        if self.powered and self.selected.flip and self.sim_connected:
            self._sim("cmd", self.selected.flip)

    def turn(self, ring, clicks):
        if not (self.powered and self.sim_connected):
            return
        down, up = getattr(self.selected, ring)
        cmd = up if clicks > 0 else down
        if cmd:
            for _ in range(abs(clicks)):
                self._sim("cmd", cmd)

    # ------------------------------------------------------------ simulateur
    def sim_datarefs(self):
        refs = []
        for s in self.sources:
            refs += [r for r in (s.active, s.standby) if r]
        return list(dict.fromkeys(refs))

    def on_sim(self, name, value, t):
        if self.values.get(name) != value:
            self.values[name] = value
            if name in (self.selected.active, self.selected.standby):
                self._changed = True

    # ------------------------------------------------------------ sorties
    def radio_display(self):
        """{"ACTIVE": texte, "STANDBY": texte} et {voyant: allumé}."""
        if not self.powered:
            return {"ACTIVE": "", "STANDBY": ""}, {}
        s = self.selected
        texts = {"ACTIVE": s.text(self.values.get(s.active)),
                 "STANDBY": s.text(self.values.get(s.standby))}
        return texts, {led: True for led in s.leds}

    def poll(self, t):
        if self._changed:
            self._changed = False
            self.value = self.summary()
            return self.value
        return None

    def summary(self):
        if not self.powered:
            return "éteinte"
        texts, _ = self.radio_display()
        return f"{self.selected.name} {texts['ACTIVE']} ↔ {texts['STANDBY']}"

    def describe(self):
        return f"radio : {', '.join(s.name for s in self.sources)} ; transfert entrée {self.transfer}"
