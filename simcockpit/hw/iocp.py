"""Serveur IOCP : le protocole réseau de SIOC (OpenCockpits), pour les cartes en wifi
(Arduino, ESP8266…) écrites pour SIOC.

Texte sur TCP (port 8092 par défaut), une ligne par message, champs séparés par « : » :
- la carte se connecte et annonce les variables qu'elle veut recevoir :
      Arn.Inicio:201:202:203:
- le serveur lui envoie leurs valeurs (entiers), à l'annonce puis à chaque changement :
      Arn.Resp:201=3679:202=3650:203=0:
- le serveur envoie régulièrement « Arn.Vivo: », la carte répond « Arn.Vivo: » ;
- une carte peut aussi envoyer « Arn.Resp:var=valeur: » (entrées), remontées ici.

Relu dans le programme de l'afficheur carburant (ESP8266) écrit pour le MD-80 sous SIOC,
2026-11-25. La carte se connecte à nous : rien n'est envoyé tant qu'elle ne s'annonce pas.
"""

import selectors
import socket
import threading
import time

DEFAULT_PORT = 8092
VIVO_EVERY = 5.0         # s entre deux « Arn.Vivo: »


def parse_line(line):
    """Ligne reçue → (« Inicio », [variables]) ou (« Resp », {variable: valeur}) ou
    (« Vivo », None) ; None si la ligne n'est pas un message IOCP."""
    line = line.strip()
    if not line.startswith("Arn."):
        return None
    kind, _, rest = line[4:].partition(":")
    fields = [f for f in rest.split(":") if f]
    if kind == "Inicio":
        return "Inicio", [int(f) for f in fields if f.strip().lstrip("-").isdigit()]
    if kind == "Resp":
        values = {}
        for f in fields:
            var, eq, value = f.partition("=")
            if eq and var.strip().isdigit():
                try:
                    values[int(var)] = int(float(value))
                except ValueError:
                    pass
        return "Resp", values
    if kind == "Vivo":
        return "Vivo", None
    return None


def resp_line(values):
    """{variable: valeur} → « Arn.Resp:201=3679:202=3650:\\n » (valeurs entières)."""
    body = "".join(f"{var}={int(round(value))}:" for var, value in sorted(values.items()))
    return f"Arn.Resp:{body}\n"


VIVO_LINE = "Arn.Vivo:\n"


class _Client:
    def __init__(self, sock, addr):
        self.sock, self.addr = sock, addr
        self.buf = b""
        self.wanted = set()          # variables annoncées par « Inicio »
        self.sent = {}               # variable → dernière valeur envoyée


class IocpServer:
    """Serveur IOCP dans son propre fil. `set_values` (depuis le moteur) fixe les valeurs ;
    `poll_inputs` rend les valeurs reçues des cartes ; `clients` les cartes connectées."""

    def __init__(self, port=DEFAULT_PORT, host="0.0.0.0"):
        self.port, self.host = port, host
        self.values = {}
        self.error = None
        self._inputs = {}
        self._clients = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._listener = None

    @property
    def clients(self):
        with self._lock:
            return [f"{c.addr[0]}" for c in self._clients]

    def start(self):
        self._listener = socket.create_server((self.host, self.port), reuse_port=False)
        self._listener.setblocking(False)
        self._thread = threading.Thread(target=self._run, name=f"IOCP {self.port}", daemon=True)
        self._thread.start()
        return self

    def set_values(self, values):
        with self._lock:
            self.values.update(values)

    def poll_inputs(self):
        with self._lock:
            out, self._inputs = self._inputs, {}
        return out

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        for c in list(self._clients):
            c.sock.close()
        if self._listener:
            self._listener.close()

    # ------------------------------------------------------------ fil du serveur
    def _drop(self, sel, client):
        sel.unregister(client.sock)
        client.sock.close()
        with self._lock:
            self._clients.remove(client)

    def _send(self, sel, client, text):
        try:
            client.sock.sendall(text.encode("ascii"))
        except OSError:
            self._drop(sel, client)

    def _run(self):
        sel = selectors.DefaultSelector()
        sel.register(self._listener, selectors.EVENT_READ, None)
        last_vivo = time.monotonic()
        try:
            while not self._stop.is_set():
                for key, _ in sel.select(timeout=0.05):
                    if key.data is None:                       # nouvelle carte
                        sock, addr = self._listener.accept()
                        sock.setblocking(False)
                        client = _Client(sock, addr)
                        sel.register(sock, selectors.EVENT_READ, client)
                        with self._lock:
                            self._clients.append(client)
                        continue
                    client = key.data
                    try:
                        data = client.sock.recv(4096)
                    except OSError:
                        data = b""
                    if not data:
                        self._drop(sel, client)
                        continue
                    client.buf += data
                    while b"\n" in client.buf:
                        raw, client.buf = client.buf.split(b"\n", 1)
                        msg = parse_line(raw.decode("ascii", "replace"))
                        if msg is None:
                            continue
                        kind, payload = msg
                        if kind == "Inicio":
                            client.wanted.update(payload)
                            client.sent = {}                   # tout renvoyer
                        elif kind == "Resp":
                            with self._lock:
                                self._inputs.update(payload)
                # valeurs changées → chaque carte reçoit celles qu'elle a demandées
                with self._lock:
                    values = dict(self.values)
                    clients = list(self._clients)
                for client in clients:
                    changed = {v: values[v] for v in client.wanted
                               if v in values and client.sent.get(v) != int(round(values[v]))}
                    if changed:
                        client.sent.update({v: int(round(x)) for v, x in changed.items()})
                        self._send(sel, client, resp_line(changed))
                now = time.monotonic()
                if now - last_vivo >= VIVO_EVERY:
                    last_vivo = now
                    for client in clients:
                        if client in self._clients:
                            self._send(sel, client, VIVO_LINE)
        except OSError as e:
            self.error = str(e)
        finally:
            sel.close()
