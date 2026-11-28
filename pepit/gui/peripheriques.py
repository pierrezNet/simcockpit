"""Page Périphériques : ce qui est branché en USB, où, depuis quand, et si Pepit y a accès.

Le veilleur (`UsbWatcher`) tourne dès le lancement de Pepit, page ouverte ou non : il
suit les branchements (hw/uevent.py), relit sysfs (hw/usb.py) et tient l'historique.
La page ne fait qu'afficher ce qu'il a relevé.
"""

import time

from PySide6.QtCore import QObject, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView, QLabel,
                               QListWidget, QMainWindow, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..hw import usb
from ..hw.uevent import UeventMonitor
from .winstate import remember

SETTLE = 400         # ms sans événement avant de relire (un branchement en produit une rafale)
ACL_DELAY = 2000     # ms : udev pose les droits un peu après le noyau, on relit encore

# pastille : état -> (couleur, texte)
STATES = {"ok": ("#2e9e44", "accessible"), "partiel": ("#f0a020", "accès partiel"),
          "refusé": ("#e05555", "accès refusé"), "": ("#7b8a92", "branché (pas de nœud utile)"),
          "absent": ("#4a5257", "débranché")}
COLUMNS = ["", "Périphérique", "Pour Pepit", "VID:PID", "Port", "Vitesse", "Courant",
           "Branché", "Première fois", "Dernière fois", "Nœuds (✓ accessible)"]


class UsbWatcher(QObject):
    """Relevés USB et historique, en tâche de fond. `updated(changes)` après chaque relevé."""

    updated = Signal(list)
    _poke = Signal()                     # depuis le fil de surveillance

    def __init__(self, history=None, parent=None):
        super().__init__(parent)
        self.history = history if history is not None else usb.History()
        self.devices = []
        self._settle = QTimer(self, singleShot=True, interval=SETTLE, timeout=self._after_event)
        self._acl = QTimer(self, singleShot=True, interval=ACL_DELAY, timeout=self.refresh)
        self._poke.connect(self._settle.start)
        self.monitor = UeventMonitor(lambda action, props: self._poke.emit())

    @property
    def live(self):
        return self.monitor.live

    def start(self):
        self.monitor.start()
        self.refresh()
        return self

    def stop(self):
        self.monitor.stop()

    def _after_event(self):
        self.refresh()
        self._acl.start()

    def refresh(self):
        self.devices = usb.scan()
        changes = self.history.update(self.devices)
        self.updated.emit(changes)


def _item(text, tip=None, color=None):
    it = QTableWidgetItem(text)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if tip:
        it.setToolTip(tip)
    if color:
        it.setForeground(QBrush(QColor(color)))
    return it


class PeripheriquesPage(QMainWindow):
    def __init__(self, watcher):
        super().__init__()
        self.watcher = watcher
        self.settings = QSettings("pepit", "app")
        self.setWindowTitle("Pepit — périphériques")
        remember(self, "peripheriques", (1150, 600))

        body = QWidget()
        lay = QVBoxLayout(body)
        bar = QHBoxLayout()
        self.summary = QLabel()
        self.only_cockpit = QCheckBox("Cartes de cockpit seulement")
        self.only_cockpit.setChecked(self.settings.value("peripheriques/cockpit", False, bool))
        self.show_absent = QCheckBox("Montrer les débranchés")
        self.show_absent.setChecked(self.settings.value("peripheriques/debranches", True, bool))
        for box, key in ((self.only_cockpit, "cockpit"), (self.show_absent, "debranches")):
            box.toggled.connect(lambda on, k=key: (
                self.settings.setValue(f"peripheriques/{k}", on), self.fill()))
        again = QPushButton("Relire")
        again.clicked.connect(watcher.refresh)
        bar.addWidget(self.summary, 1)
        bar.addWidget(self.only_cockpit)
        bar.addWidget(self.show_absent)
        bar.addWidget(again)
        lay.addLayout(bar)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeToContents)
        head.setStretchLastSection(True)    # les nœuds : liste parfois longue
        self.journal = QListWidget()
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.table)
        holder = QWidget()
        jl = QVBoxLayout(holder)
        jl.setContentsMargins(0, 0, 0, 0)
        jl.addWidget(QLabel("Journal (depuis le lancement de Pepit)"))
        jl.addWidget(self.journal)
        split.addWidget(holder)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)
        legend = QLabel("   ".join(f"<span style='color:{c}'>●</span> {t}"
                                   for c, t in STATES.values()))
        lay.addWidget(legend)
        self.setCentralWidget(body)

        watcher.updated.connect(self.on_update)
        self.fill()

    # ------------------------------------------------------------ données
    def on_update(self, changes):
        for kind, seen, dev in changes:
            port = dev.port if dev is not None else (seen.ports[-1] if seen.ports else "?")
            extra = f", {STATES[dev.access][1]}" if dev is not None and dev.nodes else ""
            self.journal.insertItem(0, f"{time.strftime('%H:%M:%S')}   {kind} : {seen.name}"
                                       f" (port {port}{extra})")
        self.fill()

    def rows(self):
        """(Seen, UsbDevice ou None) à afficher : branchés d'abord, puis par nom."""
        present = {d.key: d for d in self.watcher.devices}
        out = []
        for key, seen in self.watcher.history.seen.items():
            dev = present.get(key)
            if dev is None and not self.show_absent.isChecked():
                continue
            if self.only_cockpit.isChecked() and not seen.cockpit:
                continue
            out.append((seen, dev))
        out.sort(key=lambda r: (r[1] is None, not r[0].cockpit, r[0].name.lower()))
        return out

    def fill(self):
        rows = self.rows()
        n = len(self.watcher.devices)
        mode = ("surveillance en direct" if self.watcher.live
                else "relecture chaque seconde (événements du noyau indisponibles)")
        self.summary.setText(f"{n} périphérique(s) branché(s) — {mode}")
        self.table.setRowCount(len(rows))
        for r, (seen, dev) in enumerate(rows):
            state = dev.access if dev is not None else "absent"
            color, label = STATES[state]
            grey = STATES["absent"][0] if dev is None else None
            dot = _item("●", label, color)
            dot.setTextAlignment(Qt.AlignCenter)
            if dev is not None:
                nodes = ", ".join(f"{x.name} {'✓' if x.access else '✗'}" for x in dev.nodes)
                tip = "\n".join(f"{x.path} ({x.kind}) : {'accessible' if x.access else 'refusé'}"
                                f"{'' if x in dev.useful_nodes else ' — non utilisé par Pepit'}"
                                for x in dev.nodes)
                cells = [dot, _item(seen.name, f"{seen.name}\nclé : {dev.key}"),
                         _item(seen.pepit), _item(seen.vid_pid), _item(dev.port),
                         _item(dev.speed_label), _item(f"{dev.max_power} mA"),
                         _item(f"{seen.plugs} fois"), _item(seen.first), _item("maintenant"),
                         _item(nodes, tip or None)]
            else:
                ports = ", ".join(seen.ports)
                cells = [dot, _item(seen.name, f"{seen.name}\nports vus : {ports}", grey),
                         _item(seen.pepit, None, grey), _item(seen.vid_pid, None, grey),
                         _item(seen.ports[-1] if seen.ports else "", f"ports vus : {ports}", grey),
                         _item("", None, grey), _item("", None, grey),
                         _item(f"{seen.plugs} fois", None, grey), _item(seen.first, None, grey),
                         _item(seen.last, None, grey), _item("", None, grey)]
            for c, it in enumerate(cells):
                self.table.setItem(r, c, it)
