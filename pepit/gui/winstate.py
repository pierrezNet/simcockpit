"""Mémoire de la position et de la taille des fenêtres (QSettings, ~/.config/pepit/).

Enregistrée à chaque déplacement ou redimensionnement (après une courte pause), et pas
seulement à la fermeture : le mode --dev relance la fenêtre sans la fermer proprement.
"""

import shutil
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSettings, QTimer

# Avant le changement de nom (2026-11-28), les réglages étaient dans ~/.config/simcockpit/ :
# ils sont repris une fois, pour garder les positions et les écrans des fenêtres.
_OLD = Path.home() / ".config" / "simcockpit" / "fenetres.conf"
_NEW = Path.home() / ".config" / "pepit" / "fenetres.conf"


class _Saver(QObject):
    def __init__(self, window, key):
        super().__init__(window)
        self.window, self.key = window, key
        self.timer = QTimer(self, singleShot=True, interval=500, timeout=self.save)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Move, QEvent.Resize):
            self.timer.start()
        elif event.type() == QEvent.Close:
            self.save()
        return False

    def save(self):
        settings().setValue(self.key, self.window.saveGeometry())


def settings():
    if not _NEW.exists() and _OLD.exists():
        _NEW.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_OLD, _NEW)
    return QSettings("pepit", "fenetres")


def remember(window, key, default_size):
    """Restaure la géométrie enregistrée sous `key` (sinon `default_size`), puis la suit."""
    geometry = settings().value(key)
    if geometry is None or not window.restoreGeometry(geometry):
        window.resize(*default_size)
    window.installEventFilter(_Saver(window, key))
