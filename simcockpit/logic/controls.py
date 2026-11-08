"""Types de commandes : transforment un groupe d'entrées en une valeur métier.

Chaque commande lit un groupe d'entrées « actives » (0/1, polarité de la carte déjà
appliquée) avec un anti-rebond de GROUPE : pas de valeur intermédiaire fausse quand
plusieurs bits basculent à quelques ms d'écart.
"""

from ..hw.debounce import GroupDebouncer
from .atmosphere import cas_to_mach, mach_to_cas


class Control:
    type = "?"

    def __init__(self, name, indexes, delay=0.05, display=None, led=None, leading_zeros=False):
        self.name = name
        self.leading_zeros = leading_zeros   # afficher « 045 » plutôt que « 45 » (cap, route)
        self.indexes = list(indexes)
        self._deb = GroupDebouncer(self.indexes, delay)
        self.value = None
        self.display = display    # afficheur de sortie (ex. « HDG » sur le MCP)
        self.led = led            # voyant de sortie (ex. « A/T ARM »)

    def update(self, active, t):
        """`active` : liste complète des entrées (1 = actionnée). Retourne la nouvelle valeur ou None."""
        self._deb.update(active, t)

    def poll(self, t):
        bits = self._deb.poll(t)
        if bits is None:
            return None
        new = self.decode(dict(zip(self.indexes, bits)))
        if new != self.value:
            self.value = new
            return new
        return None

    def decode(self, bits):
        raise NotImplementedError

    def display_value(self, value):
        """Ce qu'il faut afficher pour `value` : (valeur ou texte, point décimal allumé ?)."""
        return value, False

    def describe(self):
        return f"{self.type} sur {self.indexes}"


class OctalDigits(Control):
    """Chiffres codés en binaire sur 3 entrées chacun (bit 0 en premier) : ex. code transpondeur."""
    type = "octal_digits"

    def __init__(self, name, inputs, **kw):
        self.groups = [list(g) for g in inputs]
        for g in self.groups:
            if len(g) != 3:
                raise ValueError(f"{name} : chaque chiffre doit avoir 3 entrées, reçu {g}")
        super().__init__(name, [i for g in self.groups for i in g], **kw)

    def decode(self, bits):
        return "".join(str(bits[a] | bits[b] << 1 | bits[c] << 2) for a, b, c in self.groups)


class Selector(Control):
    """Sélecteur à positions : la 1re position active de la liste l'emporte, sinon `default`."""
    type = "selector"

    def __init__(self, name, positions, default="OFF", **kw):
        self.positions = dict(positions)   # libellé -> entrée, dans l'ordre de priorité
        self.default = default
        super().__init__(name, self.positions.values(), **kw)

    def decode(self, bits):
        for label, index in self.positions.items():
            if bits[index]:
                return label
        return self.default

    def describe(self):
        return f"sélecteur {self.positions}, sinon {self.default}"


class Switch(Control):
    """Interrupteur ou poussoir sur une entrée : True quand actionné."""
    type = "switch"

    def __init__(self, name, input, **kw):
        super().__init__(name, [input], **kw)

    def decode(self, bits):
        return bool(bits[self.indexes[0]])


# Ordre du code Gray d'un encodeur (a = 1re entrée, b = 2e) : 00 → 01 → 11 → 10.
_GRAY = {(0, 0): 0, (1, 0): 1, (1, 1): 2, (0, 1): 3}
# Accélération par défaut : (intervalle max entre deux crans en s, multiplicateur)
DEFAULT_ACCEL = ((0.06, 10), (0.15, 3))


class Encoder(Control):
    """Encodeur rotatif (2 entrées en code Gray) qui fait varier une valeur.

    Un changement d'état = un cran (vérifié sur le MCP). `wrap` : boucle (cap 359 → 0) ;
    sinon la valeur est bornée. `invert` : inverse le sens. `accel` : multiplie le pas
    quand les crans s'enchaînent vite (liste [[intervalle_s, multiplicateur], ...]).
    Pas d'anti-rebond : chaque cran compte, sinon une rotation rapide serait perdue.
    """
    type = "encoder"

    def __init__(self, name, inputs, min=0, max=359, step=1, initial=None, wrap=False,
                 invert=False, accel=True, **kw):
        if len(inputs) != 2:
            raise ValueError(f"{name} : un encodeur a 2 entrées, reçu {inputs}")
        super().__init__(name, inputs, **kw)
        self.min, self.max, self.step = min, max, step
        self.wrap, self.sign = wrap, (-1 if invert else 1)
        self.accel = sorted(DEFAULT_ACCEL if accel is True else (accel or ()))
        if initial is None:                  # 0 si possible (V/S), sinon le minimum
            initial = 0 if min <= 0 <= max else min
        self.value = self._clamp(initial)
        self._state = None
        self._last_t = None
        self._changed = True          # publier la valeur initiale

    def _clamp(self, v):
        if self.wrap:
            span = self.max - self.min + self.step
            return self.min + (v - self.min) % span
        return max(self.min, min(self.max, v))

    def _multiplier(self, t):
        if self._last_t is None:
            return 1
        dt = t - self._last_t
        for limit, mult in self.accel:
            if dt <= limit:
                return mult
        return 1

    def turn(self, clicks, t):
        """Applique `clicks` crans (signés) à l'instant t."""
        mult = self._multiplier(t)
        self._last_t = t
        new = self._clamp(self.value + self.sign * clicks * self.step * mult)
        if new != self.value:
            self.value, self._changed = new, True

    def update(self, active, t):
        state = _GRAY[(active[self.indexes[0]], active[self.indexes[1]])]
        if self._state is not None and state != self._state:
            d = (state - self._state) % 4
            # d == 2 : un état sauté (rotation plus rapide qu'une trame) → 2 crans dans le dernier sens
            clicks = {1: 1, 3: -1}.get(d, 2 * getattr(self, "_last_dir", 1))
            self._last_dir = 1 if clicks > 0 else -1
            self.turn(clicks, t)
        self._state = state

    def poll(self, t):
        if self._changed:
            self._changed = False
            return self.value
        return None

    def describe(self):
        mode = "en boucle" if self.wrap else "borné"
        return f"encodeur {self.indexes}, {self.min}..{self.max} par {self.step}, {mode}"


class SpeedEncoder(Encoder):
    """Encodeur de vitesse avec bouton de bascule IAS / Mach (C/O).

    En IAS, la valeur est en nœuds ; en Mach, en centièmes (78 = Mach 0,78).
    Si `altitude_from` désigne l'encodeur d'altitude du même instrument, la bascule
    convertit la vitesse à cette altitude (ISA, QNH 1013, vent nul) au lieu de reprendre
    la dernière valeur de l'autre mode.
    """
    type = "speed_encoder"

    def __init__(self, name, inputs, toggle_input, toggle_level=1, ias=(100, 340, 1),
                 mach=(40, 89, 1), initial_ias=250, initial_mach=78, altitude_from=None,
                 **kw):
        super().__init__(name, inputs, min=ias[0], max=ias[1], step=ias[2], initial=initial_ias,
                         **kw)
        self.indexes.append(toggle_input)
        self._ranges = {"IAS": tuple(ias), "MACH": tuple(mach)}
        self._values = {"IAS": initial_ias, "MACH": initial_mach}
        self.mode = "IAS"
        self.altitude_from = altitude_from    # nom de l'encodeur d'altitude (relié par config)
        self.altitude_control = None
        self._toggle = toggle_input
        self._toggle_level = toggle_level     # valeur « actionnée » du bouton C/O (MCP : 0)
        self._was_pressed = None
        self._last_toggle_t = -1e9

    def update(self, active, t):
        super().update(active, t)
        pressed = active[self._toggle] == self._toggle_level
        if self._was_pressed is None:                  # état initial : pas de bascule
            self._was_pressed = pressed
            return
        # appui pris au premier front ; rebonds ignorés pendant 0,3 s
        if pressed and not self._was_pressed and t - self._last_toggle_t >= 0.3:
            self._last_toggle_t = t
            self._switch_mode()
        self._was_pressed = pressed

    def _switch_mode(self):
        self._values[self.mode] = self.value
        new_mode = "MACH" if self.mode == "IAS" else "IAS"
        lo, hi, _ = self._ranges[new_mode]
        if self.altitude_control is not None:
            back = getattr(self, "_converted", None)
            if back and back[1] == self.value and back[2] == self.altitude_control.value:
                # valeur non retouchée depuis la conversion : on retrouve la valeur exacte
                self._values[new_mode] = back[0]
            else:
                alt = self.altitude_control.value
                if new_mode == "MACH":
                    v = round(100 * cas_to_mach(self.value, alt))
                else:
                    v = round(mach_to_cas(self.value / 100, alt))
                self._values[new_mode] = max(lo, min(hi, v))
            self._converted = (self.value, self._values[new_mode], self.altitude_control.value)
        self.mode = new_mode
        self.min, self.max, self.step = self._ranges[new_mode]
        self.value, self._changed = self._values[new_mode], True

    def display_value(self, value):
        if self.mode == "MACH":                       # « .78 » : chiffre de gauche éteint + point
            return f"{value:02d}" if value < 100 else str(value), True
        return value, False

    def describe(self):
        return (f"vitesse {self.indexes[:2]} + bascule IAS/MACH sur {self._toggle} ; "
                f"IAS {self._ranges['IAS']}, Mach {self._ranges['MACH']} (centièmes)")


TYPES = {c.type: c for c in (OctalDigits, Selector, Switch, Encoder, SpeedEncoder)}


def make(name, spec):
    spec = dict(spec)
    kind = spec.pop("type", None)
    if kind not in TYPES:
        raise ValueError(f"{name} : type inconnu {kind!r} (connus : {', '.join(TYPES)})")
    return TYPES[kind](name, **spec)
