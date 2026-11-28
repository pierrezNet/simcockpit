"""Onglet du bus FDBUS (jauges EFDE) : une colonne par jauge branchée.

Rien n'est figé : le nom et l'unité de chaque jauge, comme l'étalonnage de son cadran, se
règlent ici et sont gardés dans config/fdbus.yaml (voir hw/fdbus.Calibration).
"""

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QGridLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget, QMessageBox,
                               QPushButton, QScrollArea, QSlider, QSpinBox, QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from ..hw import fdbus

GREY = "color:#999;"
WARN = "#e05050"
PER_ROW = 3          # jauges par rangée
SHORTCUTS_PER_ROW = 6


def format_value(value, unit):
    """−3350 ft/min, 18°, 1 200 tr/min… (signe moins typographique, milliers espacés)."""
    if abs(value) >= 1000:
        text = f"{abs(value):,.0f}".replace(",", " ")
    elif abs(value - round(value)) < 0.05:
        text = f"{abs(value):.0f}"
    else:
        text = f"{abs(value):.1f}".replace(".", ",")
    if round(value, 1) < 0:
        text = "−" + text
    sep = "" if unit.startswith(("°", "%")) else " "
    return f"{text}{sep}{unit}" if unit else text


def clear_layout(layout):
    """Retire et détruit les widgets d'une grille (masqués tout de suite : deleteLater
    n'agit qu'au tour suivant de la boucle d'événements)."""
    while layout.count():
        w = layout.takeAt(0).widget()
        if w:
            w.hide()
            w.setParent(None)
            w.deleteLater()


class Section(QWidget):
    """Section repliable : titre à flèche, contenu masqué par défaut."""

    def __init__(self, title, content, opened=False):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.button = QToolButton()
        self.button.setCheckable(True)
        self.button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.button.setStyleSheet("QToolButton { border:none; font-weight:bold; }")
        self.button.toggled.connect(self._toggle)
        self.content = content
        lay.addWidget(self.button)
        lay.addWidget(content)
        self.set_title(title)
        self.button.setChecked(opened)
        self._toggle(opened)

    def set_title(self, title, warn=False):
        self.button.setText(title)
        self.button.setStyleSheet("QToolButton { border:none; font-weight:bold;"
                                  f"{f' color:{WARN};' if warn else ''} }}")

    def _toggle(self, on):
        self.button.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self.content.setVisible(on)


class GaugePanel(QGroupBox):
    """Une sortie de module : la jauge, sa valeur au cadran, ses réglages."""

    def __init__(self, view, module, channel=1):
        super().__init__()
        self.view, self.m, self.ch = view, module, channel
        self.foreign = view.foreign_calibration(module, channel)
        self.cal = view.calibration(module, channel)
        lo, hi = module.limits(channel)
        lay = QVBoxLayout(self)

        self.title = QLabel()
        self.title.setStyleSheet("font-size:17px; font-weight:bold;")
        lay.addWidget(self.title)
        sub = QLabel(f"module {module.address} · sortie {channel} · {module.type_label}")
        sub.setStyleSheet(GREY)
        lay.addWidget(sub)
        self.big = QLabel("—")
        self.big.setAlignment(Qt.AlignCenter)
        self.big.setStyleSheet("font-size:34px; font-weight:bold; padding:6px;")
        lay.addWidget(self.big)
        self.raw = QLabel()
        self.raw.setAlignment(Qt.AlignCenter)
        self.raw.setStyleSheet(GREY)
        lay.addWidget(self.raw)

        row = QHBoxLayout()
        row.addWidget(QLabel("Valeur au cadran"))
        self.target = QSpinBox()
        self.target.setRange(-100000, 100000)
        self.target.lineEdit().returnPressed.connect(self._go)
        row.addWidget(self.target, 1)
        self.go = QPushButton("Placer l'aiguille")
        self.go.clicked.connect(self._go)
        row.addWidget(self.go)
        lay.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Position moteur"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(lo, hi)
        self.spin = QSpinBox()
        self.spin.setRange(lo, hi)
        rest = self.rest_position()
        for w in (self.slider, self.spin):
            w.blockSignals(True)
            w.setValue(rest)
            w.blockSignals(False)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)
        self.slider.valueChanged.connect(lambda v: view.request(module.address, v))
        row.addWidget(self.slider, 1)
        row.addWidget(self.spin)
        lay.addLayout(row)

        self.shortcuts = QGridLayout()
        self.shortcuts.setSpacing(3)
        lay.addLayout(self.shortcuts)

        self.cal_section = Section("Étalonnage", self._build_calibration())
        lay.addWidget(self.cal_section)
        self.module_section = Section("Jauge et module", self._build_settings())
        lay.addWidget(self.module_section)
        lay.addStretch()
        self.refresh()
        self.raw.setText("position non envoyée")

    # ---------------------------------------------------------------- construction
    def _build_calibration(self):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 0, 0, 0)
        self.cal_note = QLabel()
        self.cal_note.setWordWrap(True)
        lay.addWidget(self.cal_note)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Repère du cadran", "Position moteur"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMaximumHeight(220)
        self.table.cellClicked.connect(self._pick_point)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(QLabel("Repère"))
        self.mark = QSpinBox()
        self.mark.setRange(-100000, 100000)
        self.mark.setToolTip("Valeur du repère du cadran sur lequel l'aiguille est placée")
        row.addWidget(self.mark, 1)
        self.add_btn = QPushButton("Enregistrer (aiguille sur ce repère)")
        self.add_btn.clicked.connect(self._add_point)
        row.addWidget(self.add_btn)
        self.del_btn = QPushButton("Supprimer")
        self.del_btn.clicked.connect(self._remove_point)
        row.addWidget(self.del_btn)
        lay.addLayout(row)
        help_ = QLabel("Placez l'aiguille sur un repère avec « Position moteur », saisissez la"
                       " valeur du repère, puis « Enregistrer ». Deux repères au minimum ; un"
                       " clic dans le tableau reprend un repère pour le corriger.")
        help_.setWordWrap(True)
        help_.setStyleSheet(GREY)
        lay.addWidget(help_)
        return box

    def _build_settings(self):
        m = self.m
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 0, 0, 0)
        form = QGridLayout()
        hint = fdbus.FSUIPC_OFFSETS.get(m.word("Offset1"))
        self.name_edit = QLineEdit(self.cal.name)
        self.name_edit.setPlaceholderText(f"ex. {hint[0]}" if hint else "ex. volets, IVSI…")
        self.unit_edit = QLineEdit(self.cal.unit)
        self.unit_edit.setPlaceholderText(f"ex. {hint[1]}" if hint else "ex. °, ft/min, %")
        for edit in (self.name_edit, self.unit_edit):
            edit.editingFinished.connect(self._save_names)
            edit.setEnabled(not self.foreign)
        form.addWidget(QLabel("Jauge branchée"), 0, 0)
        form.addWidget(self.name_edit, 0, 1)
        form.addWidget(QLabel("Unité du cadran"), 1, 0)
        form.addWidget(self.unit_edit, 1, 1)
        lay.addLayout(form)
        factory = f" ; réglage d'usine EFDE : {m.data_label}" if m.data_label else ""
        params = QLabel(f"Paramètres du module{factory}.\n{m.params_text() or '(aucun)'}")
        params.setWordWrap(True)
        params.setStyleSheet(GREY)
        lay.addWidget(params)
        lo, hi = m.limits(self.ch)
        row = QHBoxLayout()
        for text, v in (("Mini", lo), ("Milieu", (lo + hi) // 2), ("Maxi", hi)):
            b = QPushButton(f"{text} ({v})")
            b.clicked.connect(lambda _=False, v=v: self.set_position(v))
            row.addWidget(b)
        b = QPushButton("Remise à zéro (07)")
        b.setToolTip("Commande de remise à zéro du module : le moteur X27 repart en butée.")
        b.clicked.connect(lambda: self.view.reset(m))
        row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Nouvelle adresse"))
        self.new_adr = QSpinBox()
        self.new_adr.setRange(fdbus.FIRST_ADDRESS, fdbus.LAST_ADDRESS)
        used = self.view.addresses()
        free = [a for a in range(250, fdbus.FIRST_ADDRESS - 1, -1) if a not in used]
        self.new_adr.setValue(free[0] if free else fdbus.FIRST_ADDRESS)
        row.addWidget(self.new_adr)
        b = QPushButton("Changer l'adresse du module…")
        b.setToolTip("Écrit la nouvelle adresse dans l'EEPROM du module (fonction 50)."
                     " Le strap de configuration doit être en place.")
        b.clicked.connect(lambda: self.view.change_address(m, self.new_adr.value()))
        row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        return box

    # ---------------------------------------------------------------- affichage
    def rest_position(self):
        """Position de repos : valeur 0 du cadran si la jauge est étalonnée."""
        pos = self.cal.position(0)
        return self.m.rest_position(self.ch) if pos is None else pos

    def refresh(self):
        """Titre, raccourcis et tableau d'étalonnage d'après les réglages."""
        cal = self.cal
        self.title.setText(cal.name or f"Module {self.m.address}")
        self.target.setSuffix(f" {cal.unit}" if cal.unit else "")
        self.mark.setSuffix(f" {cal.unit}" if cal.unit else "")
        ready = len(cal) >= 2
        self.target.setEnabled(ready)
        self.go.setEnabled(ready)
        clear_layout(self.shortcuts)
        for k, value in enumerate(sorted(cal.points) if ready else []):
            b = QPushButton(format_value(value, cal.unit))
            b.setToolTip(f"Place l'aiguille sur le repère {format_value(value, cal.unit)}")
            b.clicked.connect(lambda _=False, v=value: self.go_to(v))
            self.shortcuts.addWidget(b, k // SHORTCUTS_PER_ROW, k % SHORTCUTS_PER_ROW)

        bad = set(cal.incoherent())
        self.table.setRowCount(len(cal))
        for r, (value, pos) in enumerate(sorted(cal.points.items())):
            for c, text in enumerate((format_value(value, cal.unit), str(pos))):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                if value in bad:
                    item.setForeground(Qt.red)
                    item.setToolTip("Ce repère casse le sens de la courbe : la position recule"
                                    " alors que la valeur avance. Curseur mal placé ?")
                self.table.setItem(r, c, item)
        if self.foreign:
            self.cal_note.setText(
                f"L'étalonnage enregistré pour l'adresse {self.m.address} est celui d'un autre"
                f" module (type {self.foreign}) : il est conservé mais pas utilisé ici.")
            self.cal_note.setStyleSheet(f"color:{WARN};")
        elif bad:
            self.cal_note.setText(f"{len(bad)} repère(s) en rouge à vérifier.")
            self.cal_note.setStyleSheet(f"color:{WARN};")
        else:
            self.cal_note.setText("" if ready else "Pas encore étalonnée.")
            self.cal_note.setStyleSheet(GREY)
        self.cal_note.setVisible(bool(self.cal_note.text()))
        for w in (self.add_btn, self.del_btn, self.mark):
            w.setEnabled(not self.foreign)
        warn = " ⚠" if bad or self.foreign else ""
        self.cal_section.set_title(f"Étalonnage ({len(cal)} repère(s){warn})", bool(warn))
        self.shown(self.slider.value())

    def shown(self, pos):
        """Affiche la position envoyée et sa valeur au cadran."""
        value = self.cal.value(pos)
        if value is not None:
            self.big.setText(format_value(value, self.cal.unit))
        else:
            sim = self.m.to_sim(pos, self.ch)
            self.big.setText(f"{pos}" if sim is None else f"≈ {format_value(sim, '')}")
        self.raw.setText(f"position moteur {pos}")

    # ---------------------------------------------------------------- actions
    def set_position(self, pos):
        self.slider.setValue(pos)
        self.view.request(self.m.address, pos)

    def go_to(self, value):
        pos = self.cal.position(value)
        if pos is not None:
            self.target.setValue(round(value))
            self.set_position(pos)

    def _go(self):
        self.go_to(self.target.value())

    def _pick_point(self, row, _col):
        value = sorted(self.cal.points)[row]
        self.mark.setValue(round(value))
        self.set_position(self.cal.points[value])

    def _add_point(self):
        self.cal.add(self.mark.value(), self.slider.value())
        self.view.save(f"{self.title.text()} : repère {self.mark.value()} = position"
                       f" {self.slider.value()}")
        self.refresh()

    def _remove_point(self):
        if self.mark.value() in self.cal.points:
            self.cal.remove(self.mark.value())
            self.view.save(f"{self.title.text()} : repère {self.mark.value()} supprimé")
            self.refresh()

    def _save_names(self):
        name, unit = self.name_edit.text().strip(), self.unit_edit.text().strip()
        if (name, unit) == (self.cal.name, self.cal.unit):
            return
        self.cal.name, self.cal.unit = name, unit
        self.view.save(f"module {self.m.address} : jauge « {name or '-'} », unité"
                       f" « {unit or '-'} »")
        self.refresh()


class FdbusView(QWidget):
    """Contenu de l'onglet de la carte FDBUS ; reçoit les événements de la carte."""

    def __init__(self, card, parent=None):
        super().__init__(parent)
        self.card = card
        self.driven = lambda: False                # le cockpit pilote-t-il les jauges ?
        self.out = fdbus.FdbusOutputs()
        self.cals = fdbus.load_calibrations()      # (adresse, sortie) -> Calibration
        self.panels = {}                           # adresse -> GaugePanel
        self.pending = {}                          # adresse -> position à envoyer
        root = QVBoxLayout(self)
        self.last = QLabel("Initialisation du bus…")
        self.last.setStyleSheet("font-size:18px; font-weight:bold; padding:6px;")
        root.addWidget(self.last)
        bar = QHBoxLayout()
        again = QPushButton("Relancer l'initialisation")
        again.setToolTip("Explore de nouveau le bus et relit les paramètres des modules"
                         " (après avoir branché ou débranché un module).")
        again.clicked.connect(self.reinit)
        bar.addWidget(again)
        bar.addSpacing(20)
        bar.addWidget(QLabel("Rétroéclairage (non vérifié)"))
        self.light = QSpinBox()
        self.light.setRange(0, 15)
        self.light.setValue(15)
        bar.addWidget(self.light)
        b = QPushButton("Envoyer")
        b.clicked.connect(self._backlight)
        bar.addWidget(b)
        bar.addStretch()
        root.addLayout(bar)
        self.warn = QLabel()
        self.warn.setWordWrap(True)
        self.warn.setStyleSheet(f"color:{WARN}; font-weight:bold;")
        self.warn.hide()
        root.addWidget(self.warn)
        holder = QWidget()
        self.grid = QGridLayout(holder)
        self.grid.setAlignment(Qt.AlignTop)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        root.addWidget(scroll, 1)
        self.log = QListWidget()
        self.log.setMinimumHeight(140)
        root.addWidget(Section("Journal", self.log))
        self.status = QLabel()
        root.addWidget(self.status)
        # les positions partent au plus toutes les 50 ms (curseur déplacé à la souris)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._flush)

    # ---------------------------------------------------------------- réglages
    def foreign_calibration(self, m, ch):
        """Type du module étalonné à cette adresse s'il diffère de `m`, sinon None."""
        cal = self.cals.get((m.address, ch))
        if cal is not None and cal.module_type not in (None, m.type) and not cal.empty():
            return cal.module_type
        return None

    def calibration(self, m, ch):
        if self.foreign_calibration(m, ch):
            return fdbus.Calibration(module_type=m.type)    # copie vide, jamais enregistrée
        cal = self.cals.setdefault((m.address, ch), fdbus.Calibration(module_type=m.type))
        cal.module_type = m.type
        return cal

    def save(self, what):
        try:
            fdbus.save_calibrations(self.cals)
        except OSError as e:
            self.log_line(f"ERREUR enregistrement : {e}")
            return
        self.log_line(f"{what} (config/fdbus.yaml)")

    def addresses(self):
        return {m.address for m in self.card.fdbus.modules} if self.card.fdbus else set()

    # ---------------------------------------------------------------- événements
    def log_line(self, text):
        self.log.insertItem(0, text)
        if self.log.count() > 300:
            self.log.takeItem(300)

    def handle(self, ev):
        if ev.kind == "log":
            self.log_line(f"{ev.t:8.2f} s   {ev.value}")
        elif ev.kind == "module":
            m = ev.value
            self.log_line(f"{ev.t:8.2f} s   module trouvé : adresse {m.address}, {m.type_label}")
        elif ev.kind == "ready":
            self._show(ev.value)
        elif ev.kind == "init_failed":
            self.last.setText(f"Initialisation échouée : {ev.value}")
            self.log_line(f"{ev.t:8.2f} s   ÉCHEC : {ev.value}")
            self.status.setText("Vérifiez le 5 V et le câble du bus, puis « Relancer"
                                " l'initialisation ».")
        elif ev.kind == "error":
            self.timer.stop()
            self.status.setText(f"Carte perdue ({ev.value}). Rebranchez puis « Rechercher ».")
            self.log_line(f"ERREUR : {ev.value}")

    def _clear(self):
        clear_layout(self.grid)
        self.panels.clear()
        self.pending.clear()
        self.warn.hide()

    def reinit(self):
        self.timer.stop()
        self._clear()
        self.out = fdbus.FdbusOutputs()
        self.last.setText("Initialisation du bus…")
        self.card.request_init()

    def _show(self, modules):
        self._clear()
        if not modules:
            self.last.setText("Aucun module sur le bus (5 V branché ?)")
            return
        self.last.setText(f"Bus prêt : {len(modules)} module(s)")
        dup = self.card.fdbus.duplicates() if self.card.fdbus else []
        if dup:
            self.warn.setText(f"Attention : adresse(s) {dup} annoncée(s) plusieurs fois. Deux"
                              " modules sur la même adresse ne peuvent pas fonctionner ensemble.")
            self.warn.show()
        for k, m in enumerate(sorted(modules, key=lambda m: m.address)):
            panel = GaugePanel(self, m)
            self.grid.addWidget(panel, k // PER_ROW, k % PER_ROW)
            self.panels[m.address] = panel
            if not self.driven():                    # aiguilles au repos, sauf si le
                self.request(m.address, panel.rest_position())   # cockpit les tient
        self.status.setText(f"{self.card.name} — {self.card.info.path} — prêt.")
        self.timer.start(50)

    # ---------------------------------------------------------------- écritures
    def request(self, adr, pos):
        self.pending[adr] = pos

    def _flush(self):
        pending, self.pending = self.pending, {}
        for adr, pos in pending.items():
            panel = self.panels.get(adr)
            if panel is None:
                continue
            frames = self.out.position(panel.m, pos)
            try:
                for k, f in enumerate(frames):
                    if k:
                        time.sleep(0.03)
                    self.card.write(f)
            except OSError as e:
                self.log_line(f"ERREUR écriture : {e}")
                return
            if frames:
                sent = self.out.sent[(adr, 1)]
                panel.shown(sent)
                self.log_line(f"{panel.title.text()} : {panel.big.text()}, position {sent}"
                              f"  (→ {frames[0][:3].hex(' ')}{' ×2' if len(frames) > 1 else ''})")

    def reset(self, m):
        try:
            for f in self.out.reset(m):
                self.card.write(f)
        except OSError as e:
            self.log_line(f"ERREUR écriture : {e}")
            return
        self.panels[m.address].raw.setText("remis à zéro (butée)")
        self.log_line(f"module {m.address} : remise à zéro (→ 07 {m.address:02x} 00)")

    def change_address(self, m, new):
        """Fonction 50, comme le bouton « Écrit EEPROM » du driver d'EFDE, mais seule :
        aucun autre paramètre du module n'est réécrit."""
        try:
            frame = fdbus.address_frame(m, new)
        except ValueError as e:
            self.log_line(f"adresse : {e}")
            return
        if new in self.addresses():
            self.log_line(f"adresse : {new} est déjà prise par un autre module")
            return
        ok = QMessageBox.question(
            self, "Changer l'adresse du module",
            f"Module {m.address} ({m.type_label}) → nouvelle adresse {new}.\n\n"
            f"Ce module doit être SEUL sur le bus à l'adresse {m.address}.\n"
            "Mettez maintenant le strap de configuration sur le module, puis cliquez sur OK.\n\n"
            f"Trame envoyée (écriture EEPROM de l'adresse seulement) : {frame[:3].hex(' ')}",
            QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        if ok != QMessageBox.Ok:
            self.log_line("changement d'adresse annulé")
            return
        try:
            self.card.write(frame)
        except OSError as e:
            self.log_line(f"ERREUR écriture : {e}")
            return
        time.sleep(0.1)   # le driver d'EFDE attend 100 ms après cette trame
        self.log_line(f"module {m.address} : nouvelle adresse {new} écrite"
                      f" (→ {frame[:3].hex(' ')})")
        QMessageBox.information(
            self, "Changer l'adresse du module",
            "Retirez le strap de configuration, puis cliquez sur OK : le bus sera de nouveau"
            " exploré. Si le module n'apparaît pas à sa nouvelle adresse, coupez et remettez"
            " l'alimentation du bus, puis « Relancer l'initialisation ».")
        self.reinit()

    def _backlight(self):
        level = self.light.value()
        try:
            for f in self.out.backlight(level):
                self.card.write(f)
        except OSError as e:
            self.log_line(f"ERREUR écriture : {e}")
            return
        self.log_line(f"rétroéclairage {level}/15 (→ 06 32 {level * 17:02x})")

    def stop(self):
        self.timer.stop()
