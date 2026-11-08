"""Application « panneau virtuel » : lit cockpit.yaml, connecte les cartes, affiche les instruments.

Lancement : .venv/bin/python -m simcockpit.panel [cockpit.yaml]
"""

import sys
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QLabel, QListWidget,
                               QMainWindow, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from ..logic import config
from ..logic.controls import Encoder, OctalDigits, Selector, SpeedEncoder, Switch
from ..gui.qtenv import prepare
from ..logic.engine import Engine

LCD = ("background:#111; color:#ffb000; font-family:monospace; font-size:56px;"
       " font-weight:bold; padding:6px 18px; border:2px solid #444; border-radius:6px;")
POS_ON = "background:#2e9e44; color:white; font-weight:bold; padding:6px 14px; border-radius:4px;"
POS_OFF = "background:#3a3f47; color:#9aa; padding:6px 14px; border-radius:4px;"


class ControlWidget(QWidget):
    """Affichage d'une commande selon son type."""

    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        out = " → ".join(x for x in (ctrl.display and f"afficheur {ctrl.display}",
                                      ctrl.led and f"voyant {ctrl.led}") if x)
        title = QLabel(f"<b>{ctrl.name}</b> <span style='color:#888'>— {ctrl.describe()}"
                       + (f" — sortie : {out}" if out else "") + "</span>")
        title.setWordWrap(True)               # sinon la fenêtre s'élargit pour tout afficher
        lay.addWidget(title)
        if isinstance(ctrl, (OctalDigits, Encoder)):
            self.lcd = QLabel("----")
            self.lcd.setStyleSheet(LCD if isinstance(ctrl, OctalDigits)
                                   else LCD.replace("56px", "34px"))
            self.lcd.setAlignment(Qt.AlignCenter)
            lay.addWidget(self.lcd)
        elif isinstance(ctrl, Selector):
            row = QHBoxLayout()
            # affichage dans l'ordre physique habituel : défaut à gauche
            self.pos = {}
            for name in [ctrl.default] + list(reversed(list(ctrl.positions))):
                lab = QLabel(name)
                lab.setStyleSheet(POS_OFF)
                row.addWidget(lab)
                self.pos[name] = lab
            row.addStretch()
            lay.addLayout(row)
        elif isinstance(ctrl, Switch):
            self.ind = QLabel("—")
            self.ind.setStyleSheet(POS_OFF)
            lay.addWidget(self.ind)

    def show_value(self, value):
        if isinstance(self.ctrl, SpeedEncoder):
            self.lcd.setText(f"IAS {value}" if self.ctrl.mode == "IAS" else f"M .{value:02d}")
        elif isinstance(self.ctrl, Encoder):
            width = len(str(self.ctrl.max)) if self.ctrl.leading_zeros else 0
            self.lcd.setText(f"{value:0{width}d}" if width else str(value))
        elif isinstance(self.ctrl, OctalDigits):
            self.lcd.setText(value)
        elif isinstance(self.ctrl, Selector):
            for name, lab in self.pos.items():
                lab.setStyleSheet(POS_ON if name == value else POS_OFF)
        elif isinstance(self.ctrl, Switch):
            self.ind.setText("ACTIONNÉ" if value else "repos")
            self.ind.setStyleSheet(POS_ON if value else POS_OFF)


class PanelWindow(QMainWindow):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.engine = None
        self.widgets = {}
        self.setWindowTitle(f"simcockpit — panneau virtuel ({path})")
        self.resize(1200, 700)   # même taille que simcockpit-gui

        central = QWidget()
        self.root = QVBoxLayout(central)
        bar = QHBoxLayout()
        self.cards_label = QLabel()
        self.cards_label.setTextFormat(Qt.RichText)
        self.cards_label.setWordWrap(True)
        reload_btn = QPushButton("Recharger la configuration")
        reload_btn.clicked.connect(self.load)
        bar.addWidget(self.cards_label, 1)
        bar.addWidget(reload_btn)
        self.root.addLayout(bar)
        self.tabs = QTabWidget()          # un onglet par instrument
        self.root.addWidget(self.tabs, 1)
        self.root.addWidget(QLabel("Journal de la logique métier"))
        self.log = QListWidget()
        self.log.setMaximumHeight(160)
        self.root.addWidget(self.log)
        self.setCentralWidget(central)

        self.tick = QTimer(self, interval=20, timeout=self._step)
        self.retry = QTimer(self, interval=2000, timeout=self._connect)
        self.load()

    def _clear_body(self):
        current = self.tabs.tabText(self.tabs.currentIndex()) if self.tabs.count() else None
        while self.tabs.count():
            w = self.tabs.widget(0)
            self.tabs.removeTab(0)
            w.deleteLater()
        return current

    def load(self):
        self.tick.stop()
        self.retry.stop()
        if self.engine:
            self.engine.close()
        previous_tab = self._clear_body()
        self.widgets.clear()
        try:
            cockpit = config.load(self.path)
        except (OSError, config.ConfigError, Exception) as e:  # YAML invalide inclus
            self.cards_label.setText(f"<span style='color:#e55'>Configuration invalide : {e}</span>")
            self.engine = None
            return
        self.engine = Engine(cockpit)
        for inst in cockpit.instruments.values():
            page = QWidget()
            outer = QVBoxLayout(page)
            outer.addWidget(QLabel(f"<i>carte « {inst.card} » ({cockpit.cards[inst.card].product})</i>"))
            lay = QGridLayout()
            for k, (name, ctrl) in enumerate(inst.controls.items()):
                w = ControlWidget(ctrl)
                lay.addWidget(w, k // 3, k % 3)
                self.widgets[(inst.id, name)] = w
            outer.addLayout(lay)
            outer.addStretch()
            self.tabs.addTab(page, inst.label)
            if inst.label == previous_tab:
                self.tabs.setCurrentWidget(page)
        self._log("configuration chargée : " + ", ".join(cockpit.instruments))
        self._connect()
        self.tick.start()
        self.retry.start()

    def _connect(self):
        if not self.engine:
            return
        before = dict(self.engine.status)
        status = self.engine.connect()
        for cid, st in status.items():
            if st != before.get(cid):
                self._log(f"carte {cid} : {st}")
        self.cards_label.setText(" &nbsp; ".join(
            f"<b>{cid}</b> ({self.engine.cockpit.cards[cid].product}) : "
            f"<span style='color:{'#4c4' if st.startswith('connectée') else '#e55'}'>{st}</span>"
            for cid, st in status.items()))

    def _step(self):
        if not self.engine:
            return
        for ch in self.engine.step():
            w = self.widgets.get((ch.instrument, ch.control))
            if w:
                w.show_value(ch.value)
            self._log(f"{ch.instrument}.{ch.control} = {ch.value}")

    def _log(self, text):
        self.log.insertItem(0, time.strftime("%H:%M:%S  ") + text)
        if self.log.count() > 300:
            self.log.takeItem(300)

    def closeEvent(self, event):
        if self.engine:
            self.engine.close()
        super().closeEvent(event)


def main():
    prepare()
    app = QApplication(sys.argv)
    path = sys.argv[1] if len(sys.argv) > 1 else "cockpit.yaml"
    win = PanelWindow(path)
    win.show()
    return app.exec()
