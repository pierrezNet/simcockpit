"""Page Cartes : la liste des cartes détectées à gauche, la vue de la carte choisie à droite.

Une liste plutôt que des onglets : elle défile quel que soit le nombre de cartes. Chaque
ligne porte une pastille d'état (connectée, pilotée par le cockpit, en erreur).
"""

import sys

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QPushButton, QSplitter,
                               QStackedWidget, QVBoxLayout, QWidget)

from ..hw.hub import DeviceHub
from .card_view import CardView
from .qtenv import prepare
from .winstate import remember

# pastilles : état de la carte -> couleur
DOTS = {"connectée": "#2e9e44", "pilotée": "#3d8bfd", "erreur": "#e05555"}
LEGEND = {"connectée": "connectée", "pilotée": "pilotée par le cockpit", "erreur": "erreur"}
ROLE_KEY = Qt.UserRole      # clé de la carte portée par la ligne


def dot(color, size=12):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pix)


def card_key(detected):
    """Produit et port USB : stables d'un branchement à l'autre (le nœud hidraw, non)."""
    return f"{detected.info.product}@{detected.info.usb_port}"


class MainWindow(QMainWindow):
    def __init__(self, hub=None):
        super().__init__()
        self.hub = hub if hub is not None else DeviceHub()   # partagé avec le cockpit
        self.setWindowTitle("Pepit — cartes")
        remember(self, "banc_de_test", (1200, 700))   # position et taille mémorisées
        self.settings = QSettings("pepit", "app")
        self.views = {}  # clé de la carte -> CardView
        self.dots = {state: dot(color) for state, color in DOTS.items()}

        central = QWidget()
        lay = QVBoxLayout(central)
        bar = QHBoxLayout()
        self.found = QLabel()
        refresh = QPushButton("Rechercher les cartes")
        refresh.clicked.connect(self.rescan)
        self.follow = QCheckBox("Suivre la carte actionnée")
        self.follow.setToolTip("Affiche la carte dont on vient d'actionner une commande."
                               " Décochez si une carte a des entrées instables.")
        self.follow.setChecked(True)
        bar.addWidget(self.found, 1)
        bar.addWidget(self.follow)
        bar.addWidget(refresh)
        lay.addLayout(bar)

        self.list = QListWidget()
        self.list.setIconSize(QSize(12, 12))
        self.list.setMinimumWidth(180)
        self.list.setSpacing(2)
        self.stack = QStackedWidget()
        self.empty = QLabel("Aucune carte de cockpit détectée.\n"
                            "Branchez-la puis « Rechercher les cartes ».")
        self.empty.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(self.empty)
        self.list.currentItemChanged.connect(self._select)
        side = QWidget()
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(0, 0, 0, 0)
        side_lay.addWidget(self.list, 1)
        legend = QLabel("<br>".join(f"<span style='color:{DOTS[k]}'>●</span> {text}"
                                    for k, text in LEGEND.items()))
        legend.setStyleSheet("padding:2px 4px;")
        side_lay.addWidget(legend)
        self.split = QSplitter(Qt.Horizontal)
        self.split.addWidget(side)
        self.split.addWidget(self.stack)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([240, 960])
        state = self.settings.value("cartes/separateur")
        if state is not None:
            self.split.restoreState(state)
        self.split.splitterMoved.connect(
            lambda *_: self.settings.setValue("cartes/separateur", self.split.saveState()))
        lay.addWidget(self.split, 1)
        self.setCentralWidget(central)
        self.rescan()

    # ------------------------------------------------------------ cartes
    def rescan(self):
        chosen = self.current_key() or self.settings.value("cartes/choisie")
        for view in self.views.values():          # chacun se désabonne ; les cartes restent
            view.stop()                            # ouvertes par le concentrateur
            self.stack.removeWidget(view)
            view.deleteLater()
        self.views.clear()
        self.list.blockSignals(True)
        self.list.clear()
        self.list.blockSignals(False)
        cards = self.hub.refresh()
        if not cards:
            self.found.setText("Aucune carte de cockpit détectée.")
            self.stack.setCurrentWidget(self.empty)
            return
        self.found.setText(f"{len(cards)} carte(s) détectée(s)")
        for d in sorted(cards, key=lambda d: (d.label, d.info.usb_port or "")):
            key = card_key(d)
            if key in self.views:                  # deux nœuds sur un même port
                key = f"{key}@{d.info.path}"
            view = CardView(d, self.hub)
            self.stack.addWidget(view)
            self.views[key] = view
            item = QListWidgetItem(f"{d.label.split(' (')[0]}\nport {d.info.usb_port}")
            item.setData(ROLE_KEY, key)
            self.list.addItem(item)
            view.activity.connect(lambda v=view: self._follow(v))
            view.health_changed.connect(lambda v=view, i=item: self._paint(v, i))
            view.start()
            self._paint(view, item)
        rows = [self.list.item(r).data(ROLE_KEY) for r in range(self.list.count())]
        self.list.setCurrentRow(rows.index(chosen) if chosen in rows else 0)

    def current_key(self):
        item = self.list.currentItem()
        return item.data(ROLE_KEY) if item is not None else None

    def _paint(self, view, item):
        state, detail = view.health()
        item.setIcon(self.dots[state])
        d = view.detected
        item.setToolTip(f"{d.label}\n{d.info.path}, port {d.info.usb_port}\n{detail}")

    def _select(self, item, _previous=None):
        if item is None:
            return
        key = item.data(ROLE_KEY)
        self.stack.setCurrentWidget(self.views[key])
        self.settings.setValue("cartes/choisie", key)

    def _follow(self, view):
        if not self.follow.isChecked() or self.stack.currentWidget() is view:
            return
        for r in range(self.list.count()):
            if self.views.get(self.list.item(r).data(ROLE_KEY)) is view:
                self.list.setCurrentRow(r)
                return

    def closeEvent(self, event):
        for view in self.views.values():
            view.stop()
        super().closeEvent(event)


def main():
    prepare()
    app = QApplication(sys.argv)
    hub = DeviceHub()
    win = MainWindow(hub)
    win.show()
    code = app.exec()
    hub.close()
    return code
