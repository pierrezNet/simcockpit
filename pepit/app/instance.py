"""Une seule instance de Pepit.

Le premier lanceur devient l'instance et ouvre un canal local (QLocalServer), réservé au
compte de l'utilisateur. Les lanceurs suivants s'y connectent, transmettent la page à
afficher (« afficher<TAB>cartes ») et se terminent : lancer pepit-cartes puis
pepit-peripheriques ajoute la page Périphériques au Pepit déjà ouvert.
"""

import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SEP = "\t"


def server_name():
    return f"pepit-{os.getuid()}"


def encode(*fields):
    return SEP.join(str(f) for f in fields)


def decode(line):
    return [f for f in line.strip().split(SEP) if f != ""]


def send(message, name=None, timeout=500):
    """Transmet `message` à l'instance déjà ouverte ; False s'il n'y en a pas."""
    sock = QLocalSocket()
    sock.connectToServer(name or server_name())
    if not sock.waitForConnected(timeout):
        return False
    sock.write((message + "\n").encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(timeout)
    sock.disconnectFromServer()
    return True


class Instance(QObject):
    """Le canal de l'instance : `message` est émis pour chaque ligne reçue d'un lanceur."""

    message = Signal(str)

    def __init__(self, name=None, parent=None):
        super().__init__(parent)
        self.name = name or server_name()
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)   # ce compte seulement
        self.server.newConnection.connect(self._accept)

    def listen(self):
        if self.server.listen(self.name):
            return True
        # canal laissé par un Pepit arrêté brutalement : personne ne répond, on le reprend
        QLocalServer.removeServer(self.name)
        return self.server.listen(self.name)

    def close(self):
        self.server.close()

    def _accept(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: self._read(s))
            sock.disconnected.connect(sock.deleteLater)
            self._read(sock)                     # ce qui est déjà arrivé

    def _read(self, sock):
        while sock.canReadLine():
            line = bytes(sock.readLine()).decode("utf-8", "replace").strip()
            if line:
                self.message.emit(line)
