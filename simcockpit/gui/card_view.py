"""Vue d'une carte : grille des entrées, axes, sorties, journal."""

import queue
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QProgressBar, QPushButton, QSpinBox,
                               QVBoxLayout,
                               QWidget)

from ..hw import dme, mastercard, mcp, usbfmc
from ..hw.device import Card

ACTIVE = "#2e9e44"       # vert : entrée actionnée
REST = "#3a3f47"         # gris : repos
RECENT = "#f0a020"       # orange : vient de changer
OUT_ON = "#d03030"
OUT_OFF = "#3a3f47"
# Délai entre deux trames écrites : le MCP ignore les trames trop rapprochées
# (10 ms : seules les dernières sont prises ; 50 ms : toutes le sont).
WRITE_GAP = 0.06


class Cell(QLabel):
    def __init__(self, text, size=34):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(size, size)
        self.set_colors(REST)

    def set_colors(self, bg, border=None):
        border = border or bg
        self.setStyleSheet(f"background:{bg}; color:white; font-weight:bold;"
                           f" border:3px solid {border}; border-radius:4px;")


class OutputCell(QPushButton):
    def __init__(self, number):
        super().__init__(str(number))
        self.number = number
        self.on = False
        self.setFixedSize(34, 34)
        self.refresh()

    def refresh(self):
        bg = OUT_ON if self.on else OUT_OFF
        self.setStyleSheet(f"background:{bg}; color:white; font-weight:bold; border-radius:4px;")


class CardView(QWidget):
    # une commande de la carte vient d'être actionnée (entrée ou touche ; pas les axes)
    activity = Signal()

    def __init__(self, detected, parent=None):
        super().__init__(parent)
        self.detected = detected
        self.card = Card(detected.info, detected.type, debounce=0.03,
                         raw_events=not detected.known)
        self.state = [None] * mastercard.INPUTS
        self.changed_at = [0.0] * mastercard.INPUTS
        self.counts = [0] * mastercard.INPUTS
        self.out_bits = {}  # segment -> octet
        self.cells, self.out_cells = [], []
        self._last_raw, self._raw_count = None, 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        if not detected.known:
            self._build_passive()
            return

        root = QVBoxLayout(self)

        self.last = QLabel("Appuyez sur une touche…" if detected.type.protocol == "keys"
                           else "Actionnez un bouton du panneau…")
        self.last.setAlignment(Qt.AlignCenter)
        self.last.setStyleSheet("font-size:22px; font-weight:bold; padding:8px;")
        root.addWidget(self.last)

        top = QHBoxLayout()
        root.addLayout(top, 1)

        # --- entrées
        box = QGroupBox("Entrées (numéros SIOC) — vert = actionnée, orange = vient de changer")
        grid = QGridLayout(box)
        grid.setSpacing(4)
        self.cells = []
        # Master/EFDE : 8 groupes de 9 entrées ; MCP (bitmap) : 8 octets de 8 bits
        per_row, row_name = (8, "octet") if detected.type.protocol == "bitmap" else (9, "groupe")
        n_inputs = 0 if detected.type.protocol == "keys" else min(detected.type.inputs,
                                                                   mastercard.INPUTS)
        for row in range(-(-n_inputs // per_row)):
            is_dme = detected.type.protocol == "dme"
            grid.addWidget(QLabel("SEL, PWR" if is_dme else f"{row_name} {row}"), row, 0)
            for b in range(min(per_row, n_inputs - per_row * row)):
                i = per_row * row + b
                cell = Cell(str(i))
                cell.setToolTip(f"Entrée {i} ({row_name} {row}, bit {b})")
                grid.addWidget(cell, row, b + 1)
                self.cells.append(cell)
        if detected.type.protocol == "dme":
            box.setTitle("Boutons : entrée 0 = SEL, entrée 1 = PWR")
        if detected.type.protocol == "keys":
            box = self._build_keys()
        top.addWidget(box)

        side = QVBoxLayout()
        top.addLayout(side)

        # --- axes
        abox = QGroupBox("Entrées analogiques")
        alay = QGridLayout(abox)
        self.axes = {}
        for n in range(1, detected.type.axes + 1):
            bar = QProgressBar()
            bar.setRange(0, 255)
            bar.setFormat("%v")
            alay.addWidget(QLabel(f"#{n}"), n, 0)
            alay.addWidget(bar, n, 1)
            self.axes[n] = bar
        side.addWidget(abox)
        abox.setVisible(detected.type.axes > 0)

        # --- sorties (verrouillées)
        obox = QGroupBox("Sorties (numéros SIOC)")
        olay = QVBoxLayout(obox)
        self.allow = QCheckBox("Autoriser l'écriture (sorties et afficheurs)")
        self.allow.setToolTip("Codage non vérifié sur votre carte : ne cochez que si des LED"
                              " (avec résistance) sont branchées.")
        self.allow.toggled.connect(self._allow_outputs)
        olay.addWidget(self.allow)
        self.single = QCheckBox("Une seule sortie à la fois (éteint les autres à chaque clic)")
        self.single.setChecked(True)
        olay.addWidget(self.single)
        brow = QHBoxLayout()
        self.all_on = QPushButton("Tout allumer")
        self.all_off = QPushButton("Tout éteindre")
        for btn, on in ((self.all_on, True), (self.all_off, False)):
            btn.setEnabled(False)
            btn.clicked.connect(lambda _=False, on=on: self._set_all(on))
            brow.addWidget(btn)
        brow.addStretch()
        olay.addLayout(brow)
        og = QGridLayout()
        self.out_cells = []
        for k in range(detected.type.outputs):
            n = mastercard.FIRST_OUTPUT + k
            c = OutputCell(n)
            c.setEnabled(False)
            c.clicked.connect(lambda _=False, c=c: self._toggle_output(c))
            og.addWidget(c, k // 8, k % 8)
            self.out_cells.append(c)
        olay.addLayout(og)
        side.addWidget(obox)
        obox.setVisible(detected.type.outputs > 0)

        # --- afficheurs 7 segments (exploration)
        dbox = QGroupBox("Afficheurs — trouver quelle position correspond à quel chiffre")
        dlay = QVBoxLayout(dbox)
        help_ = QLabel("1) Effacer tout  2) Motif « unités » : notez les chiffres lus"
                       "  3) Motif « dizaines » : notez à nouveau.\nPosition d'un chiffre ="
                       " dizaines × 10 + unités.")
        help_.setWordWrap(True)
        dlay.addWidget(help_)
        row = QHBoxLayout()
        self.disp_btns = []
        n = detected.type.displays
        for text, fn in (("Effacer tout", lambda: {p: mastercard.BLANK for p in range(n)}),
                         ("Motif unités", lambda: {p: p % 10 for p in range(n)}),
                         ("Motif dizaines", lambda: {p: p // 10 for p in range(n)}),
                         ("Tout à 8", lambda: {p: 8 for p in range(n)})):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, fn=fn, text=text: self._send_digits(fn(), text))
            row.addWidget(b)
            self.disp_btns.append(b)
        dlay.addLayout(row)
        one = QHBoxLayout()
        one.addWidget(QLabel("Position"))
        self.disp_pos = QSpinBox()
        self.disp_pos.setRange(0, max(n - 1, 0))
        one.addWidget(self.disp_pos)
        one.addWidget(QLabel("valeur"))
        self.disp_val = QSpinBox()
        self.disp_val.setRange(0, 10)
        self.disp_val.setSpecialValueText("")
        self.disp_val.setToolTip("0-9 ; 10 = éteint")
        one.addWidget(self.disp_val)
        b = QPushButton("Envoyer ce chiffre")
        b.clicked.connect(lambda: self._send_digits(
            {self.disp_pos.value(): self.disp_val.value()},
            f"position {self.disp_pos.value()} = {self.disp_val.value()}"))
        one.addWidget(b)
        self.disp_btns.append(b)
        one.addStretch()
        dlay.addLayout(one)
        for b in self.disp_btns:
            b.setEnabled(False)
        side.addWidget(dbox)
        dbox.setVisible(n > 0)

        # --- sorties spécifiques du MCP OpenCockpits (afficheurs + LED nommés)
        self.mcp_out = None
        if detected.type.out_protocol == "mcp":
            self.mcp_out = mcp.McpOutputs()
            mbox = QGroupBox("Afficheurs et voyants du MCP")
            mlay = QVBoxLayout(mbox)
            dgrid = QGridLayout()
            self.mcp_fields = {}
            for k, name in enumerate(mcp.DISPLAYS):
                field = QLineEdit()
                field.setPlaceholderText(f"{len(mcp.DISPLAYS[name])} chiffres max")
                field.setMaxLength(len(mcp.DISPLAYS[name]))
                field.returnPressed.connect(self._send_mcp_displays)
                dgrid.addWidget(QLabel(name), k // 3 * 2, k % 3)
                dgrid.addWidget(field, k // 3 * 2 + 1, k % 3)
                self.mcp_fields[name] = field
            mlay.addLayout(dgrid)
            b = QPushButton("Afficher (ou touche Entrée dans un champ)")
            b.clicked.connect(self._send_mcp_displays)
            mlay.addWidget(b)
            lgrid = QGridLayout()
            self.mcp_leds = {}
            for k, name in enumerate(mcp.LEDS):
                lb = QPushButton(name)
                lb.setCheckable(True)
                lb.setStyleSheet("QPushButton:checked { background:#2e9e44; color:white;"
                                 " font-weight:bold; }")
                lb.toggled.connect(lambda on, name=name: self._toggle_mcp_led(name, on))
                lgrid.addWidget(lb, k // 5, k % 5)
                self.mcp_leds[name] = lb
            mlay.addLayout(lgrid)
            row = QHBoxLayout()
            for text, on in (("Toutes les LED", True), ("Aucune LED", False)):
                bb = QPushButton(text)
                bb.clicked.connect(lambda _=False, on=on: self._all_mcp_leds(on))
                row.addWidget(bb)
            row.addStretch()
            mlay.addLayout(row)
            note = QLabel("Les afficheurs ne restent allumés que tant que cette fenêtre lit la carte.")
            note.setStyleSheet("color:#999;")
            mlay.addWidget(note)
            side.addWidget(mbox)

        if detected.type.out_protocol == "dme":
            side.addWidget(self._build_dme())
        if detected.type.out_protocol == "usbfmc":
            side.addWidget(self._build_fmc_leds())

        # --- journal
        side.addWidget(QLabel("Journal"))
        self.log = QListWidget()
        side.addWidget(self.log, 1)

        self.status = QLabel()
        root.addWidget(self.status)

    def _build_keys(self):
        """Touches du CDU, groupées comme sur la façade ; une touche appuyée passe au vert."""
        box = QGroupBox("Touches du CDU — vert = vient d'être appuyée (la carte n'envoie"
                        " rien au relâchement)")
        lay = QVBoxLayout(box)
        self.key_cells, self.key_pressed_at = {}, {}
        codes = {name: code for code, name in usbfmc.KEYS.items()}
        for title, names in usbfmc.LAYOUT.items():
            lay.addWidget(QLabel(f"<b>{title}</b>"))
            grid = QGridLayout()
            grid.setSpacing(4)
            per_row = 6 if title.startswith("Lignes") else 10
            for k, name in enumerate(names):
                cell = QLabel(name)
                cell.setAlignment(Qt.AlignCenter)
                cell.setMinimumSize(44, 30)
                cell.setWordWrap(True)
                cell.setToolTip(f"{name} : touche n° {codes[name]}")
                grid.addWidget(cell, k // per_row, k % per_row)
                self.key_cells[codes[name]] = cell
                self._paint_key(codes[name], False)
            lay.addLayout(grid)
        lay.addStretch()
        return box

    def _paint_key(self, code, pressed):
        bg = ACTIVE if pressed else REST
        self.key_cells[code].setStyleSheet(f"background:{bg}; color:white; font-weight:bold;"
                                           " border-radius:4px; font-size:11px;")

    def _build_fmc_leds(self):
        box = QGroupBox("Voyants du CDU")
        lay = QHBoxLayout(box)
        self.fmc_leds = {}
        colors = {"EXEC": "#2e9e44", "DSPY": "#c62828", "FAIL": "#c62828"}
        for name in usbfmc.LEDS:
            b = QPushButton(name)
            b.setCheckable(True)
            b.setStyleSheet(f"QPushButton:checked {{ background:{colors.get(name, '#e0a020')};"
                            " color:white; font-weight:bold; }")
            b.toggled.connect(self._send_fmc_leds)
            lay.addWidget(b)
            self.fmc_leds[name] = b
        lay.addStretch()
        return box

    def _send_fmc_leds(self, *_):
        lit = [n for n, b in self.fmc_leds.items() if b.isChecked()]
        try:
            self._write(usbfmc.led_frame(lit))
        except OSError as e:
            self._log(f"ERREUR écriture : {e}")
            return
        self._log(f"CDU voyants : {', '.join(lit) or 'aucun'}")

    def _build_dme(self):
        """Écran et voyants du DME EFDE."""
        self.dme_out = dme.DmeOutputs()
        box = QGroupBox("Écran et voyants du DME")
        lay = QVBoxLayout(box)
        form = QGridLayout()
        self.dme_dist = QLineEdit()
        self.dme_dist.setPlaceholderText("ex. 3.2 (NM)")
        self.dme_right = QLineEdit()
        self.dme_right.setMaxLength(4)
        self.dme_right.setPlaceholderText("ex. LIL (4 car.)")
        for f in (self.dme_dist, self.dme_right):
            f.returnPressed.connect(self._send_dme_texts)
        form.addWidget(QLabel("Distance (NM)"), 0, 0)
        form.addWidget(self.dme_dist, 0, 1)
        form.addWidget(QLabel("Texte à droite"), 1, 0)
        form.addWidget(self.dme_right, 1, 1)
        b = QPushButton("Afficher")
        b.clicked.connect(self._send_dme_texts)
        form.addWidget(b, 0, 2, 2, 1)
        lay.addLayout(form)

        titles = {"canal": "Voyant", "unite_gauche": "Sous la distance",
                  "unite_droite": "Sous le texte"}
        self.dme_groups = {}
        for group, (_, _, values) in dme.ANNUNCIATORS.items():
            row = QHBoxLayout()
            row.addWidget(QLabel(titles[group]))
            buttons = []
            for label in values:
                lb = QPushButton(label)
                lb.setCheckable(True)
                lb.setStyleSheet("QPushButton:checked { background:#2e9e44; color:white;"
                                 " font-weight:bold; }")
                lb.clicked.connect(lambda on, g=group, l=label: self._set_dme_annunciator(
                    g, l if on else None))
                row.addWidget(lb)
                buttons.append(lb)
            row.addStretch()
            lay.addLayout(row)
            self.dme_groups[group] = buttons

        row = QHBoxLayout()
        row.addWidget(QLabel("Rétroéclairage"))
        self.dme_auto = QCheckBox("cellule photo")
        self.dme_auto.setChecked(True)
        self.dme_level = QSpinBox()
        self.dme_level.setRange(1, 255)
        self.dme_level.setValue(255)
        self.dme_level.setEnabled(False)
        self.dme_auto.toggled.connect(lambda on: (self.dme_level.setEnabled(not on),
                                                  self._send_dme_backlight()))
        self.dme_level.valueChanged.connect(self._send_dme_backlight)
        row.addWidget(self.dme_auto)
        row.addWidget(self.dme_level)
        row.addStretch()
        lay.addLayout(row)

        row = QHBoxLayout()
        for text, fn in (("Effacer l'écran", self._dme_clear),
                         ("Éteindre le DME", lambda: self._dme_cmd(dme.OFF, "DME éteint")),
                         ("Allumer (test des segments)",
                          lambda: self._dme_cmd(dme.ON, "DME allumé")),
                         ("Exemple : 3.2 NM LIL", self._dme_demo)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        return box

    def _dme_send(self, frames, what):
        try:
            for f in frames:
                self._write(f)
        except (OSError, ValueError) as e:
            self._log(f"DME : {e}")
            return False
        self._log(f"DME : {what}")
        return True

    def _send_dme_texts(self):
        text = self.dme_dist.text().strip().replace(",", ".")
        try:
            dist = float(text) if text else None
            frames = [dme.distance(dist)] if dist is not None else []
            frames.append(dme.right_text(self.dme_right.text()))
        except ValueError as e:
            self._log(f"DME : {e}")
            return
        if self._dme_send(frames, f"distance {text or '-'}, texte « {self.dme_right.text()} »"):
            self.dme_out.distance, self.dme_out.right = dist, self.dme_right.text()

    def _set_dme_annunciator(self, group, label):
        for b in self.dme_groups[group]:
            b.setChecked(b.text() == label)
        if self._dme_send([dme.annunciator(group, label)], f"{group} = {label or 'éteint'}"):
            self.dme_out.lit[group] = label

    def _send_dme_backlight(self):
        level = None if self.dme_auto.isChecked() else self.dme_level.value()
        if self._dme_send([dme.backlight(level)],
                          f"rétroéclairage {'cellule photo' if level is None else level}"):
            self.dme_out.backlight = level

    def _dme_cmd(self, function, what):
        self._dme_send([dme.command(function)], what)

    def _dme_clear(self):
        if self._dme_send([dme.command(dme.CLEAR)], "écran effacé"):
            self.dme_out = dme.DmeOutputs()
            for buttons in self.dme_groups.values():
                for b in buttons:
                    b.setChecked(False)

    def _dme_demo(self):
        self.dme_dist.setText("3.2")
        self.dme_right.setText("LIL")
        self._dme_clear()
        self._send_dme_texts()
        for group, label in (("canal", "1"), ("unite_gauche", "NM"), ("unite_droite", "ID")):
            self._set_dme_annunciator(group, label)

    def _build_passive(self):
        """Carte d'un fabricant connu mais modèle non pris en charge : trames brutes seulement."""
        root = QVBoxLayout(self)
        info = self.detected.info
        msg = QLabel(
            f"<h3>{self.detected.label}</h3>"
            f"<p>Produit « {info.product} » de {info.manufacturer}, port {info.usb_port},"
            f" {info.path}.</p><p>Ce modèle n'est pas encore pris en charge : la carte est"
            f" ouverte en <b>écoute seule</b>, rien ne lui est envoyé. Les trames qu'elle émet"
            f" d'elle-même s'affichent ci-dessous (les répétitions identiques sont regroupées).</p>")
        msg.setWordWrap(True)
        root.addWidget(msg)
        self.last = QLabel("En attente de trames…")
        self.last.setStyleSheet("font-size:18px; font-weight:bold; padding:6px;")
        root.addWidget(self.last)
        self.log = QListWidget()
        root.addWidget(self.log, 1)
        self.status = QLabel()
        root.addWidget(self.status)

    # ------------------------------------------------------------------ cycle de vie
    def start(self):
        try:
            self.card.start()
        except PermissionError:
            self.status.setText(
                f"Accès refusé à {self.detected.info.path} : installez la règle udev"
                " (voir udev/99-simcockpit.rules) puis débranchez/rebranchez la carte.")
            self.status.setStyleSheet("color:#e55; font-weight:bold;")
            if not self.detected.known:
                self.last.setText("Accès refusé (règle udev manquante)")
            return
        except OSError as e:
            self.status.setText(f"Impossible d'ouvrir {self.detected.info.path} : {e}")
            return
        self.status.setText(f"{self.card.name} — {self.detected.info.path} — en attente de l'état…")
        self.timer.start(20)

    def stop(self):
        self.timer.stop()
        self.card.stop()

    # ------------------------------------------------------------------ événements
    def _poll(self):
        now = time.monotonic() - self.card.t0
        while True:
            try:
                ev = self.card.events.get_nowait()
            except queue.Empty:
                break
            self.handle(ev)
        for code, t in list(getattr(self, "key_pressed_at", {}).items()):   # touche : 0,6 s en vert
            if now - t > 0.6:
                del self.key_pressed_at[code]
                self._paint_key(code, False)
        for i, cell in enumerate(self.cells):  # estompe l'orange après 1 s
            if self.changed_at[i] and now - self.changed_at[i] > 1.0:
                self.changed_at[i] = 0.0
                self._paint(i)

    def handle(self, ev):
        if ev.kind == "raw":
            hexa = ev.value.hex(" ")
            self._raw_count += 1
            self.last.setText(f"{self._raw_count} trame(s) reçue(s) — dernière : {hexa}")
            if hexa == self._last_raw and self.log.count():
                n = getattr(self, "_repeat", 1) + 1
                self._repeat = n
                self.log.item(0).setText(f"{ev.t:8.3f} s   RX {hexa}   (×{n})")
            else:
                self._last_raw, self._repeat = hexa, 1
                self._log(f"{ev.t:8.3f} s   RX {hexa}")
            return
        if ev.kind == "key":
            self.activity.emit()
            self.last.setText(f"Touche {ev.value}  (n° {ev.index})")
            self._log(f"{ev.t:8.2f} s   touche {ev.value} (n° {ev.index})")
            if ev.index in self.key_cells:
                self.key_pressed_at[ev.index] = ev.t
                self._paint_key(ev.index, True)
            return
        if ev.kind == "ready":
            self.state = list(ev.value)
            for i in range(len(self.cells)):
                self._paint(i)
            act = [i for i, v in enumerate(self.state) if self.card.is_active(v)]
            self.status.setText(f"{self.card.name} — {self.detected.info.path} — prête."
                                f" Actionnées au repos : {act or 'aucune'}")
        elif ev.kind == "input":
            self.activity.emit()
            self.state[ev.index] = ev.value
            self.changed_at[ev.index] = ev.t
            active = self.card.is_active(ev.value)
            if active:
                self.counts[ev.index] += 1
            self._paint(ev.index)
            verb = "ACTIONNÉE" if active else "relâchée"
            self.last.setText(f"Entrée {ev.index} {verb}")
            self._log(f"{ev.t:8.2f} s   entrée {ev.index:2d} {verb}")
        elif ev.kind == "axis" and ev.index in self.axes:
            self.axes[ev.index].setValue(ev.value)
        elif ev.kind == "error":
            self.timer.stop()
            self.status.setText(f"Carte perdue ({ev.value}). Rebranchez puis « Rechercher ».")
            self._log(f"ERREUR : {ev.value}")

    def _paint(self, i):
        v = self.state[i]
        bg = ACTIVE if (v is not None and self.card.is_active(v)) else REST
        self.cells[i].set_colors(bg, RECENT if self.changed_at[i] else None)
        n = self.counts[i]
        self.cells[i].setToolTip(f"Entrée {i} — actionnée {n} fois")

    def _log(self, text):
        self.log.insertItem(0, text)
        if self.log.count() > 300:
            self.log.takeItem(300)

    # ------------------------------------------------------------------ sorties
    def _allow_outputs(self, on):
        for c in self.out_cells + [self.all_on, self.all_off] + self.disp_btns:
            c.setEnabled(on)

    def _write(self, report):
        """Écrit une trame en respectant WRITE_GAP depuis la précédente."""
        wait = getattr(self, "_last_write", 0.0) + WRITE_GAP - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.card.write(report)
        self._last_write = time.monotonic()

    def _send_mcp_displays(self):
        try:
            for name, field in self.mcp_fields.items():
                text = field.text().strip()
                value = int(text) if text.lstrip("-").isdigit() else (text or None)
                self.mcp_out.set_display(name, value)
        except ValueError as e:
            self._log(f"afficheur : {e}")
            return
        try:
            for f in self.mcp_out.display_frames():
                self._write(f)
        except OSError as e:
            self._log(f"ERREUR écriture : {e}")
            return
        self._log("MCP afficheurs : " + "  ".join(
            f"{n}={f.text() or '-'}" for n, f in self.mcp_fields.items()))

    def _toggle_mcp_led(self, name, on):
        self.mcp_out.set_led(name, on)
        try:
            self._write(self.mcp_out.led_frame())
        except OSError as e:
            self._log(f"ERREUR écriture : {e}")
            return
        self._log(f"MCP voyant {name} -> {'allumé' if on else 'éteint'}")

    def _all_mcp_leds(self, on):
        for name, b in self.mcp_leds.items():
            b.blockSignals(True)
            b.setChecked(on)
            b.blockSignals(False)
            self.mcp_out.set_led(name, on)
        try:
            self._write(self.mcp_out.led_frame())
        except OSError as e:
            self._log(f"ERREUR écriture : {e}")
        self._log(f"MCP : toutes les LED {'allumées' if on else 'éteintes'}")

    def _send_digits(self, digits, what):
        try:
            for rep in mastercard.display_reports(digits, ndisplays=self.detected.type.displays):
                self._write(rep)
        except OSError as e:
            self._log(f"ERREUR écriture : {e}")
            return
        self._log(f"afficheurs : {what}")

    def _set_all(self, on, quiet=False):
        """Met toutes les sorties de la carte à 1 (on) ou à 0, un rapport par segment."""
        segments = {}
        for c in self.out_cells:
            c.on = on
            c.refresh()
            seg, bit = mastercard.output_location(c.number)
            segments[seg] = segments.get(seg, 0) | ((1 << bit) if on else 0)
        for seg, bits in sorted(segments.items()):
            self.out_bits[seg] = bits
            try:
                self._write(mastercard.output_report(seg, bits))
            except OSError as e:
                self._log(f"ERREUR écriture : {e}")
                return
        if not quiet:
            self._log(f"toutes les sorties -> {int(on)}  (segments {sorted(segments)})")

    def _toggle_output(self, cell):
        seg, bit = mastercard.output_location(cell.number)
        turn_on = not cell.on
        if self.single.isChecked():
            self._set_all(False, quiet=True)   # repart de tout éteint
        cell.on = turn_on
        bits = self.out_bits.get(seg, 0)
        bits = bits | (1 << bit) if cell.on else bits & ~(1 << bit)
        self.out_bits[seg] = bits
        try:
            self._write(mastercard.output_report(seg, bits))
        except OSError as e:
            self._log(f"ERREUR écriture : {e}")
        cell.refresh()
        self._log(f"sortie {cell.number} -> {int(cell.on)}  (segment {seg} = {bits:08b})")
