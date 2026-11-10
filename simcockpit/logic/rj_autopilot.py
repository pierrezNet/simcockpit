"""Logique simulée du pilote automatique de l'Avro RJ sur le MCP OpenCockpits (737).

Correspondance reprise des anciens scripts de l'utilisateur (rj85.lua, MCP.txt) :
  HDG SEL → HDG, VOR LOC → NAV, LNAV, VNAV, LVL CHG, APP, ALT HLD → ALT, V/S → VS,
  N1 et SPEED → THRUST (gestion de poussée), CMD A / CMD B → NAV1 / NAV2,
  voyants CWS A / CWS B → F/D gauche / droit, A/T ARM → AT.

Règles validées par l'utilisateur le 2026-11-10 (en attendant X-Plane, qui décidera
lui-même de l'état des modes) :
- modes latéraux exclusifs : HDG, NAV, LNAV ; modes verticaux exclusifs : ALT, VS,
  LVL CHG, VNAV ;
- APP engage le latéral et le vertical (localizer + glide) et remplace les modes en
  cours ; un mode latéral ou vertical choisi ensuite annule APP ;
- un nouvel appui sur un mode engagé le désengage ;
- NAV1 / NAV2 : un seul à la fois (nouvel appui = aucun) ;
- CWS A / CWS B s'allument selon les interrupteurs F/D gauche / droit, A/T ARM selon
  son interrupteur ;
- barre DISENGAGE baissée : tous les modes, THRUST et NAV1/NAV2 s'éteignent, et les
  boutons restent sans effet tant qu'elle est baissée.

Les poussoirs du MCP valent 1 au repos et 0 pendant l'appui (vérifié).
"""

from .controls import Control

LATERAL = {"HDG SEL": "HDG", "VOR LOC": "NAV", "LNAV": "LNAV"}
VERTICAL = {"ALT HLD": "ALT", "V/S": "VS", "LVL CHG": "LVL CHG", "VNAV": "VNAV"}
THRUST_BUTTONS = ("N1", "SPEED")
NAV_SOURCE = {"CMD A": "NAV1", "CMD B": "NAV2"}
# boutons sans fonction dans cette logique (leurs voyants suivent les F/D) ;
# un appui alors que le F/D correspondant est sur OFF donne une alerte
UNUSED = ("CWS A", "CWS B")
CWS_FD = {"CWS A": ("fd_left", "F/D gauche"), "CWS B": ("fd_right", "F/D droit")}
# voyant du MCP → mode RJ qui l'allume
LED_OF_MODE = {"HDG": "HDG SEL", "NAV": "VOR LOC", "LNAV": "LNAV", "ALT": "ALT HLD",
               "VS": "V/S", "LVL CHG": "LVL CHG", "VNAV": "VNAV", "APP": "APP"}
LOCKOUT = 0.15     # s : un rebond dans ce délai n'est pas un nouvel appui


class RjAutopilot(Control):
    type = "rj_autopilot"

    def __init__(self, name, buttons, fd_left=None, fd_right=None, at_arm=None,
                 disengage=None, button_level=0, **kw):
        known = set(LATERAL) | set(VERTICAL) | set(THRUST_BUTTONS) | set(NAV_SOURCE) | set(UNUSED) | {"APP"}
        unknown = set(buttons) - known
        if unknown:
            raise ValueError(f"{name} : boutons inconnus {sorted(unknown)} (connus : {sorted(known)})")
        self.buttons = dict(buttons)
        self.switches = {k: v for k, v in (("fd_left", fd_left), ("fd_right", fd_right),
                                           ("at_arm", at_arm), ("disengage", disengage))
                         if v is not None}
        super().__init__(name, list(self.buttons.values()) + list(self.switches.values()), **kw)
        self.button_level = button_level
        # état de l'automatisme
        self.lateral = None
        self.vertical = None
        self.thrust = False
        self.nav_source = None
        self.fd = {"fd_left": False, "fd_right": False}
        self.at_armed = False
        self.disengaged = False
        # boutons
        self._down = {}
        self._last_press = {}
        self._first = True
        self.alert = None          # dernier message d'alerte, lu (et effacé) par le panneau
        self._changed = True
        self.value = self.summary()

    # ------------------------------------------------------------ entrées
    def update(self, active, t):
        if self._first:                          # état initial : pas d'appui
            self._first = False
            for b, i in self.buttons.items():
                self._down[b] = active[i] == self.button_level
            self._read_switches(active)
            return
        for b, i in self.buttons.items():
            down = active[i] == self.button_level
            if down and not self._down[b] and t - self._last_press.get(b, -1e9) >= LOCKOUT:
                self._last_press[b] = t
                self.press(b)
            self._down[b] = down
        self._read_switches(active)

    def _read_switches(self, active):
        for key in ("fd_left", "fd_right"):
            if key in self.switches:
                self._set("fd", bool(active[self.switches[key]]), key)
        if "at_arm" in self.switches:
            self._set_attr("at_armed", bool(active[self.switches["at_arm"]]))
        if "disengage" in self.switches:
            down = not active[self.switches["disengage"]]     # 0 = barre baissée (vérifié)
            if down and not self.disengaged:
                self.lateral = self.vertical = self.nav_source = None
                self.thrust = False
            self._set_attr("disengaged", down)

    def _set(self, attr, value, key):
        if getattr(self, attr)[key] != value:
            getattr(self, attr)[key] = value
            self._changed = True

    def _set_attr(self, attr, value):
        if getattr(self, attr) != value:
            setattr(self, attr, value)
            self._changed = True

    def press(self, button):
        """Appui sur un bouton du MCP (matériel ou bouton virtuel du panneau).

        Retourne un message d'alerte, ou None."""
        if button in CWS_FD:
            key, label = CWS_FD[button]
            if not self.fd[key]:
                self.alert = f"{button} : sans effet, {label} sur OFF"
                self._changed = True
                return self.alert
            return None
        if self.disengaged:
            self.alert = f"{button} : sans effet, barre DISENGAGE baissée"
            self._changed = True
            return self.alert
        if button == "APP":
            if self.lateral == "APP":
                self.lateral = self.vertical = None
            else:
                self.lateral = self.vertical = "APP"
        elif button in LATERAL:
            mode = LATERAL[button]
            if self.lateral == "APP":
                self.vertical = None
            self.lateral = None if self.lateral == mode else mode
        elif button in VERTICAL:
            mode = VERTICAL[button]
            if self.vertical == "APP":
                self.lateral = None
            self.vertical = None if self.vertical == mode else mode
        elif button in THRUST_BUTTONS:
            self.thrust = not self.thrust
        elif button in NAV_SOURCE:
            src = NAV_SOURCE[button]
            self.nav_source = None if self.nav_source == src else src
        else:
            return
        self._changed = True

    # ------------------------------------------------------------ sorties
    def led_states(self):
        """Voyant du MCP → allumé ?"""
        on = {LED_OF_MODE[m] for m in (self.lateral, self.vertical) if m}
        if self.thrust:
            on.add("N1")
        if self.nav_source == "NAV1":
            on.add("CMD A")
        elif self.nav_source == "NAV2":
            on.add("CMD B")
        if self.fd["fd_left"]:
            on.add("CWS A")
        if self.fd["fd_right"]:
            on.add("CWS B")
        if self.at_armed:
            on.add("A/T ARM")
        names = ("APP", "ALT HLD", "V/S", "CMD A", "CWS A", "CMD B", "CWS B", "A/T ARM", "N1",
                 "SPEED", "VNAV", "LVL CHG", "HDG SEL", "LNAV", "VOR LOC")
        return {n: n in on for n in names}

    def poll(self, t):
        if self._changed:
            self._changed = False
            self.value = self.summary()
            return self.value
        return None

    def summary(self):
        if self.disengaged:
            return "DÉSENGAGÉ"
        parts = [f"lat {self.lateral or '-'}", f"vert {self.vertical or '-'}"]
        if self.thrust:
            parts.append("THRUST")
        if self.nav_source:
            parts.append(self.nav_source)
        fd = [s for s, k in (("G", "fd_left"), ("D", "fd_right")) if self.fd[k]]
        if fd:
            parts.append("F/D " + "+".join(fd))
        if self.at_armed:
            parts.append("AT")
        return " · ".join(parts)

    def describe(self):
        return (f"pilote automatique RJ : {len(self.buttons)} boutons, "
                f"interrupteurs {', '.join(f'{k} {v}' for k, v in self.switches.items())}")
