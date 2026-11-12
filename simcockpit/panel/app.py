"""Application « panneau virtuel » : lit la configuration, connecte les cartes, affiche les instruments.

Lancement : .venv/bin/python -m simcockpit.panel [config/avions/rj85-simule | dossier d'avion | fichier .yaml]
"""

import sys
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QCheckBox, QDoubleSpinBox, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow,
                               QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ..logic import config
from ..hw import dme as dme_hw
from ..logic.controls import Encoder, OctalDigits, Selector, SpeedEncoder, Switch
from ..logic.dme_indicator import DmeIndicator
from ..logic.radio_panel import RadioPanel
from ..logic.rj_autopilot import RjAutopilot
from ..gui.qtenv import prepare
from ..logic.engine import Engine

LCD = ("background:#111; color:#ffb000; font-family:monospace; font-size:56px;"
       " font-weight:bold; padding:6px 18px; border:2px solid #444; border-radius:6px;")
POS_ON = "background:#2e9e44; color:white; font-weight:bold; padding:6px 14px; border-radius:4px;"
POS_OFF = "background:#3a3f47; color:#9aa; padding:6px 14px; border-radius:4px;"


class DmeScreen(QWidget):
    """Écran du DME dessiné aux positions du vrai (relevées sur photos, en fraction de largeur).

    Ligne du haut : 9 colonnes de caractères, distance calée à droite sur les colonnes 1-4,
    texte sur les colonnes 6-9. Ligne du bas : voyants à leur place fixe.
    """
    TOP = [0.14, 0.21, 0.28, 0.35, None, 0.62, 0.70, 0.78, 0.86]   # centres des colonnes 1-9
    LAMPS = {"1": 0.06, "2": 0.09, "3": 0.12, "WPT": 0.23, "NM": 0.33,
             "HLD": 0.56, "KT": 0.66, "MIN": 0.76, "ID": 0.86}
    ON, OFF, BG, DARK = QColor("#ffd8cf"), QColor(255, 216, 207, 28), QColor("#b3261e"), QColor("#24110f")

    def __init__(self):
        super().__init__()
        self.setFixedSize(440, 120)
        self.cells = [""] * 9          # caractère de chaque colonne
        self.dot = None                # colonne suivie d'un point décimal
        self.lit = set()
        self.powered = True

    def show(self, cells, dot, lit, powered=True):
        self.cells, self.dot, self.lit, self.powered = cells, dot, set(lit), powered
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor("#111"), 8))
        p.setBrush(self.BG if self.powered else self.DARK)
        p.drawRoundedRect(QRectF(4, 4, w - 8, h - 8), 8, 8)
        if not self.powered:
            return
        big = QFont("monospace", 30, QFont.Bold)
        p.setFont(big)
        p.setPen(self.ON)
        cw = 0.075 * w
        for col, ch in enumerate(self.cells):
            x = self.TOP[col]
            if x is None or not ch:
                continue
            p.drawText(QRectF(x * w - cw / 2, 12, cw, 54), Qt.AlignCenter, ch)
            if self.dot == col:
                p.drawText(QRectF(x * w + cw * 0.18, 12, cw * 0.6, 54), Qt.AlignCenter, ".")
        p.setFont(QFont("sans-serif", 9, QFont.Bold))
        for name, x in self.LAMPS.items():
            p.setPen(self.ON if name in self.lit else self.OFF)
            p.drawText(QRectF(x * w - 22, 76, 44, 22), Qt.AlignCenter, name)
        p.end()


def dme_cells(ctrl):
    """État de l'indicateur → (9 caractères, colonne du point, voyants allumés)."""
    left, right, lit = ctrl.fields()
    cells, dot = [""] * 9, None
    if left is None:
        cells[1:4] = list("---")
    else:
        if left < dme_hw.TENTHS_BELOW_NM:            # dixième affiché, point après l'unité
            digits = str(round(left * 10))
            digits = digits.rjust(2, "0")
            dot = 3 - 1
        else:                                        # entier tronqué au-delà de 200 NM
            digits = str(int(left))
        digits = digits[-4:]
        cells[4 - len(digits):4] = list(digits)
    if right is None:
        cells[6:9] = list("---")
    else:
        text = right.ljust(4) if ctrl.mode == "ID" else right.rjust(4)
        cells[5:9] = list(text[:4])
    return cells, dot, [x for x in lit.values() if x]


class DmeWidget(QWidget):
    """Réplique de l'écran du DME, boutons virtuels et données simulées (en attendant X-Plane)."""

    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        lay = QVBoxLayout(self)
        title = QLabel(f"<b>{ctrl.name}</b> <span style='color:#888'>— {ctrl.describe()}</span>")
        title.setWordWrap(True)
        lay.addWidget(title)
        self.screen = DmeScreen()
        lay.addWidget(self.screen)

        row = QHBoxLayout()
        for text, fn, tip in (("SEL", ctrl.press_sel, "ID → KT → MIN"),
                              ("PWR", ctrl.toggle_power, "marche / arrêt")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)

        sim = QGroupBox("Simulateur (en attendant X-Plane)")
        g = QGridLayout(sim)
        self.signal = QCheckBox("signal DME reçu")
        self.signal.setChecked(True)
        self.dist = QDoubleSpinBox(decimals=1, maximum=999.9, singleStep=0.1, value=3.2,
                                   suffix=" NM")
        self.gs = QSpinBox(maximum=999, value=240, suffix=" kt")
        self.ident = QLineEdit("LIL")
        self.ident.setMaxLength(4)
        self.fly = QCheckBox("voler vers la station")
        self.fly.setToolTip("la distance diminue selon la vitesse sol")
        g.addWidget(self.signal, 0, 0, 1, 2)
        g.addWidget(QLabel("Distance"), 1, 0)
        g.addWidget(self.dist, 1, 1)
        g.addWidget(QLabel("Vitesse sol"), 2, 0)
        g.addWidget(self.gs, 2, 1)
        g.addWidget(QLabel("Identifiant"), 3, 0)
        g.addWidget(self.ident, 3, 1)
        g.addWidget(self.fly, 4, 0, 1, 2)
        lay.addWidget(sim)
        for w, sig in ((self.signal, "toggled"), (self.dist, "valueChanged"),
                       (self.gs, "valueChanged"), (self.ident, "textChanged")):
            getattr(w, sig).connect(self._push)
        self._fly_timer = QTimer(self, interval=1000, timeout=self._fly_step)
        self.fly.toggled.connect(lambda on: self._fly_timer.start() if on else self._fly_timer.stop())
        self._push()

    def _push(self, *_):
        on = self.signal.isChecked()
        self.ctrl.set_sim(distance=self.dist.value() if on else None,
                          groundspeed=self.gs.value() if on else None,
                          ident=self.ident.text() if on else "")
        self.show_value(None)

    def _fly_step(self):
        self.dist.setValue(max(0.0, self.dist.value() - self.gs.value() / 3600))

    def show_value(self, _value):
        c = self.ctrl
        if not c.powered:
            self.screen.show([""] * 9, None, [], powered=False)
        elif c.testing:                              # test des segments : tout allumé
            self.screen.show(list("8888 8888"), None, DmeScreen.LAMPS)
        else:
            self.screen.show(*dme_cells(c))


class AutopilotWidget(QWidget):
    """Pilote automatique RJ : voyants du MCP, état des modes, boutons virtuels."""

    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        lay = QVBoxLayout(self)
        title = QLabel(f"<b>{ctrl.name}</b> <span style='color:#888'>— {ctrl.describe()}</span>")
        title.setWordWrap(True)
        lay.addWidget(title)
        self.state = QLabel()
        self.state.setStyleSheet("font-size:20px; font-weight:bold; padding:4px;")
        lay.addWidget(self.state)
        self.alert = QLabel()
        self.alert.setStyleSheet("background:#f0a020; color:#1c1600; font-weight:bold;"
                                 " padding:6px 10px; border-radius:4px;")
        self.alert.hide()
        lay.addWidget(self.alert)
        self._alert_timer = QTimer(self, singleShot=True, interval=3000, timeout=self.alert.hide)
        grid = QGridLayout()
        self.lamps = {}
        for k, name in enumerate(ctrl.led_states()):
            lab = QLabel(name)
            lab.setAlignment(Qt.AlignCenter)
            lab.setMinimumHeight(32)             # sinon le texte est rogné par le padding
            lab.setStyleSheet(POS_OFF)
            grid.addWidget(lab, k // 8, k % 8)
            self.lamps[name] = lab
        lay.addWidget(QLabel("Voyants du MCP"))
        lay.addLayout(grid)
        lay.addWidget(QLabel("Boutons virtuels (même effet qu'un appui sur le MCP)"))
        bgrid = QGridLayout()
        for k, name in enumerate(ctrl.buttons):
            b = QPushButton(name)
            b.clicked.connect(lambda _=False, n=name: ctrl.press(n))
            bgrid.addWidget(b, k // 8, k % 8)
        lay.addLayout(bgrid)
        self.show_value(None)

    def show_value(self, _value):
        if self.ctrl.alert:                         # alerte : bandeau orange pendant 3 s
            self.alert.setText("⚠ " + self.ctrl.alert)
            self.alert.show()
            self._alert_timer.start()
            self.ctrl.alert = None
        self.state.setText(self.ctrl.summary())
        for name, on in self.ctrl.led_states().items():
            self.lamps[name].setStyleSheet(POS_ON if on else POS_OFF)


class RadioWidget(QWidget):
    """Boîtier radio : source choisie, fréquences ACTIVE / STANDBY, boutons virtuels."""

    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        lay = QVBoxLayout(self)
        title = QLabel(f"<b>{ctrl.name}</b> <span style='color:#888'>— {ctrl.describe()}</span>")
        title.setWordWrap(True)
        lay.addWidget(title)
        self.lcd = QLabel()
        self.lcd.setStyleSheet(LCD.replace("56px", "30px"))
        lay.addWidget(self.lcd)
        row = QHBoxLayout()
        for s in ctrl.sources:
            b = QPushButton(s.name)
            b.clicked.connect(lambda _=False, n=s.name: ctrl.select(n))
            row.addWidget(b)
        b = QPushButton("⇄ transfert")
        b.clicked.connect(ctrl.swap)
        row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.show_value(None)

    def show_value(self, _value):
        if not self.ctrl.powered:
            self.lcd.setText("radio éteinte")
            return
        texts, _ = self.ctrl.radio_display()
        self.lcd.setText(f"{self.ctrl.selected.name}   {texts['ACTIVE']}  ⇄  {texts['STANDBY']}")


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
            shown, _ = self.ctrl.shown(value)        # min_digits, blank_when, blank_unless
            width = len(str(self.ctrl.max)) if self.ctrl.leading_zeros else 0
            if shown is None:
                self.lcd.setText("")
            elif isinstance(shown, int) and width:
                self.lcd.setText(f"{shown:0{width}d}")
            else:
                self.lcd.setText(str(shown))
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
                if isinstance(ctrl, RjAutopilot):          # sur toute la largeur, sous les afficheurs
                    w = AutopilotWidget(ctrl)
                    lay.addWidget(w, 100, 0, 1, 3)
                elif isinstance(ctrl, RadioPanel):
                    w = RadioWidget(ctrl)
                    lay.addWidget(w, k // 3, 0, 1, 3)
                else:
                    w = DmeWidget(ctrl) if isinstance(ctrl, DmeIndicator) else ControlWidget(ctrl)
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
        self._show_status(status)

    def _show_status(self, status=None):
        status = status or self.engine.status
        parts = [f"<b>{cid}</b> ({self.engine.cockpit.cards[cid].product}) : "
                 f"<span style='color:{'#4c4' if st.startswith('connectée') else '#e55'}'>{st}</span>"
                 for cid, st in status.items()]
        if self.engine.cockpit.sim:
            ok = self.engine.sim_connected
            parts.append("<b>X-Plane</b> : " + (
                "<span style='color:#4c4'>connecté</span>" if ok else
                "<span style='color:#e55'>en attente (lancez X-Plane)</span>"))
        self.cards_label.setText(" &nbsp; ".join(parts))

    def _step(self):
        if not self.engine:
            return
        was = self.engine.sim_connected
        changes = self.engine.step()
        if self.engine.sim_connected != was:
            self._log("X-Plane " + ("connecté" if self.engine.sim_connected else "perdu"))
            self._show_status()
        for ch in changes:
            w = self.widgets.get((ch.instrument, ch.control))
            alert = getattr(getattr(w, "ctrl", None), "alert", None)
            if alert:
                self._log(f"⚠ {ch.instrument}.{ch.control} : {alert}")
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
    path = sys.argv[1] if len(sys.argv) > 1 else "config/avions/rj85-simule"
    win = PanelWindow(path)
    win.show()
    return app.exec()
