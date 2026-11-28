"""Écran du CDU : dessin (16 × 24 caractères pour le FMS d'X-Plane, 14 × 25 pour l'UFMC ;
couleurs, deux tailles) et fenêtre plein écran
sur l'écran physique du CDU. N'affiche que ce que la logique (logic/cdu_screen.py) a lu
dans X-Plane."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..hw.screens import content_rect
from ..logic.cdu_screen import COLUMNS, LINES

COLORS = {0: "#000000", 1: "#3ad6f0", 2: "#ff4040", 3: "#ffe14d", 4: "#36e05a",
          5: "#ff5ce6", 6: "#ffb000", 7: "#f2f2f2"}
BACKGROUND = "#050505"


class CduCanvas(QWidget):
    """Dessin de l'écran ; `margins` (gauche, haut, droite, bas) en pixels. Avec `test_card`,
    une mire (cadre et grille) aide à caler l'image dans la découpe de la façade."""

    def __init__(self, ctrl, margins=(10, 0, 10, 0), parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.margins = list(margins)
        self.test_card = False

    def set_margins(self, margins):
        self.margins = list(margins)
        self.update()

    def set_test_card(self, on):
        self.test_card = on
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(BACKGROUND))
        x0, y0, w, h = content_rect(self.width(), self.height(), self.margins)
        columns = getattr(self.ctrl, "columns", COLUMNS)
        rows = getattr(self.ctrl, "rows", LINES)
        cw, lh = w / columns, h / rows
        if self.test_card:
            p.setPen(QPen(QColor("#2f6f8f"), 1))
            for c in range(1, columns):
                p.drawLine(int(x0 + c * cw), y0, int(x0 + c * cw), y0 + h)
            for r in range(1, rows):
                p.drawLine(x0, int(y0 + r * lh), x0 + w, int(y0 + r * lh))
            p.setPen(QPen(QColor("#ffb000"), 3))
            p.drawRect(QRectF(x0 + 1.5, y0 + 1.5, w - 3, h - 3))
        big = QFont("monospace", 1, QFont.Bold)
        big.setPixelSize(max(6, int(min(lh * 0.85, cw * 1.45))))
        small = QFont("monospace", 1)
        small.setPixelSize(max(5, int(min(lh * 0.62, cw * 1.1))))
        for row, (text, styles) in enumerate(self.ctrl.lines()):
            y = y0 + row * lh
            for col, ch in enumerate(text):
                st = styles[col] if col < len(styles) else 0
                color = QColor(COLORS.get(st & 0x07, "#f2f2f2"))
                rect = QRectF(x0 + col * cw, y, cw, lh)
                if st & 0x40:                          # vidéo inverse
                    p.fillRect(rect, color)
                    color = QColor(BACKGROUND)
                if ch == " ":
                    continue
                p.setFont(big if st & 0x80 else small)
                p.setPen(color)
                p.drawText(rect, Qt.AlignCenter, ch)
        p.end()


def screen_names():
    """Sorties vidéo connues de Qt : [(nom, « HDMI-2 — 1024 × 768 »)]."""
    out = []
    for s in QGuiApplication.screens():
        g = s.geometry()
        out.append((s.name(), f"{s.name()} — {g.width()} × {g.height()}"))
    return out


class CduDisplayWindow(QWidget):
    """Fenêtre sans bordure qui occupe toute la sortie vidéo de l'écran du CDU.
    Fenêtre enfant de `owner` : elle disparaît avec lui (rechargement, fermeture)."""

    def __init__(self, ctrl, owner):
        super().__init__(owner, Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle("Pepit — écran du CDU")
        self.setCursor(Qt.BlankCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.canvas = CduCanvas(ctrl, (0, 0, 0, 0))
        lay.addWidget(self.canvas)

    def place(self, output):
        """Affiche la fenêtre en plein écran sur la sortie `output` ; False si elle est absente."""
        screen = next((s for s in QGuiApplication.screens() if s.name() == output), None)
        if screen is None:
            self.hide()
            return False
        # Fenêtre sans bordure posée sur toute la sortie, sans passer en mode plein écran :
        # en plein écran, GNOME envoie l'image directement à l'écran sans passer par son
        # compositeur, et sur la 2e carte graphique (GT 1030) l'écran du CDU restait figé
        # sur la première image (constaté le 2026-11-17).
        self.setGeometry(screen.geometry())
        self.show()
        handle = self.windowHandle()
        if handle is not None:
            handle.setScreen(screen)
        self.setGeometry(screen.geometry())
        return True
