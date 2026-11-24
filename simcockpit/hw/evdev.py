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


def _eviocgabs(axis):
    return (2 << 30) | (_ABSINFO.size << 16) | (ord("E") << 8) | (0x40 + axis)


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
        caps = open(f"/sys/class/input/{os.path.basename(path)}/device/capabilities/abs").read()
        mask = int(caps.split()[-1], 16)       # mot de poids faible : axes 0 à 63
        for axis in range(64):
            if mask >> axis & 1:
                value, lo, hi, *_ = _ABSINFO.unpack(fcntl.ioctl(self.fd, _eviocgabs(axis),
                                                                bytes(_ABSINFO.size)))
                self.ranges[axis] = (lo, hi)
                self.initial[axis] = value

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
