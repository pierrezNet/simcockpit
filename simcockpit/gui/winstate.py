"""Mémoire de la position et de la taille des fenêtres (QSettings, ~/.config/simcockpit/).

Enregistrée à chaque déplacement ou redimensionnement (après une courte pause), et pas
seulement à la fermeture : le mode --dev relance la fenêtre sans la fermer proprement.
"""

from PySide6.QtCore import QEvent, QObject, QSettings, QTimer


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
    return QSettings("simcockpit", "fenetres")


def remember(window, key, default_size):
    """Restaure la géométrie enregistrée sous `key` (sinon `default_size`), puis la suit."""
    geometry = settings().value(key)
    if geometry is None or not window.restoreGeometry(geometry):
        window.resize(*default_size)
    window.installEventFilter(_Saver(window, key))
