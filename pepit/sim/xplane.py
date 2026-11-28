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
PER_SOCKET = 400        # X-Plane ne sert que les 500 premiers abonnements d'un client
                        # (vérifié le 2026-11-14) : au-delà, on ouvre un autre port local
STALE_AFTER = 2.0       # s sans réponse → X-Plane considéré absent
RESUBSCRIBE_EVERY = 2.0  # s entre deux tentatives d'abonnement quand X-Plane est absent
RETRY_BATCH = 200       # abonnements sans réponse renvoyés par tentative : X-Plane perd une
                        # partie d'une rafale de plus de 1000 demandes (vérifié le 2026-11-14)


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
        self.socks = [self._open()]     # un port local par tranche de PER_SOCKET abonnements
        self.sock = self.socks[0]       # commandes et écritures
        self.names = []                 # index global → nom du dataref
        self.values = {}                # nom → dernière valeur reçue
        self.last_rx = None
        self._last_subscribe = -1e9

    # ------------------------------------------------------------ état
    @property
    def connected(self):
        return self.last_rx is not None and time.monotonic() - self.last_rx < STALE_AFTER

    @staticmethod
    def _open():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", 0))
        sock.setblocking(False)
        return sock

    def _sock_for(self, index):
        return self.socks[index // PER_SOCKET]

    def subscribe(self, name):
        if name not in self.names:
            self.names.append(name)
            index = len(self.names) - 1
            if index // PER_SOCKET >= len(self.socks):
                self.socks.append(self._open())
            self._send(rref_packet(RREF_FREQ, index % PER_SOCKET, name), self._sock_for(index))

    def _resubscribe(self):
        for i, name in enumerate(self.names):
            self._send(rref_packet(RREF_FREQ, i % PER_SOCKET, name), self._sock_for(i))
        self._last_subscribe = time.monotonic()

    # ------------------------------------------------------------ échanges
    def poll(self):
        """Lit les réponses en attente. Retourne {nom: valeur} des datarefs qui ont changé."""
        changed = {}
        for k, sock in enumerate(self.socks):
            while True:
                try:
                    data, _ = sock.recvfrom(65536)
                except (BlockingIOError, InterruptedError):
                    break
                except OSError:          # port fermé (X-Plane absent) : on réessaiera
                    break
                self.last_rx = time.monotonic()
                for index, value in parse_rref(data):
                    index += k * PER_SOCKET
                    if 0 <= index < len(self.names):
                        name = self.names[index]
                        if self.values.get(name) != value:
                            self.values[name] = value
                            changed[name] = value
        now = time.monotonic()
        if not self.connected and now - self._last_subscribe > RESUBSCRIBE_EVERY:
            self._resubscribe()
        elif self.connected and now - self._last_subscribe > RESUBSCRIBE_EVERY:
            self._retry_missing()
        return changed

    def _retry_missing(self):
        """Renvoie, par petits paquets, les abonnements qui n'ont encore reçu aucune valeur."""
        missing = [i for i, name in enumerate(self.names) if name not in self.values]
        for i in missing[:RETRY_BATCH]:
            self._send(rref_packet(RREF_FREQ, i % PER_SOCKET, self.names[i]), self._sock_for(i))
        self._last_subscribe = time.monotonic()

    def write(self, name, value):
        self._send(dref_packet(name, value))

    def command(self, name):
        self._send(cmnd_packet(name))

    def _send(self, packet, sock=None):
        try:
            (sock or self.sock).sendto(packet, self.addr)
        except OSError:
            pass                     # X-Plane absent : rien à faire

    def close(self):
        for i, name in enumerate(self.names):
            self._send(rref_packet(0, i % PER_SOCKET, name), self._sock_for(i))  # fréquence 0
        for sock in self.socks:
            sock.close()
