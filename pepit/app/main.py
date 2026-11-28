"""Pepit en tâche de fond : un seul processus, trois pages qu'on montre ou qu'on cache.

- Simulateur : le cockpit (logique et liaison X-Plane). Il est créé au démarrage et tourne
  même fenêtre cachée.
- Cartes : le banc de test, créé à la première demande.
- Périphériques : les périphériques USB, leur accès et leur historique. Le veilleur
  tourne dès le démarrage, pour que l'historique soit tenu même page fermée.

Fermer une fenêtre la cache ; seul « Quitter Pepit » (icône de la barre du haut) arrête
tout. Sans barre d'icônes disponible, fermer la dernière fenêtre arrête Pepit.

Lancement : python -m pepit.app --page cartes|simulateur|peripheriques [--fond] [profil]
"""

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSettings, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ..gui.peripheriques import PeripheriquesPage, UsbWatcher
from ..gui.qtenv import prepare
from ..hw.hub import DeviceHub
from ..logic.profiles import same as same_profile
from . import instance

ROOT = Path(__file__).resolve().parents[2]
ICON = ROOT / "docs" / "assets" / "favicon.svg"
PAGES = {"peripheriques": "Périphériques", "simulateur": "Simulateur", "cartes": "Cartes"}
DEFAULT_PROFILE = "config/avions/rj85-simule"


def parse(argv):
    p = argparse.ArgumentParser(prog="pepit", description="Pepit : cockpit de simulateur sous Linux")
    p.add_argument("--page", choices=sorted(PAGES), default="simulateur",
                   help="page à afficher (défaut : simulateur)")
    p.add_argument("--fond", action="store_true",
                   help="démarrer sans fenêtre (icône dans la barre du haut seulement)")
    p.add_argument("profil", nargs="?", help="dossier d'avion pour le simulateur")
    return p.parse_args(argv)


def settings():
    return QSettings("pepit", "app")


class _HideOnClose(QObject):
    """Fermer une page la cache, tant que Pepit ne s'arrête pas."""

    def __init__(self, app):
        super().__init__()
        self.app = app

    def eventFilter(self, window, event):
        if event.type() == QEvent.Close and not self.app.quitting and self.app.tray is not None:
            event.ignore()
            window.hide()
            return True
        return False


class Pepit(QObject):
    def __init__(self, app, profile=None):
        super().__init__()
        self.app = app
        self.quitting = False
        self.pages = {}
        self.hub = DeviceHub()               # chaque carte ouverte une fois, pour toutes les pages
        self.usb = UsbWatcher()              # branchements et historique, en fond
        self.usb.updated.connect(self.on_usb)
        self.usb.start()
        self.tray = self._make_tray()
        app.setQuitOnLastWindowClosed(self.tray is None)
        self._hide_filter = _HideOnClose(self)
        self.profile = profile or settings().value("profil", DEFAULT_PROFILE)
        self.page("simulateur")              # le cockpit tourne dès le démarrage

    # ------------------------------------------------------------ pages
    def page(self, name):
        window = self.pages.get(name)
        if window is None:
            if name == "simulateur":
                from ..panel.app import PanelWindow
                window = PanelWindow(self.profile, self.hub)
                window.profile_changed.connect(self._remember_profile)
                settings().setValue("profil", self.profile)
            elif name == "cartes":
                from ..gui.app import MainWindow
                window = MainWindow(self.hub)
            else:
                window = PeripheriquesPage(self.usb)
            window.installEventFilter(self._hide_filter)
            self.pages[name] = window
        return window

    def show(self, name, profile=None):
        window = self.page(name)
        if name == "simulateur" and profile and not same_profile(profile, window.path):
            window.set_profile(profile)              # → _remember_profile
        window.show()
        window.setWindowState(window.windowState() & ~Qt.WindowMinimized)
        window.raise_()
        window.activateWindow()

    def _remember_profile(self, path):
        self.profile = path
        settings().setValue("profil", path)

    def launch_xplane(self):
        self.page("simulateur").launch_xplane()

    def on_message(self, line):
        """Message d'un autre lanceur : « afficher<TAB>page[<TAB>profil] »."""
        fields = instance.decode(line)
        if len(fields) >= 2 and fields[0] == "afficher" and fields[1] in PAGES:
            self.show(fields[1], fields[2] if len(fields) > 2 else None)

    def on_usb(self, changes):
        """Branchement d'une carte de cockpit : la page Cartes se met à jour, et une
        bulle prévient si Pepit n'y a pas accès."""
        cockpit = [(kind, seen, dev) for kind, seen, dev in changes if seen.cockpit]
        if not cockpit:
            return
        if "cartes" in self.pages and any(k != "accès" for k, _s, _d in cockpit):
            self.pages["cartes"].rescan()
        refused = [seen.name for kind, seen, dev in cockpit
                   if dev is not None and dev.access in ("refusé", "partiel")]
        if refused and self.tray is not None:
            self.tray.showMessage("Pepit", f"Accès refusé : {', '.join(refused)}."
                                  " Voir la page Périphériques.", QSystemTrayIcon.Warning, 8000)

    # ------------------------------------------------------------ barre du haut
    def _make_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QSystemTrayIcon(QIcon(str(ICON)), self)
        tray.setToolTip("Pepit")
        menu = QMenu()
        for name, label in PAGES.items():
            action = QAction(label, menu)
            action.triggered.connect(lambda _=False, n=name: self.show(n))
            menu.addAction(action)
        menu.addSeparator()
        xplane = QAction("Lancer X-Plane", menu)
        xplane.triggered.connect(self.launch_xplane)
        menu.addAction(xplane)
        menu.addSeparator()
        quit_action = QAction("Quitter Pepit", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        self._menu = menu                    # garder une référence
        tray.activated.connect(lambda reason: self.show("simulateur")
                               if reason == QSystemTrayIcon.Trigger else None)
        tray.show()
        return tray

    def quit(self):
        self.quitting = True
        self.usb.stop()
        for window in self.pages.values():
            window.close()                   # chacun se désabonne ; le cockpit ferme sa liaison
        self.hub.close()                     # puis les cartes elles-mêmes
        if self.tray is not None:
            self.tray.hide()
        self.app.quit()


def main(argv=None):
    args = parse(sys.argv[1:] if argv is None else argv)
    prepare()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Pepit")
    profile = str(Path(args.profil).resolve().relative_to(ROOT)) if args.profil and \
        Path(args.profil).resolve().is_relative_to(ROOT) else args.profil
    message = instance.encode("afficher", args.page, *([profile] if profile else []))
    if not args.fond and instance.send(message):
        print(f"Pepit est déjà ouvert : page « {PAGES[args.page]} » affichée.", flush=True)
        return 0
    if args.fond and instance.send(instance.encode("rien")):
        return 0                             # déjà en fond : rien à faire
    channel = instance.Instance()
    if not channel.listen():
        print("Pepit : impossible d'ouvrir le canal de l'instance unique.", file=sys.stderr)
    pepit = Pepit(app, profile)
    channel.message.connect(pepit.on_message)
    if not args.fond or pepit.tray is None:
        pepit.show(args.page)
    code = app.exec()
    channel.close()
    return code
