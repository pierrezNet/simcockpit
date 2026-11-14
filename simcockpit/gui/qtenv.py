"""Préparation de l'environnement Qt, à appeler AVANT de créer QApplication.

- Thème : sous GNOME, Qt charge par défaut son thème GTK (libqgtk3), qui lit la clé
  « antialiasing » du schéma org.gnome.settings-daemon.plugins.xsettings. Cette clé
  n'existe plus dans les GNOME récents : GLib arrête alors le programme (core dumped).
  Le thème « xdgdesktopportal » évite ce chemin.
- Position des fenêtres : sous Wayland, GNOME interdit à une application de choisir sa
  position (seule la taille se mémorise). On passe donc par XWayland (plateforme « xcb »)
  quand toutes les bibliothèques nécessaires sont présentes (XCB_LIBS).
Un choix explicite de l'utilisateur (QT_QPA_PLATFORMTHEME, QT_QPA_PLATFORM) est respecté.
"""

import ctypes
import os

# Bibliothèques dont le module « xcb » de Qt a besoin (relevé par ldd) → paquet Ubuntu.
XCB_LIBS = {
    "libxcb-cursor.so.0": "libxcb-cursor0", "libxcb-icccm.so.4": "libxcb-icccm4",
    "libxcb-keysyms.so.1": "libxcb-keysyms1", "libxcb-xkb.so.1": "libxcb-xkb1",
    "libxkbcommon-x11.so.0": "libxkbcommon-x11-0", "libxcb-image.so.0": "libxcb-image0",
    "libxcb-render-util.so.0": "libxcb-render-util0", "libxcb-randr.so.0": "libxcb-randr0",
    "libxcb-shape.so.0": "libxcb-shape0", "libxcb-shm.so.0": "libxcb-shm0",
    "libxcb-sync.so.1": "libxcb-sync1", "libxcb-util.so.1": "libxcb-util1",
    "libxcb-xfixes.so.0": "libxcb-xfixes0", "libxcb-render.so.0": "libxcb-render0",
    "libX11-xcb.so.1": "libx11-xcb1", "libX11.so.6": "libx11-6", "libxcb.so.1": "libxcb1",
    "libxkbcommon.so.0": "libxkbcommon0",
}


def missing_xcb_packages():
    """Paquets à installer pour que Qt puisse passer par XWayland ([] si rien ne manque)."""
    missing = []
    for lib, package in XCB_LIBS.items():
        try:
            ctypes.CDLL(lib)
        except OSError:
            missing.append(package)
    return missing


def prepare():
    os.environ.setdefault("QT_QPA_PLATFORMTHEME", "xdgdesktopportal")
    if (os.environ.get("XDG_SESSION_TYPE") == "wayland" and "QT_QPA_PLATFORM" not in os.environ
            and os.environ.get("DISPLAY")):
        missing = missing_xcb_packages()
        if not missing:
            os.environ["QT_QPA_PLATFORM"] = "xcb"          # XWayland : position mémorisable
        else:
            print("simcockpit : sous Wayland, seule la taille des fenêtres est mémorisée ;"
                  f" pour la position aussi : sudo apt install {' '.join(missing)}", flush=True)
