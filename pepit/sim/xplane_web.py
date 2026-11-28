"""Lecture de datarefs par l'API web locale d'X-Plane 12 (port 8086), en complément de l'UDP.

Le protocole UDP (RREF) ne renvoie que des nombres, élément par élément ; pour un dataref
texte publié par un plugin (type « data »), seul le premier octet revient (vérifié le
2026-11-17 avec l'UFMC du BAe 146 : « FJCC/UFMC/LINE_3[1] » vaut toujours 0). L'API web
(X-Plane 12.1.1 et suivants, vérifié avec la 12.4.4) renvoie la valeur entière, en base64.

- HTTP  GET /api/v2/datarefs?filter[name]=…  → identifiant numérique du dataref ;
- WebSocket /api/v2 : « dataref_subscribe_values » ; X-Plane pousse ensuite les valeurs
  qui changent (« dataref_update_values »).

Lecture seule : rien n'est jamais écrit par ce module. Client WebSocket minimal écrit avec
la bibliothèque standard (pas de dépendance).
"""

import base64
import json
import os
import socket
import struct
import threading
import time
import urllib.parse
import urllib.request

WEB_PORT = 8086
RETRY_EVERY = 2.0        # s entre deux tentatives de connexion


# ------------------------------------------------------------ trames WebSocket (RFC 6455)
def ws_frame(payload: bytes, opcode=0x1, mask=None) -> bytes:
    """Trame client (toujours masquée)."""
    mask = mask if mask is not None else os.urandom(4)
    head = bytearray([0x80 | opcode])
    n = len(payload)
    if n < 126:
        head.append(0x80 | n)
    elif n < 1 << 16:
        head += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        head += bytes([0x80 | 127]) + struct.pack(">Q", n)
    return bytes(head) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


def parse_frame(buf: bytes):
    """Début de `buf` → (fin, opcode, données, octets consommés), ou None si incomplet."""
    if len(buf) < 2:
        return None
    fin, opcode = bool(buf[0] & 0x80), buf[0] & 0x0F
    masked, n = bool(buf[1] & 0x80), buf[1] & 0x7F
    pos = 2
    if n == 126:
        if len(buf) < 4:
            return None
        n, pos = struct.unpack(">H", buf[2:4])[0], 4
    elif n == 127:
        if len(buf) < 10:
            return None
        n, pos = struct.unpack(">Q", buf[2:10])[0], 10
    mask = None
    if masked:
        if len(buf) < pos + 4:
            return None
        mask, pos = buf[pos:pos + 4], pos + 4
    if len(buf) < pos + n:
        return None
    data = buf[pos:pos + n]
    if mask:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return fin, opcode, data, pos + n


def decode_value(value):
    """Valeur reçue : texte base64 (dataref « data ») → octets ; nombres inchangés."""
    if isinstance(value, str):
        return base64.b64decode(value)
    return value


class WebSocket:
    def __init__(self, host, port, path, timeout=5.0):
        self.sock = socket.create_connection((host, port), timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
                           "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise OSError("connexion fermée pendant la poignée de main")
            buf += chunk
        head, self.buf = buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n")[0] + b" ":
            raise OSError(f"refus du WebSocket : {head.splitlines()[0]!r}")

    def send_json(self, obj):
        self.sock.sendall(ws_frame(json.dumps(obj).encode()))

    def recv_json(self):
        """Message suivant (JSON) ; répond aux ping ; OSError si la connexion se ferme."""
        parts = []
        while True:
            frame = parse_frame(self.buf)
            if frame is None:
                chunk = self.sock.recv(65536)
                if not chunk:
                    raise OSError("connexion fermée")
                self.buf += chunk
                continue
            fin, opcode, data, used = frame
            self.buf = self.buf[used:]
            if opcode == 0x8:
                raise OSError("connexion fermée par X-Plane")
            if opcode == 0x9:
                self.sock.sendall(ws_frame(data, opcode=0xA))
                continue
            if opcode in (0x0, 0x1, 0x2):
                parts.append(data)
                if fin:
                    return json.loads(b"".join(parts))

    def close(self):
        try:
            self.sock.sendall(ws_frame(b"", opcode=0x8))
        except OSError:
            pass
        self.sock.close()


class XPlaneWeb:
    """Abonnement en lecture à des datarefs par l'API web ; même usage que sim.xplane.XPlane
    pour la lecture (`subscribe`, `poll`, `values`, `connected`)."""

    def __init__(self, host="127.0.0.1", port=WEB_PORT):
        self.host, self.port = host, port
        self.names = []
        self.values = {}
        self.connected = False
        self.error = None
        self._changed = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._ws = None

    def subscribe(self, name):
        if name not in self.names:
            self.names.append(name)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="X-Plane web", daemon=True)
        self._thread.start()
        return self

    def poll(self):
        """Valeurs changées depuis l'appel précédent : {nom: valeur}."""
        with self._lock:
            out, self._changed = self._changed, {}
        return out

    def close(self):
        self._stop.set()
        if self._ws is not None:
            self._ws.close()

    # ------------------------------------------------------------ fil de lecture
    def _get(self, path):
        with urllib.request.urlopen(f"http://{self.host}:{self.port}{path}", timeout=3) as r:
            return json.loads(r.read())

    def _lookup(self):
        ids = {}
        for name in self.names:
            q = urllib.parse.urlencode({"filter[name]": name})
            found = self._get(f"/api/v2/datarefs?{q}").get("data") or []
            if found:
                ids[int(found[0]["id"])] = name
        return ids

    def _run(self):
        while not self._stop.is_set():
            try:
                ids = self._lookup()
                if not ids:
                    raise OSError("aucun des datarefs demandés n'existe (avion pas chargé ?)")
                self._ws = WebSocket(self.host, self.port, "/api/v2")
                self._ws.send_json({"req_id": 1, "type": "dataref_subscribe_values",
                                    "params": {"datarefs": [{"id": i} for i in ids]}})
                self._ws.sock.settimeout(None)
                self.connected, self.error = True, None
                while not self._stop.is_set():
                    msg = self._ws.recv_json()
                    if msg.get("type") != "dataref_update_values":
                        continue
                    with self._lock:
                        for key, value in (msg.get("data") or {}).items():
                            name = ids.get(int(key))
                            if name is not None:
                                value = decode_value(value)
                                self.values[name] = value
                                self._changed[name] = value
            except (OSError, ValueError, KeyError) as e:
                self.error = str(e)
            self.connected = False
            if self._ws is not None:
                self._ws.close()
                self._ws = None
            self._stop.wait(RETRY_EVERY)
