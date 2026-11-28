"""Page Périphériques : ce qui est branché en USB ou connecté en wifi, depuis quand, et
si Pepit y a accès.

Le veilleur (`UsbWatcher`) tourne dès le lancement de Pepit, page ouverte ou non : il
suit les branchements (hw/uevent.py), relit sysfs (hw/usb.py), relève les cartes wifi
connectées aux serveurs IOCP du cockpit (hw/network.py) et tient l'historique.
La page ne fait qu'afficher ce qu'il a relevé.
"""

import time

from PySide6.QtCore import QObject, QProcess, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView, QLabel,
                               QListWidget, QMainWindow, QMessageBox, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ..hw import authorize, usb
from ..hw.uevent import UeventMonitor
from .winstate import remember

SETTLE = 400         # ms sans événement avant de relire (un branchement en produit une rafale)
ACL_DELAY = 2000     # ms : udev pose les droits un peu après le noyau, on relit encore
NETWORK_POLL = 2000  # ms : relevé des cartes wifi connectées

# pastille : état -> (couleur, texte)
STATES = {"ok": ("#2e9e44", "accessible"), "partiel": ("#f0a020", "accès partiel"),
          "refusé": ("#e05555", "accès refusé"), "": ("#7b8a92", "branché (pas de nœud utile)"),
          "absent": ("#4a5257", "débranché")}
COLUMNS = ["", "Périphérique", "Accès", "Pour Pepit", "VID:PID", "Port", "Vitesse", "Courant",
           "Branché", "Première fois", "Dernière fois", "Nœuds (✓ accessible)"]
# cartes wifi : état -> (couleur, texte)
NET_STATES = {"ok": ("#2e9e44", "connectée, sert le profil chargé"),
              "inconnue": ("#f0a020", "connectée, mais le profil chargé ne la déclare pas"),
              "absent": ("#4a5257", "déconnectée")}
NET_COLUMNS = ["", "Carte", "Sert (profil chargé)", "Variables IOCP", "Adresse IP", "Adresse MAC",
               "Fabricant", "Connectée", "Première fois", "Dernière fois"]


class UsbWatcher(QObject):
    """Relevés USB et historique, en tâche de fond. `updated(changes)` après chaque relevé."""

    updated = Signal(list)
    _poke = Signal()                     # depuis le fil de surveillance

    def __init__(self, history=None, parent=None):
        super().__init__(parent)
        self.history = history if history is not None else usb.History()
        self.devices = []
        self.net_devices = []            # cartes wifi connectées (network.NetDevice)
        self.iocp_ports = []             # ports des serveurs IOCP ouverts par le cockpit
        # () -> (cartes wifi, ports) : fourni par l'application (moteur du cockpit)
        self.network_source = None
        self._net = QTimer(self, interval=NETWORK_POLL, timeout=self.refresh_network)
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
        self._net.start()
        return self

    def stop(self):
        self._net.stop()
        self.monitor.stop()

    def _after_event(self):
        self.refresh()
        self._acl.start()

    def refresh(self):
        self.devices = usb.scan()
        changes = self.history.update(self.devices, "usb")
        self.updated.emit(changes)

    def refresh_network(self):
        devices, ports = self.network_source() if self.network_source else ([], [])
        self.net_devices, self.iocp_ports = devices, ports
        changes = self.history.update(devices, "wifi")
        self.updated.emit(changes)


def _table(columns):
    t = QTableWidget(0, len(columns))
    t.setHorizontalHeaderLabels(columns)
    t.verticalHeader().hide()
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setAlternatingRowColors(True)
    head = t.horizontalHeader()
    head.setSectionResizeMode(QHeaderView.ResizeToContents)
    head.setStretchLastSection(True)
    return t


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
        self.only_cockpit = QCheckBox("Matériel de simulation seulement")
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
        self.setup_note = QLabel(
            "Le bouton « Autoriser » ouvre l'accès à un périphérique sans mot de passe. Il"
            " demande une installation unique, à lancer dans un terminal après avoir lu le"
            " script :  <b>sudo bin/pepit-installer</b>  puis relancer Pepit.")
        self.setup_note.setWordWrap(True)
        self.setup_note.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setup_note.setStyleSheet("background:#f0c040; color:#111; padding:6px;")
        self.setup_note.setVisible(not authorize.installed())
        lay.addWidget(self.setup_note)
        self.running = {}                    # vid:pid -> QProcess (autorisation en cours)

        self.table = _table(COLUMNS)
        self.net_table = _table(NET_COLUMNS)
        self.net_note = QLabel()
        self.net_note.setWordWrap(True)
        net_page = QWidget()
        nl = QVBoxLayout(net_page)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.addWidget(self.net_note)
        nl.addWidget(self.net_table, 1)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.table, "USB")
        self.tabs.addTab(net_page, "Wifi (IOCP)")
        self.tabs.setCurrentIndex(int(self.settings.value("peripheriques/onglet", 0)))
        self.tabs.currentChanged.connect(
            lambda i: self.settings.setValue("peripheriques/onglet", i))
        self.journal = QListWidget()
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.tabs)
        holder = QWidget()
        jl = QVBoxLayout(holder)
        jl.setContentsMargins(0, 0, 0, 0)
        jl.addWidget(QLabel("Journal (depuis le lancement de Pepit)"))
        jl.addWidget(self.journal)
        split.addWidget(holder)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)
        legend = QLabel("USB : " + "   ".join(f"<span style='color:{c}'>●</span> {t}"
                                            for c, t in STATES.values())
                        + "<br>Wifi : " + "   ".join(f"<span style='color:{c}'>●</span> {t}"
                                                     for c, t in NET_STATES.values()))
        lay.addWidget(legend)
        self.setCentralWidget(body)

        watcher.updated.connect(self.on_update)
        self.fill()

    # ------------------------------------------------------------ données
    def on_update(self, changes):
        for kind, seen, dev in changes:
            port = dev.port if dev is not None else (seen.ports[-1] if seen.ports else "?")
            if seen.kind == "wifi":
                verb = {"branché": "connectée", "débranché": "déconnectée"}.get(kind, kind)
                self._journal(f"wifi {verb} : {seen.name} ({port})")
                continue
            extra = f", {STATES[dev.access][1]}" if dev is not None and dev.nodes else ""
            self._journal(f"{kind} : {seen.name} (port {port}{extra})")
        self.fill()

    def rows(self, kind="usb"):
        """(Seen, périphérique ou None) à afficher : branchés d'abord, puis par nom."""
        devices = self.watcher.devices if kind == "usb" else self.watcher.net_devices
        present = {d.key: d for d in devices}
        out = []
        for key, seen in self.watcher.history.seen.items():
            if seen.kind != kind:
                continue
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
        n, w = len(self.watcher.devices), len(self.watcher.net_devices)
        mode = ("surveillance en direct" if self.watcher.live
                else "relecture chaque seconde (événements du noyau indisponibles)")
        self.summary.setText(f"{n} périphérique(s) USB branché(s), {w} carte(s) wifi"
                             f" connectée(s) — {mode}")
        self.tabs.setTabText(0, f"USB ({n})")
        self.tabs.setTabText(1, f"Wifi (IOCP) ({w})")
        self.fill_network()
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
                cells = [dot, _item(seen.name, f"{seen.name}\nclé : {dev.key}"), self._access_cell(dev),
                         _item(seen.pepit), _item(seen.vid_pid), _item(dev.port),
                         _item(dev.speed_label), _item(f"{dev.max_power} mA"),
                         _item(f"{seen.plugs} fois"), _item(seen.first), _item("maintenant"),
                         _item(nodes, tip or None)]
            else:
                ports = ", ".join(seen.ports)
                cells = [dot, _item(seen.name, f"{seen.name}\nports vus : {ports}", grey),
                         _item("", None, grey),
                         _item(seen.pepit, None, grey), _item(seen.vid_pid, None, grey),
                         _item(seen.ports[-1] if seen.ports else "", f"ports vus : {ports}", grey),
                         _item("", None, grey), _item("", None, grey),
                         _item(f"{seen.plugs} fois", None, grey), _item(seen.first, None, grey),
                         _item(seen.last, None, grey), _item("", None, grey)]
            self.table.removeCellWidget(r, 2)
            for c, it in enumerate(cells):
                self.table.setItem(r, c, it)
            if dev is not None:
                button = self._access_button(dev)
                if button is not None:
                    self.table.setCellWidget(r, 2, button)

    def fill_network(self):
        ports = self.watcher.iocp_ports
        self.net_note.setText(
            f"Cartes wifi connectées au cockpit (serveur IOCP, port {', '.join(map(str, ports))})."
            " Une carte est reconnue par son adresse MAC : son adresse IP peut changer."
            if ports else
            "Aucun serveur IOCP ouvert : le profil chargé dans la page Simulateur ne déclare pas"
            " de carte wifi. Les cartes déjà vues restent dans l'historique.")
        rows = self.rows("wifi")
        self.net_table.setRowCount(len(rows))
        for r, (seen, dev) in enumerate(rows):
            x = seen.extra
            if dev is not None:
                color, label = NET_STATES["ok" if dev.cards else "inconnue"]
                cells = [_item("●", label, color), _item(seen.name, f"clé : {dev.key}"),
                         _item(", ".join(dev.cards) or "—"), _item(x.get("variables", "")),
                         _item(dev.ip, f"ports IOCP : {dev.tcp_port}"), _item(dev.mac),
                         _item(dev.vendor), _item(f"{seen.plugs} fois"), _item(seen.first),
                         _item("maintenant")]
            else:
                grey, label = NET_STATES["absent"]
                ips = ", ".join(seen.ports)
                cells = [_item("●", label, grey), _item(seen.name, None, grey),
                         _item(x.get("cartes", ""), None, grey),
                         _item(x.get("variables", ""), None, grey),
                         _item(seen.ports[-1] if seen.ports else "", f"adresses vues : {ips}", grey),
                         _item(x.get("mac", ""), None, grey),
                         _item(x.get("fabricant", ""), None, grey),
                         _item(f"{seen.plugs} fois", None, grey), _item(seen.first, None, grey),
                         _item(seen.last, None, grey)]
            cells[0].setTextAlignment(Qt.AlignCenter)
            for c, it in enumerate(cells):
                self.net_table.setItem(r, c, it)

    # ------------------------------------------------------------ autoriser
    def _access_cell(self, dev):
        allowed = authorize.authorized().get((dev.vid.lower(), dev.pid.lower()))
        if dev.access == "ok" and allowed:
            return _item("autorisé", "Ouvert par le bouton « Autoriser » (règle udev :"
                         f" {authorize.RULES}, types : {', '.join(sorted(allowed))})")
        if dev.access == "ok":
            return _item("ouvert")
        return _item("")

    def _access_button(self, dev):
        """Bouton « Autoriser » sur une ligne dont un nœud utile est fermé."""
        if dev.access not in ("refusé", "partiel") or authorize.command(dev) is None:
            return None
        busy = dev.vid_pid in self.running
        button = QPushButton("En cours…" if busy else "Autoriser")
        kinds = ", ".join(authorize.kinds_needed(dev))
        if not authorize.installed():
            button.setEnabled(False)
            button.setToolTip("Installez d'abord l'assistant : sudo bin/pepit-installer")
        else:
            button.setEnabled(not busy)
            button.setToolTip(f"Ouvrir l'accès ({kinds}) à tous les « {dev.name} »"
                              f" ({dev.vid_pid}) pour l'utilisateur de cette session")
        button.clicked.connect(lambda _=False, d=dev: self.authorize(d))
        return button

    def authorize(self, dev):
        text = authorize.warning(dev)
        if text and QMessageBox.question(self, "Autoriser ce périphérique ?", text,
                                         QMessageBox.Yes | QMessageBox.No,
                                         QMessageBox.No) != QMessageBox.Yes:
            return
        cmd = authorize.command(dev)
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.finished.connect(lambda code, _status, d=dev, p=proc: self._authorized(d, p, code))
        proc.errorOccurred.connect(lambda _err, d=dev, p=proc: self._authorized(d, p, -1))
        self.running[dev.vid_pid] = proc
        self._journal(f"autorisation demandée : {dev.name} ({dev.vid_pid},"
                      f" {', '.join(authorize.kinds_needed(dev))})")
        proc.start(cmd[0], cmd[1:])
        self.fill()

    def _authorized(self, dev, proc, code):
        if self.running.pop(dev.vid_pid, None) is None:
            return                           # déjà traité (erreur puis fin)
        out = bytes(proc.readAll()).decode("utf-8", "replace").strip()
        if code == 0:
            self._journal(f"accès ouvert : {dev.name} ({dev.vid_pid})")
        elif code in (126, 127):             # pkexec : refus de polkit ou fenêtre fermée
            self._journal(f"autorisation refusée par le système : {dev.name} — {out}")
        else:
            self._journal(f"échec de l'autorisation ({code}) : {dev.name} — {out}")
        proc.deleteLater()
        self.watcher.refresh()
        QTimer.singleShot(1500, self.watcher.refresh)    # droits posés par udev un peu après

    def _journal(self, text):
        self.journal.insertItem(0, f"{time.strftime('%H:%M:%S')}   {text}")
