"""Bus des jauges EFDE (FDBUS) : carte USB « FDBUS » et modules RS485 derrière elle.

Trames de 8 octets, octet 0 = fonction. Structure tirée de la note d'EFDE et de
l'étude des échanges du driver d'EFDE ; séquence vérifiée sur le matériel le 2026-11-17
(moteur X27 de l'IVSI et carte analogique 12 V des volets, à la webcam).

Initialisation, obligatoire avant toute commande de position :

  1. `00 00 00 …`  : la carte explore les adresses 195 à 254. Réponses : `03 adr` = adresse
     vide (progression), `01 adr type` = module trouvé, `ff` = fin de l'exploration.
  2. pour chaque module n° i : `07 adr 00` puis `ff adr i`. Le module renvoie ses
     paramètres, un par trame `[fonction 150..187, i, valeur]`, jusqu'à 187 (0xbb).
  3. `fe 00 00` : la carte répond `fe`, l'initialisation est terminée.

En fonctionnement :

  `03 adr pos` / `04 adr pos` : position de la sortie 1 / 2 (0 à 255, bornée par Mini/Maxi
  du module). La première après l'initialisation a été ignorée deux fois sur deux : on
  l'envoie en double. `07 adr 00` ramène le moteur X27 en butée (zéro moteur).
  `06 32 v` : rétroéclairage, adresse 0x32 = tous les modules (non vérifié).

Les fonctions 50 à 88 écrivent l'EEPROM des modules (adresse, calibrage) : `frame()`
refuse de les produire. Seule exception, accordée par l'utilisateur le 2026-11-17 :
`address_frame()`, la fonction 50 (changement d'adresse) `32 adr nouvelle`, envoyée depuis le
banc de test après confirmation, strap de configuration en place. C'est la dernière trame
du bouton « Écrit EEPROM » du driver d'EFDE (qui écrit aussi tous les paramètres avant) ;
le driver d'EFDE se relance ensuite pour relire le bus.

Au repos, la carte répète sa dernière trame environ 250 fois par seconde : seules les
trames différentes de la précédente comptent.
"""

from dataclasses import dataclass, field
from pathlib import Path

EXPLORE, OUT1, OUT2, SERVO1, SERVO2, AD_READ, BACKLIGHT, RESET = 0, 1, 2, 3, 4, 5, 6, 7
END_INIT, READ_PARAMS = 0xFE, 0xFF
ALL_MODULES = 0x32
EEPROM_WRITE = range(50, 89)

# Réponses de la carte
FOUND, EMPTY, END_EXPLORE = 0x01, 0x03, 0xFF

FIRST_ADDRESS, LAST_ADDRESS = 195, 254

# Paramètres renvoyés par un module : fonction → nom (note d'EFDE, « #FReeprom… »).
PARAMS = {
    150: "Mini1", 151: "Maxi1", 152: "Mini2", 153: "Maxi2",
    154: "Offset1H", 155: "Offset1L", 156: "Offset2H", 157: "Offset2L",
    158: "FSMini1H", 159: "FSMini1L", 160: "FSMaxi1H", 161: "FSMaxi1L",
    162: "FSMini2H", 163: "FSMini2L", 164: "FSMaxi2H", 165: "FSMaxi2L",
    166: "Loffset1", 167: "Loffset2", 168: "Inv1", 169: "Inv2", 170: "Type2",
    171: "OffsetOut1H", 172: "OffsetOut1L", 173: "OffsetOut2H", 174: "OffsetOut2L",
    175: "LoffsetOut1", 176: "LoffsetOut2", 177: "TypeOut1", 178: "TypeOut2",
    179: "OffsetAN1H", 180: "OffsetAN1L", 181: "LoffsetAN1", 182: "TypeAN1",
    183: "ParamAN1H", 184: "ParamAN1L", 185: "Type1", 186: "InversionOut1", 187: "InversionOut2",
}
LAST_PARAM = 187

# Types de module observés (type de la sortie 1, annoncé à l'exploration).
MODULE_TYPES = {2: "moteur pas à pas X27", 49: "analogique 12 V (Booster)"}

# Offsets FSUIPC rencontrés dans les paramètres des modules (réglage d'usine d'EFDE,
# indicatif : la jauge réellement branchée se règle dans config/fdbus.yaml).
FSUIPC_OFFSETS = {0x02C8: ("vitesse verticale", "ft/min"), 0x0BE0: ("volets", "°")}


def frame(function, address=0, value=0) -> bytes:
    """Trame de commande ; les écritures EEPROM (50 à 88) sont refusées."""
    if function in EEPROM_WRITE:
        raise PermissionError(f"fonction {function} : écriture EEPROM interdite")
    return bytes([function, address & 0xFF, value & 0xFF]) + bytes(5)


def address_frame(module, new_address) -> bytes:
    """Fonction 50 : écrit une nouvelle adresse dans l'EEPROM du module (strap de
    configuration en place). Seule écriture EEPROM permise."""
    if not FIRST_ADDRESS <= new_address <= LAST_ADDRESS:
        raise ValueError(f"adresse {new_address} : {FIRST_ADDRESS} à {LAST_ADDRESS}")
    if new_address == module.address:
        raise ValueError(f"le module est déjà à l'adresse {new_address}")
    return bytes([50, module.address, new_address]) + bytes(5)


def _signed16(value):
    return value - 0x10000 if value & 0x8000 else value


@dataclass
class Module:
    address: int
    type: int
    index: int
    params: dict = field(default_factory=dict)   # nom → octet

    def word(self, name):
        """Paramètre sur deux octets (H puis L), ou None s'il n'a pas été reçu."""
        hi, lo = self.params.get(name + "H"), self.params.get(name + "L")
        return None if hi is None or lo is None else hi << 8 | lo

    def limits(self, channel=1):
        """Bornes de position (Mini, Maxi) de la sortie ; 0-255 si non reçues."""
        lo, hi = self.params.get(f"Mini{channel}", 0), self.params.get(f"Maxi{channel}", 255)
        return (lo, hi) if lo <= hi else (hi, lo)

    def fs_range(self, channel=1):
        """Plage de la donnée simulateur (FSMini, FSMaxi), signée, ou None."""
        lo, hi = self.word(f"FSMini{channel}"), self.word(f"FSMaxi{channel}")
        if lo is None or hi is None or lo == hi:
            return None
        return _signed16(lo), _signed16(hi)

    def to_sim(self, position, channel=1):
        """Position → valeur simulateur équivalente (interpolation linéaire), ou None."""
        rng = self.fs_range(channel)
        if rng is None:
            return None
        lo, hi = self.limits(channel)
        if hi == lo:
            return rng[0]
        return rng[0] + (position - lo) * (rng[1] - rng[0]) / (hi - lo)

    def rest_position(self, channel=1):
        """Position de repos envoyée après l'initialisation : celle de la valeur simulateur 0
        si l'échelle du module la contient (IVSI : 0 ft/min), sinon Mini (volets rentrés)."""
        lo, hi = self.limits(channel)
        rng = self.fs_range(channel)
        if rng is None or not min(rng) <= 0 <= max(rng):
            return lo
        return round(lo + (0 - rng[0]) * (hi - lo) / (rng[1] - rng[0]))

    @property
    def type_label(self):
        if self.type == 0:   # vu sans 5 V sur le bus (2026-11-17), le module ne répond plus ensuite
            return "type 0 : module sans 5 V, ou deux modules sur la même adresse ?"
        return MODULE_TYPES.get(self.type, f"type {self.type} (inconnu)")

    @property
    def data_label(self):
        offset = self.word("Offset1")
        if offset is None:
            return ""
        name = FSUIPC_OFFSETS.get(offset, ("", ""))[0]
        return f"offset {offset:04X}" + (f" ({name})" if name else "")

    def params_text(self):
        shown = []
        for name in ("Mini1", "Maxi1", "Mini2", "Maxi2", "Inv1", "Inv2", "Type1", "Type2",
                     "TypeOut1", "TypeOut2", "TypeAN1"):
            if name in self.params:
                shown.append(f"{name} {self.params[name]}")
        for name in ("Offset1", "Offset2", "OffsetOut1", "OffsetOut2", "OffsetAN1"):
            w = self.word(name)
            if w:
                shown.append(f"{name} {w:04X}")
        rng = self.fs_range(1)
        if rng:
            shown.append(f"FS1 {rng[0]}…{rng[1]}")
        return ", ".join(shown)


class BusInit:
    """Automate d'initialisation : `start()` puis `feed(trame reçue)` ; chaque appel rend
    les trames à écrire. `state` : explore → params → ending → ready (ou empty)."""

    def __init__(self):
        self.state = "idle"
        self.modules = []
        self.progress = None     # dernière adresse explorée
        self._last = None
        self._current = 0

    def start(self):
        self.state, self.modules, self.progress, self._last = "explore", [], None, None
        return [bytes(8)]

    def _ask(self, i):
        m = self.modules[i]
        return [frame(RESET, m.address, 0), frame(READ_PARAMS, m.address, i)]

    def feed(self, pkt):
        if not pkt or pkt == self._last:     # la carte répète sa dernière trame
            return []
        self._last = pkt
        fn = pkt[0]
        if self.state == "explore":
            if fn == FOUND and len(pkt) >= 3:
                self.modules.append(Module(pkt[1], pkt[2], len(self.modules)))
            elif fn == EMPTY and len(pkt) >= 2:
                self.progress = pkt[1]
            elif fn == END_EXPLORE:
                if not self.modules:
                    self.state = "empty"
                    return []
                self.state, self._current = "params", 0
                return self._ask(0)
        elif self.state == "params":
            if fn in PARAMS and len(pkt) >= 3 and pkt[1] == self._current:
                self.modules[self._current].params[PARAMS[fn]] = pkt[2]
                if fn == LAST_PARAM:
                    self._current += 1
                    if self._current < len(self.modules):
                        return self._ask(self._current)
                    self.state = "ending"
                    return [frame(END_INIT)]
        elif self.state == "ending" and fn == END_INIT:
            self.state = "ready"
        return []

    def duplicates(self):
        """Adresses annoncées plusieurs fois (deux modules sur la même adresse ?)."""
        seen = [m.address for m in self.modules]
        return sorted({a for a in seen if seen.count(a) > 1})


class FdbusOutputs:
    """Positions envoyées ; rend les trames à écrire, seulement si la position change."""

    def __init__(self):
        self.sent = {}   # (adresse, sortie) → position

    def position(self, module: Module, value, channel=1):
        lo, hi = module.limits(channel)
        value = max(lo, min(hi, int(round(value))))
        key = (module.address, channel)
        if self.sent.get(key) == value:
            return []
        first = key not in self.sent
        self.sent[key] = value
        f = frame(SERVO1 if channel == 1 else SERVO2, module.address, value)
        return [f, f] if first else [f]    # la première commande après l'init est ignorée

    def reset(self, module: Module):
        """Zéro moteur ; la position suivante sera envoyée (en double) quoi qu'il arrive."""
        for key in [k for k in self.sent if k[0] == module.address]:
            del self.sent[key]
        return [frame(RESET, module.address, 0)]

    @staticmethod
    def backlight(level):
        """Rétroéclairage de tous les modules, niveau 0 à 15 (non vérifié)."""
        if not 0 <= level <= 15:
            raise ValueError("rétroéclairage : 0 à 15")
        return [frame(BACKLIGHT, ALL_MODULES, level * 17)]


class Calibration:
    """Une sortie de module vue comme une jauge : nom, unité et étalonnage du cadran
    (valeurs lues sur le cadran → positions du moteur 0-255).

    Rien n'est figé dans le code : un autre cockpit peut brancher une autre jauge sur la
    même sortie ; tout est réglé dans le banc de test et gardé dans config/fdbus.yaml (et
    jamais dans l'EEPROM du module). Interpolation linéaire entre points, bornée aux points
    extrêmes ; il faut au moins deux points.
    """

    def __init__(self, points=None, module_type=None, name="", unit=""):
        self.module_type = module_type   # type du module étalonné (évite de mélanger deux
        self.name, self.unit = name, unit  # modules passés par la même adresse)
        self.points = {}
        for value, position in (points or {}).items():
            self.add(value, position)

    def add(self, value, position):
        value = float(value)
        self.points[int(value) if value.is_integer() else value] = int(position)

    def remove(self, value):
        self.points.pop(value, None)

    def __len__(self):
        return len(self.points)

    def empty(self):
        return not self.points and not self.name and not self.unit

    @staticmethod
    def _interp(x, pairs):
        pairs = sorted(pairs)
        if x <= pairs[0][0]:
            return pairs[0][1]
        for (x0, y0), (x1, y1) in zip(pairs, pairs[1:]):
            if x <= x1:
                return y0 if x1 == x0 else y0 + (x - x0) * (y1 - y0) / (x1 - x0)
        return pairs[-1][1]

    def position(self, value):
        """Valeur du cadran → position du moteur, ou None sans étalonnage."""
        if len(self.points) < 2:
            return None
        return round(self._interp(value, self.points.items()))

    def value(self, position):
        """Position du moteur → valeur du cadran (affichage), ou None sans étalonnage."""
        if len(self.points) < 2:
            return None
        return self._interp(position, [(p, v) for v, p in self.points.items()])

    def incoherent(self):
        """Repères qui cassent le sens de la courbe (position qui recule alors que la
        valeur du cadran avance) : le plus souvent un curseur mal placé à l'enregistrement."""
        pts = sorted(self.points.items())
        if len(pts) < 3:
            return []
        sens = 1 if pts[-1][1] >= pts[0][1] else -1
        return [v for (_, p0), (v, p) in zip(pts, pts[1:]) if (p - p0) * sens <= 0]


CALIBRATION_FILE = Path(__file__).resolve().parents[2] / "config" / "fdbus.yaml"
_HEADER = """\
# Jauges du bus FDBUS (EFDE), écrit par le banc de test (onglet FDBUS).
# Par adresse de module : type du module, puis pour chaque sortie la jauge qui y est
# branchée (nom, unité) et l'étalonnage de son cadran : « valeur lue: position du moteur
# (0-255) ». Un module d'un autre type à la même adresse n'utilise pas ces réglages.
# Ces réglages restent sur le PC : ils ne sont jamais écrits dans les modules.
"""


def load_calibrations(path=CALIBRATION_FILE):
    """{(adresse, sortie): Calibration} ; vide si le fichier n'existe pas."""
    import yaml
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    out = {}
    for address, outputs in (data.get("modules") or {}).items():
        outputs = outputs or {}
        for key, spec in outputs.items():
            if not (key.startswith("sortie") and key[6:].isdigit()):
                continue
            spec = spec or {}
            if "points" not in spec and all(not isinstance(v, dict) for v in spec.values()):
                spec = {"points": spec}      # ancien format : les points directement
            out[(int(address), int(key[6:]))] = Calibration(
                spec.get("points"), outputs.get("type"),
                str(spec.get("nom") or ""), str(spec.get("unite") or ""))
    return out


def save_calibrations(calibrations, path=CALIBRATION_FILE):
    import yaml
    modules = {}
    for (address, channel), cal in sorted(calibrations.items()):
        if cal.empty():
            continue
        entry = modules.setdefault(address, {})
        if cal.module_type is not None:
            entry.setdefault("type", cal.module_type)
        spec = {}
        if cal.name:
            spec["nom"] = cal.name
        if cal.unit:
            spec["unite"] = cal.unit
        spec["points"] = dict(sorted(cal.points.items()))
        entry[f"sortie{channel}"] = spec
    with open(path, "w", encoding="utf-8") as f:
        f.write(_HEADER)
        yaml.safe_dump({"modules": modules}, f, sort_keys=False, allow_unicode=True)
