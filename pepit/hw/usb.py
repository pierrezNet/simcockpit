"""Périphériques USB : ce qui est branché, où, et si Pepit peut s'en servir.

Lecture de /sys/bus/usb/devices, sans dépendance ni droit particulier. Pour chaque
périphérique : identifiants, fabricant, produit, numéro de série, port, vitesse, courant
demandé, et les nœuds qu'il expose dans /dev (hidraw, série, evdev) avec leur accès.

L'historique (`History`) retient chaque périphérique déjà vu : première et dernière
fois, ports successifs, nombre de branchements, état d'accès.
"""

import os
import re
import time
from dataclasses import dataclass, field

import yaml

from .cards import UNKNOWN, classify, maker

SYSFS = "/sys/bus/usb/devices"
DEV = "/dev"
_DEVICE = re.compile(r"^\d+-[\d.]+$")              # « 1-4.4 » : un périphérique (pas « 1-4:1.0 »)
_NODE = re.compile(r"^(hidraw\d+|event\d+|ttyUSB\d+|ttyACM\d+)$")
SPEEDS = {"1.5": "1,5 Mbit/s (low)", "12": "12 Mbit/s (full)", "480": "480 Mbit/s (high)",
          "5000": "5 Gbit/s", "10000": "10 Gbit/s", "20000": "20 Gbit/s"}
CLASSES = {"09": "concentrateur USB", "0e": "caméra", "01": "audio", "08": "stockage",
           "e0": "sans fil", "ef": ""}


@dataclass(frozen=True)
class Node:
    path: str          # /dev/hidraw3, /dev/input/event21, /dev/ttyUSB0
    kind: str          # « hidraw », « evdev », « serie »
    access: bool       # lisible et inscriptible par ce compte

    @property
    def name(self):
        return os.path.basename(self.path)


@dataclass(frozen=True)
class UsbDevice:
    port: str          # « 1-4.4 »
    vid: str           # « 0000 » (4 chiffres hexadécimaux)
    pid: str
    manufacturer: str
    product: str
    serial: str
    speed: str         # tel que sysfs l'écrit : « 12 » (Mbit/s)
    max_power: int     # mA demandés au port
    device_class: str  # « 09 » = concentrateur
    nodes: tuple = ()

    @property
    def vid_pid(self):
        return f"{self.vid}:{self.pid}"

    @property
    def key(self):
        """Identité dans l'historique : numéro de série s'il existe, sinon le port
        (les cartes de cockpit n'ont pas de numéro de série)."""
        return f"{self.vid_pid}:{self.serial}" if self.serial else f"{self.vid_pid}@{self.port}"

    @property
    def name(self):
        parts = [self.manufacturer, self.product]
        return " ".join(p for p in parts if p) or self.vid_pid

    @property
    def card_type(self):
        return classify(self.product)

    @property
    def cockpit(self):
        """Carte de cockpit : modèle connu de Pepit ou fabricant de cockpit."""
        return self.card_type is not UNKNOWN or maker(self.manufacturer) is not None

    @property
    def pepit(self):
        """Ce que Pepit en fait (texte court), ou « » s'il ne le connaît pas."""
        if self.card_type is not UNKNOWN:
            return self.card_type.label
        if maker(self.manufacturer):
            return f"{maker(self.manufacturer)} (non pris en charge)"
        return CLASSES.get(self.device_class, "")

    @property
    def is_hub(self):
        return self.device_class == "09"

    @property
    def speed_label(self):
        return SPEEDS.get(self.speed, f"{self.speed} Mbit/s" if self.speed else "")

    @property
    def useful_nodes(self):
        """Les nœuds dont Pepit se sert : evdev pour un joystick, hidraw pour une carte
        connue ; tous pour un périphérique qu'il ne connaît pas."""
        t = self.card_type
        if t is UNKNOWN:
            return self.nodes
        want = "evdev" if t.protocol == "evdev" else "hidraw"
        return tuple(n for n in self.nodes if n.kind == want)

    @property
    def access(self):
        """« ok » (tous les nœuds utiles ouverts), « partiel », « refusé », ou « » sans nœud."""
        nodes = self.useful_nodes
        if not nodes:
            return ""
        ok = sum(n.access for n in nodes)
        return "ok" if ok == len(nodes) else "partiel" if ok else "refusé"


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def _dev_path(name, dev):
    return os.path.join(dev, "input", name) if name.startswith("event") else os.path.join(dev, name)


def _nodes(devdir, dev):
    """Nœuds /dev exposés par ce périphérique (pas par ceux branchés derrière lui)."""
    found = {}
    for here, dirs, _files in os.walk(devdir):     # les liens (driver, subsystem…) sont ignorés
        dirs[:] = [d for d in dirs if not _DEVICE.match(d)]   # périphérique enfant : à part
        for d in dirs:
            if _NODE.match(d) and d not in found:
                kind = ("hidraw" if d.startswith("hidraw") else
                        "evdev" if d.startswith("event") else "serie")
                path = _dev_path(d, dev)
                mode = os.R_OK if kind == "evdev" else os.R_OK | os.W_OK
                found[d] = Node(path, kind, os.access(path, mode))
    return tuple(sorted(found.values(), key=lambda n: (n.kind, n.path)))


def _power(text):
    m = re.match(r"(\d+)", text)
    return int(m.group(1)) if m else 0


def scan(sysfs=SYSFS, dev=DEV):
    """Périphériques USB branchés (concentrateurs compris, sauf ceux du contrôleur)."""
    out = []
    try:
        names = sorted(os.listdir(sysfs))
    except OSError:
        return out
    for name in names:
        if not _DEVICE.match(name):
            continue
        d = os.path.join(sysfs, name)
        out.append(UsbDevice(
            port=name, vid=_read(os.path.join(d, "idVendor")) or "????",
            pid=_read(os.path.join(d, "idProduct")) or "????",
            manufacturer=_read(os.path.join(d, "manufacturer")),
            product=_read(os.path.join(d, "product")),
            serial=_read(os.path.join(d, "serial")),
            speed=_read(os.path.join(d, "speed")),
            max_power=_power(_read(os.path.join(d, "bMaxPower"))),
            device_class=_read(os.path.join(d, "bDeviceClass")),
            nodes=_nodes(os.path.realpath(d), dev)))
    return out


# ---------------------------------------------------------------- historique
def state_dir():
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "pepit")


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class Seen:
    """Un périphérique de l'historique."""
    name: str
    vid_pid: str
    serial: str = ""
    pepit: str = ""
    cockpit: bool = False
    first: str = ""
    last: str = ""                       # dernière fois branché (ou débranché, s'il ne l'est plus)
    ports: list = field(default_factory=list)
    plugs: int = 0                       # branchements vus
    plugged: bool = False
    access: str = ""                     # au dernier passage : « ok », « refusé », « »

    def to_yaml(self):
        return {"nom": self.name, "vid_pid": self.vid_pid, "serie": self.serial,
                "pepit": self.pepit, "cockpit": self.cockpit, "premiere_fois": self.first,
                "derniere_fois": self.last, "ports": list(self.ports),
                "branchements": self.plugs, "branche": self.plugged, "acces": self.access}

    @classmethod
    def from_yaml(cls, d):
        return cls(name=str(d.get("nom", "")), vid_pid=str(d.get("vid_pid", "")),
                   serial=str(d.get("serie", "") or ""), pepit=str(d.get("pepit", "") or ""),
                   cockpit=bool(d.get("cockpit", False)), first=str(d.get("premiere_fois", "")),
                   last=str(d.get("derniere_fois", "")),
                   ports=[str(p) for p in d.get("ports") or []],
                   plugs=int(d.get("branchements", 0) or 0),
                   plugged=bool(d.get("branche", False)), access=str(d.get("acces", "") or ""))


class History:
    """Historique des périphériques, dans ~/.local/state/pepit/peripheriques.yaml."""

    def __init__(self, path=None, clock=_now):
        self.path = path or os.path.join(state_dir(), "peripheriques.yaml")
        self.clock = clock
        self.seen = {}                   # clé -> Seen
        self._started = False
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            data = {}
        self.seen = {str(k): Seen.from_yaml(v) for k, v in data.items() if isinstance(v, dict)}

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("# Pepit : périphériques USB déjà vus (écrit par la page Périphériques)\n")
            yaml.safe_dump({k: s.to_yaml() for k, s in sorted(self.seen.items())}, f,
                           allow_unicode=True, sort_keys=False)
        os.replace(tmp, self.path)

    def update(self, devices):
        """Prend en compte un relevé. Retourne les changements, pour le journal :
        [(« branché » | « débranché » | « accès », Seen, UsbDevice ou None)]."""
        now, changes = self.clock(), []
        first_pass = not self._started      # au lancement : rien n'est « branché à l'instant »
        self._started = True
        present = {d.key: d for d in devices}
        for key, d in present.items():
            s = self.seen.get(key)
            if s is None:
                s = self.seen[key] = Seen(name=d.name, vid_pid=d.vid_pid, serial=d.serial,
                                          first=now)
            s.name, s.pepit, s.cockpit = d.name, d.pepit, d.cockpit
            if d.port not in s.ports:
                s.ports.append(d.port)
            if not s.plugged:
                s.plugged, s.last = True, now
                s.plugs += 1
                if not first_pass:
                    changes.append(("branché", s, d))
            if d.access != s.access:
                if s.access and not first_pass:
                    changes.append(("accès", s, d))
                s.access = d.access
        for key, s in self.seen.items():
            if s.plugged and key not in present:
                if first_pass:                   # débranché pendant que Pepit était arrêté :
                    s.plugged = False            # on ne sait pas quand
                    continue
                s.plugged, s.last = False, now
                changes.append(("débranché", s, None))
        if changes or first_pass:
            try:
                self.save()
            except OSError:
                pass                         # l'historique ne doit jamais bloquer la page
        return changes
