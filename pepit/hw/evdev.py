"""Joysticks et manettes du commerce (Thrustmaster…) lus par l'interface evdev de Linux.

Ces périphériques sont des HID standard : le noyau les décode et expose leurs axes et
boutons dans /dev/input/eventN, lisible par l'utilisateur de la session (ACL posée par
systemd-logind), sans règle udev. Le nœud evdev est retrouvé à partir du nœud hidraw
de la carte, par sysfs. Lecture seule : rien n'est jamais écrit au périphérique.

Relevé le 2026-11-24 sur le Thrustmaster TCA Q-Eng 1&2 : 7 axes de 0 à 65535 ; manette
gauche = axe 0, manette droite = axe 1 ; 0 = plein gaz (tout en avant), 65535 = fond de
la reverse ; le cran de reverse vers 47 000 ; un bouton par cran Airbus de chaque manette.
"""

import fcntl
import glob
import os
import select
import struct

EV_KEY, EV_ABS = 0x01, 0x03
_EVENT = struct.Struct("llHHi")        # struct input_event (64 bits)
_ABSINFO = struct.Struct("6i")         # valeur, min, max, fuzz, flat, résolution


KEY_MAX = 0x2ff
_KEYBYTES = (KEY_MAX + 8) // 8         # 96 octets : un bit par code de touche ou bouton


def _eviocgabs(axis):
    return (2 << 30) | (_ABSINFO.size << 16) | (ord("E") << 8) | (0x40 + axis)


def _eviocgkey(size=_KEYBYTES):
    return (2 << 30) | (size << 16) | (ord("E") << 8) | 0x18


def parse_caps(text):
    """« 7fff 0 … ffff00000000 0 0 » (sysfs, mot de poids fort d'abord) → codes présents."""
    codes = []
    for k, word in enumerate(reversed(text.split())):
        value = int(word, 16)
        codes += [64 * k + b for b in range(64) if value >> b & 1]
    return codes


def pressed(bitmap, codes):
    """Bitmap EVIOCGKEY (octets) → {code: 0/1} pour les codes demandés."""
    return {c: bitmap[c // 8] >> (c % 8) & 1 for c in codes}


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def event_node(hidraw_path):
    """/dev/hidrawN → /dev/input/eventM du même périphérique, ou None."""
    name = os.path.basename(hidraw_path)
    found = sorted(glob.glob(f"/sys/class/hidraw/{name}/device/input/input*/event*"))
    return "/dev/input/" + os.path.basename(found[0]) if found else None


def normalize(value, lo, hi):
    """Valeur brute → 0..1 sur la plage de l'axe."""
    return 0.0 if hi == lo else min(1.0, max(0.0, (value - lo) / (hi - lo)))


def parse_events(data):
    """Octets lus → [(type, code, valeur)]."""
    out = []
    for k in range(0, len(data) - _EVENT.size + 1, _EVENT.size):
        _sec, _usec, typ, code, value = _EVENT.unpack_from(data, k)
        out.append((typ, code, value))
    return out


class EvdevDevice:
    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        self.ranges = {}                       # axe → (min, max)
        self.initial = {}                      # axe → valeur brute à l'ouverture
        caps = f"/sys/class/input/{os.path.basename(path)}/device/capabilities/"
        for axis in parse_caps(_read(caps + "abs")):
            if axis < 64:
                value, lo, hi, *_ = _ABSINFO.unpack(fcntl.ioctl(self.fd, _eviocgabs(axis),
                                                                bytes(_ABSINFO.size)))
                self.ranges[axis] = (lo, hi)
                self.initial[axis] = value
        # boutons (crans, interrupteurs…) : n° d'entrée = rang dans l'ordre des codes
        self.keys = [c for c in parse_caps(_read(caps + "key")) if c <= KEY_MAX]
        self.initial_keys = (pressed(fcntl.ioctl(self.fd, _eviocgkey(), bytes(_KEYBYTES)),
                                     self.keys) if self.keys else {})

    def axis_value(self, axis, raw):
        lo, hi = self.ranges.get(axis, (0, 65535))
        return normalize(raw, lo, hi)

    def read(self, timeout=0.05):
        """Événements disponibles : [(type, code, valeur brute)] ; [] après `timeout`."""
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return []
        try:
            return parse_events(os.read(self.fd, _EVENT.size * 64))
        except BlockingIOError:
            return []

    def close(self):
        os.close(self.fd)
