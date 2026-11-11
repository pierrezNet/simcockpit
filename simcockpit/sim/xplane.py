"""Liaison avec X-Plane par son protocole UDP natif (port 49000), sans plugin.

- RREF : abonnement à un dataref ; X-Plane renvoie sa valeur `freq` fois par seconde,
  sous forme de paires (index, valeur flottante) ;
- DREF : écriture d'un dataref (valeur flottante) ;
- CMND : déclenchement d'une commande (appui bref).

Vérifié le 2026-11-11 avec X-Plane 12 Linux : réponse RREF reçue sur le port local.
La liaison n'a pas d'état côté X-Plane : si le simulateur redémarre, on se réabonne.
"""

import socket
import struct
import time

RREF_FREQ = 20          # valeurs par seconde
STALE_AFTER = 2.0       # s sans réponse → X-Plane considéré absent
RESUBSCRIBE_EVERY = 2.0  # s entre deux tentatives d'abonnement quand X-Plane est absent


def rref_packet(freq, index, name) -> bytes:
    return b"RREF\x00" + struct.pack("<ii400s", freq, index, name.encode())


def dref_packet(name, value) -> bytes:
    return b"DREF\x00" + struct.pack("<f500s", float(value), name.encode())


def cmnd_packet(name) -> bytes:
    return b"CMND\x00" + name.encode() + b"\x00"


def parse_rref(data: bytes):
    """Paquet reçu → [(index, valeur)] ; [] si ce n'est pas une réponse RREF."""
    if not data.startswith(b"RREF"):
        return []
    body = data[5:]
    return [struct.unpack("<if", body[k:k + 8]) for k in range(0, len(body) - 7, 8)]


class XPlane:
    def __init__(self, host="127.0.0.1", port=49000):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", 0))
        self.sock.setblocking(False)
        self.names = []                 # index → nom du dataref
        self.values = {}                # nom → dernière valeur reçue
        self.last_rx = None
        self._last_subscribe = -1e9

    # ------------------------------------------------------------ état
    @property
    def connected(self):
        return self.last_rx is not None and time.monotonic() - self.last_rx < STALE_AFTER

    def subscribe(self, name):
        if name not in self.names:
            self.names.append(name)
            self._send(rref_packet(RREF_FREQ, len(self.names) - 1, name))

    def _resubscribe(self):
        for i, name in enumerate(self.names):
            self._send(rref_packet(RREF_FREQ, i, name))
        self._last_subscribe = time.monotonic()

    # ------------------------------------------------------------ échanges
    def poll(self):
        """Lit les réponses en attente. Retourne {nom: valeur} des datarefs qui ont changé."""
        changed = {}
        while True:
            try:
                data, _ = self.sock.recvfrom(8192)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:          # port fermé (X-Plane absent) : on réessaiera
                break
            self.last_rx = time.monotonic()
            for index, value in parse_rref(data):
                if 0 <= index < len(self.names):
                    name = self.names[index]
                    if self.values.get(name) != value:
                        self.values[name] = value
                        changed[name] = value
        if not self.connected and time.monotonic() - self._last_subscribe > RESUBSCRIBE_EVERY:
            self._resubscribe()
        return changed

    def write(self, name, value):
        self._send(dref_packet(name, value))

    def command(self, name):
        self._send(cmnd_packet(name))

    def _send(self, packet):
        try:
            self.sock.sendto(packet, self.addr)
        except OSError:
            pass                     # X-Plane absent : rien à faire

    def close(self):
        for i, name in enumerate(self.names):
            self._send(rref_packet(0, i, name))     # fréquence 0 = désabonnement
        self.sock.close()
