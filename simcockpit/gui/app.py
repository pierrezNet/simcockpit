"""Fenêtre principale : liste des cartes détectées, un onglet par carte."""

import sys

from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from ..hw import manager
from .card_view import CardView
from .qtenv import prepare


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("simcockpit — test des cartes")
        self.resize(1200, 700)
        self.views = {}  # usb_port -> CardView

        central = QWidget()
        lay = QVBoxLayout(central)
        bar = QHBoxLayout()
        self.found = QLabel()
        refresh = QPushButton("Rechercher les cartes")
        refresh.clicked.connect(self.rescan)
        bar.addWidget(self.found, 1)
        bar.addWidget(refresh)
        lay.addLayout(bar)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        self.rescan()

    def rescan(self):
        for port, view in list(self.views.items()):   # ferme proprement les anciennes vues
            view.stop()
            self.tabs.removeTab(self.tabs.indexOf(view))
            view.deleteLater()
        self.views.clear()
        cards = manager.scan()
        if not cards:
            self.found.setText("Aucune carte de cockpit détectée. Branchez-la puis « Rechercher ».")
            return
        self.found.setText("Cartes : " + ", ".join(
            f"{d.label} (port {d.info.usb_port})" for d in cards))
        for d in cards:
            view = CardView(d)
            self.tabs.addTab(view, f"{d.label.split(' (')[0]} [{d.info.usb_port}]")
            self.views[d.info.usb_port] = view
            view.start()

    def closeEvent(self, event):
        for view in self.views.values():
            view.stop()
        super().closeEvent(event)


def main():
    prepare()
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()
