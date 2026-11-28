"""Branchements et débranchements en direct : les événements du noyau (uevent).

La prise netlink NETLINK_KOBJECT_UEVENT, groupe 1, reçoit les mêmes événements que
« udevadm monitor --kernel », sans droit particulier ni dépendance. Si elle n'est pas
disponible, on prévient toutes les secondes : l'appelant relit sysfs.

`callback(action, props)` est appelé depuis le fil de surveillance : l'interface doit
repasser dans son propre fil (signal Qt).
"""

import select
import socket
import threading

NETLINK_KOBJECT_UEVENT = 15
SUBSYSTEMS = {"usb", "hidraw", "tty", "input"}
POLL = 1.0           # repli : relecture de sysfs toutes les secondes


def parse(data: bytes):
    """« add@/devices/… \\0 ACTION=add \\0 SUBSYSTEM=usb … » -> (action, {clé: valeur})."""
    parts = data.split(b"\0")
    head = parts[0].decode("utf-8", "replace")
    props = {}
    for p in parts[1:]:
        if b"=" in p:
            k, v = p.decode("utf-8", "replace").split("=", 1)
            props[k] = v
    action = props.get("ACTION") or head.split("@", 1)[0]
    return action, props


class UeventMonitor:
    def __init__(self, callback):
        self.callback = callback
        self.live = False            # vrai : événements du noyau ; faux : relecture périodique
        self._stop = threading.Event()
        self._thread = None
        self._sock = None

    def start(self):
        try:
            sock = socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM | socket.SOCK_CLOEXEC,
                                 NETLINK_KOBJECT_UEVENT)
            sock.bind((0, 1))
            self._sock, self.live = sock, True
        except (OSError, AttributeError):          # AttributeError : pas de netlink (hors Linux)
            self._sock, self.live = None, False
        self._thread = threading.Thread(target=self._run, name="uevent", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._sock:
            self._sock.close()

    def _run(self):
        while not self._stop.is_set():
            if self._sock is None:
                if not self._stop.wait(POLL):
                    self.callback("poll", {})
                continue
            ready, _, _ = select.select([self._sock], [], [], 0.25)
            if not ready:
                continue
            try:
                data = self._sock.recv(65536)
            except OSError:
                continue
            action, props = parse(data)
            if props.get("SUBSYSTEM") in SUBSYSTEMS:
                self.callback(action, props)
